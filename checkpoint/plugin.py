"""Native QGIS history controller with explicit scope, recovery and path transitions."""
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
import traceback
from uuid import uuid4

from qgis.core import Qgis, QgsApplication, QgsMessageLog, QgsProject, QgsSettings
from qgis.PyQt.QtCore import Qt, QTimer, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from .core.differ import application_summary
from .core.thumbnail import PreviewTask
from .core.snapshot import adopt_tree_identity, capture, prepare_restore, prepare_view, restore
from .core.store import HistoryStore, HistoryError, project_key
from .core.watcher import Watcher, disconnect
from .ui.panel import HistoryPanel
from .ui.settings import OptionsFactory


def tr(text):
    return QCoreApplication.translate("Checkpoint", text)


class CheckpointPlugin:
    def __init__(self, iface):
        self.iface, self.project = iface, QgsProject.instance()
        self.root = Path(QgsApplication.qgisSettingsDirPath()) / "checkpoint"
        self.panel = self.action = self.store = self.watcher = None
        self._connections, self.preview_task = [], None
        self.settings, self.options_factory = QgsSettings(), None
        self._busy, self._unloaded = False, False
        self._save_error, self._last_recovery_id = "", None
        self._details_timer = QTimer()
        self._details_timer.setSingleShot(True)
        self._details_timer.timeout.connect(self._update_details)

    def initGui(self):
        self.panel = HistoryPanel(self.iface.mainWindow())
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.panel)
        self.action = self.panel.toggleViewAction()
        self.action.setIcon(QIcon(str(Path(__file__).with_name("icon.png"))))
        self.iface.addPluginToMenu("Checkpoint", self.action)
        self.iface.addToolBarIcon(self.action)
        self.options_factory = OptionsFactory(self._apply_options)
        self.iface.registerOptionsWidgetFactory(self.options_factory)
        p = self.panel
        p.interval.setValue(self.settings.value("checkpoint/interval", 60, type=int))
        p.pin_button.clicked.connect(lambda: self._history_action("pin"))
        p.rename_button.clicked.connect(lambda: self._history_action("rename"))
        p.delete_button.triggered.connect(lambda: self._history_action("delete"))
        p.cleanup_action.triggered.connect(self._cleanup_recovery)
        p.export_action.triggered.connect(self._export)
        p.refresh_action.triggered.connect(self._reload)
        p.options_button.clicked.connect(lambda: self.iface.showOptionsDialog(self.iface.mainWindow()))
        p.previews.setChecked(self.settings.value("checkpoint/previews", True, type=bool))
        p.previews.toggled.connect(self._toggle_previews)
        p.retry_button.clicked.connect(self._retry_previews)
        p.save_button.clicked.connect(self._manual_save)
        p.restore_button.clicked.connect(self._restore_selected)
        p.undo_button.clicked.connect(self._undo)
        p.selectionChanged.connect(self._update_details)
        p.full_scope.toggled.connect(self._update_details)
        p.mode.currentIndexChanged.connect(self._configure)
        p.interval.valueChanged.connect(self._configure)
        for signal, slot in (
            (self.project.cleared, self._cleared),
            (self.project.fileNameChanged, self._path_changed),
            (self.project.projectSaved, self._project_saved),
            (self.iface.projectRead, self._session_ready),
            (self.iface.newProjectCreated, self._session_ready),
            (self.iface.mapCanvas().destinationCrsChanged, self._schedule_details),
            (self.iface.mapCanvas().extentsChanged, self._schedule_details),
        ):
            signal.connect(slot)
            self._connections.append((signal, slot))
        self._session_ready()

    def _apply_options(self):
        if self._unloaded:
            return
        self.panel.previews.setChecked(self.settings.value("checkpoint/previews", True, type=bool))
        self.panel.interval.setValue(self.settings.value("checkpoint/interval", 60, type=int))
        if self.store is not None:
            try:
                self.store.set_limit(self.settings.value("checkpoint/limit", 20, type=int))
                self._refresh()
                self._update_details()
            except Exception as exc:
                self._error(tr("Cannot apply history limit"), exc)

    def _history_action(self, action):
        if self._busy or self.store is None or self.watcher is None:
            return
        try:
            self.store.refresh(return_records=False)
            record = self.store.get_record(self.panel.selected_id())
            if record is None:
                self._refresh()
                return
            if action == "pin":
                self.store.set_pinned(record["id"], not record["pinned"])
            elif action == "rename":
                name, accepted = QInputDialog.getText(self.panel, tr("Rename checkpoint"), tr("Name:"), text=record["name"])
                if not accepted:
                    return
                self.store.rename(record["id"], name)
            elif action == "delete":
                message = tr("Delete this checkpoint permanently?")
                if record["pinned"]:
                    message += " " + tr("This is a pinned checkpoint.")
                if record.get("kind") == "recovery":
                    message += " " + tr("This removes a recovery state and may remove Undo last application.")
                if QMessageBox.question(self.panel, tr("Delete checkpoint"), message,
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                    return
                self.store.delete(record["id"])
            self._refresh()
        except Exception as exc:
            self._error(tr("Cannot update checkpoint"), exc)

    def _cleanup_recovery(self):
        if self._busy or self.store is None:
            return
        if QMessageBox.question(self.panel, tr("Clean up recoveries"), tr(
                "Delete older completed recovery entries? Keep the latest 10, all unresolved/partial applications and every user pin. Legacy 'before restore' pins are kept."),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            count = self.store.cleanup_recovery(keep=10)
            self._refresh()
            self._info(tr("Removed {count} completed recovery entries.").format(count=count))
        except Exception as exc:
            self._error(tr("Cannot clean up recovery history"), exc)

    def _export(self):
        if self.store is None:
            return
        path, _ = QFileDialog.getSaveFileName(self.panel, tr("Export styling history"),
                                             "checkpoint-history.json", tr("JSON history (*.json)"))
        if path:
            try:
                self.store.export(path)
                self._info(tr("History exported. Import into another project is not supported; layer identity must be preserved."))
            except Exception as exc:
                self._error(tr("Cannot export history"), exc)

    def _reload(self):
        try:
            if self.store is not None:
                self.store.refresh(return_records=False)
                self._refresh()
                self._update_details()
            else:
                self._session_ready()
        except Exception as exc:
            self._error(tr("Cannot refresh history"), exc)

    def _cancel_preview(self):
        if self.preview_task is not None:
            task, self.preview_task = self.preview_task, None
            task.cancel(discard=True)

    def _toggle_previews(self, enabled):
        self.settings.setValue("checkpoint/previews", enabled)
        if self.preview_task is not None:
            task, self.preview_task = self.preview_task, None
            task.cancel(tr("Map preview capture switched off"))
        self._preview_status()

    def _retry_previews(self):
        if self.store is None or self._busy:
            return
        self.settings.remove("checkpoint/heavy/" + self.store.key)
        self.panel.previews.setChecked(True)
        self._save(manual=True, retry=True)

    def _preview_status(self):
        heavy = self.store is not None and self.settings.value("checkpoint/heavy/" + self.store.key, False, type=bool)
        self.panel.preview_status.setText(tr("Map previews paused after a slow render. Symbols and details remain available; use Retry maps.")
            if heavy else tr("Map previews enabled.")
            if self.panel.previews.isChecked() else tr("Map previews off. Symbols and text remain available."))

    def _capture_preview(self, record, previous):
        if record is None:
            return
        store = self.store
        maps = self.panel.previews.isChecked() and not self.settings.value(
            "checkpoint/heavy/" + store.key, False, type=bool)
        if self.preview_task is not None:
            self.preview_task.cancel()
        def finished(payload):
            self.preview_task = None
            if self._unloaded or self.store is not store:
                return
            if payload.get("slow"):
                self.settings.setValue("checkpoint/heavy/" + store.key, True)
            try:
                store.set_preview(record["id"], payload)
            except KeyError:
                return
            except Exception as exc:
                QgsMessageLog.logMessage(tr("Cannot save preview: ") + str(exc), "Checkpoint", Qgis.MessageLevel.Warning)
                self.panel.preview_status.setText(tr("Preview could not be saved: ") + str(exc))
                return
            self.panel.set_records(store.records)
            self._preview_status()
        self.preview_task = PreviewTask(self.project, self.iface.mapCanvas(), previous,
                                        record["state"], finished, maps=maps)
        self.preview_task.start()

    def _stop_watcher(self):
        from .core.differ import clear_style_cache
        clear_style_cache()
        if self.watcher is not None:
            self.watcher.close()
            self.watcher.deleteLater()
            self.watcher = None

    def _cleared(self):
        self._details_timer.stop()
        self._cancel_preview()
        self._stop_watcher()
        self.store, self._last_recovery_id, self._save_error = None, None, ""
        self.panel.set_records([])
        self.panel.set_available(False, tr("Waiting for the project to finish opening."))

    def _session_ready(self):
        if self._unloaded:
            return
        self._cancel_preview()
        self._stop_watcher()
        self.store, self._last_recovery_id, self._save_error = None, None, ""
        self.panel.set_records([])
        try:
            self.store = HistoryStore(self.root, self.project.fileName(), self.settings.value("checkpoint/limit", 20, type=int))
            records = self.store.records
            if records and records[-1]["state"].get("schema") == 2:
                adopt_tree_identity(self.project.layerTreeRoot(), records[-1]["state"]["tree"])
            self._start_watcher()
            self._initial_checkpoint()
        except Exception as exc:
            self._error(tr("Cannot open checkpoint history"), exc, disable=True)

    def _initial_checkpoint(self):
        if self.store is None or not self.project.mapLayers():
            self._refresh()
            return
        # iface.projectRead is emitted after loading, never capture on fileNameChanged.
        self._save(manual=False, initial=True)

    def _start_watcher(self):
        self._stop_watcher()
        records, last_saved = self.store.records, None
        if records:
            stamp = datetime.fromisoformat(records[-1]["created_at"])
            age = max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds())
            last_saved = monotonic() - age
        self.watcher = Watcher(self.project, self.panel, last_saved=last_saved)
        self.watcher.saveRequested.connect(self._auto_save)
        self.watcher.stateChanged.connect(self._content_changed)
        self._configure()

    def _content_changed(self):
        self._schedule_details()
        if self.store is not None and not self.store.has_records and self.panel.mode.currentIndex() == 0:
            # For a new empty project, finish the layer-add operation before capture.
            store = self.store
            QTimer.singleShot(0, lambda: self._initial_checkpoint()
                if not self._unloaded and self.store is store and not store.has_records else None)

    def _path_changed(self):
        self._cancel_preview()
        self._stop_watcher()
        self.panel.set_available(False, tr("Project path changed. Complete saving or opening to resume history."))

    def _choose_save_as(self, has_destination):
        box = QMessageBox(self.panel)
        box.setWindowTitle(tr("History after Save As"))
        box.setText(tr("The old project's history stays at its old path."))
        copy = box.addButton(tr("Continue with a copy"), QMessageBox.ButtonRole.AcceptRole)
        copy.setEnabled(not has_destination)
        fresh = box.addButton(tr("Use destination history") if has_destination else tr("Start new history"), QMessageBox.ButtonRole.ActionRole)
        cancel = box.addButton(tr("Decide later"), QMessageBox.ButtonRole.RejectRole)
        if has_destination:
            box.setInformativeText(tr("This destination already has history. It will not be merged or overwritten."))
        box.exec()
        return "copy" if box.clickedButton() is copy else "new" if box.clickedButton() is fresh else "cancel"

    def _project_saved(self):
        path = self.project.fileName()
        if self.store is None or not path:
            return
        try:
            if not self.store.saved:
                self.store.migrate(path)
            elif self.store.key != project_key(path):
                destination = HistoryStore(self.root, path, self.settings.value("checkpoint/limit", 20, type=int))
                choice = self._choose_save_as(bool(destination.records))
                if choice == "cancel":
                    self.panel.set_available(False, tr("History paused after Save As. Save the project again to choose a history."))
                    return
                self.store = self.store.copy_to(path) if choice == "copy" else destination
                self._last_recovery_id = None
            elif self.watcher is not None:
                return
            self._start_watcher()
            self._initial_checkpoint()
        except Exception as exc:
            self._error(tr("Cannot save checkpoint history"), exc, disable=True)

    def _configure(self, *args):
        auto = self.panel.mode.currentIndex() == 0
        self.panel.interval.setEnabled(auto and self.watcher is not None)
        if self.watcher is not None:
            self.watcher.configure(auto, self.panel.interval.value())
        if self.store is not None:
            self._refresh()

    def _refresh(self):
        if self.store is None:
            return
        records = self.store.records
        self.panel.set_records(records)
        self._last_recovery_id = self.store.undo_target()
        self.panel.set_undo_available(self._last_recovery_id is not None)
        if self._save_error:
            message = tr("Saving unavailable: ") + self._save_error + " " + tr("Use Save checkpoint to retry.")
        elif not records:
            message = tr("No starting checkpoint yet. Add layers or save a checkpoint.")
        else:
            message = tr("Auto history active.") if self.panel.mode.currentIndex() == 0 else tr("Manual: use Save checkpoint after changes.")
        if not self.store.saved:
            message += " " + tr("Unsaved project: history only in memory, lost when closed.")
        self.panel.set_available(self.watcher is not None and not self._busy, message)
        self._preview_status()

    def _schedule_details(self, *args):
        if not self._unloaded:
            self._details_timer.start(150)

    def _update_details(self, *args):
        if self._unloaded or self.panel is None or self.store is None or self._busy:
            return
        target = self.panel._records.get(self.panel.selected_id())
        if target is None:
            return
        self._details_timer.stop()
        try:
            current = capture(self.project, self.iface.mapCanvas())
            view_enabled = self.settings.value("checkpoint/restore_view", True, type=bool)
            summary = application_summary(current, target["state"], restore_view=view_enabled, full=self.panel.full_scope.isChecked())
            if view_enabled:
                _, notice = prepare_view(self.project, self.iface.mapCanvas(), target["state"])
                if notice:
                    summary += "\n" + notice
            self.panel.details.setPlainText(summary)
        except Exception as exc:
            self.panel.details.setPlainText(tr("Application unavailable: ") + str(exc))
            self.panel.restore_button.setEnabled(False)

    def _manual_save(self, *args):
        self._save(manual=True)

    def _auto_save(self):
        self._save(manual=False)

    def _save(self, *, manual, initial=False, retry=False):
        if self._busy or self.store is None or self.watcher is None:
            return
        self._busy = True
        try:
            records = self.store.refresh()
            previous = records[-1]["state"] if records else None
            record = self.store.append(capture(self.project, self.iface.mapCanvas()),
                description=tr("Session starting point") if initial else tr("Map preview retry with current data") if retry else None,
                force=retry)
            self._save_error = ""
            self.watcher.acknowledge(record is not None)
            self._capture_preview(record, previous)
            if manual:
                self._info(tr("Checkpoint saved.") if record is not None else tr("No styling changes. Checkpoint not saved."))
        except Exception as exc:
            self._save_error = str(exc)
            self._error(tr("Starting checkpoint unavailable") if initial else tr("Cannot save checkpoint"), exc)
        finally:
            self._busy = False
            self._refresh()
            if manual:
                self._update_details()

    def _restore_selected(self, *args):
        self._apply(self.panel.selected_id())

    def _undo(self):
        self._apply(self._last_recovery_id, undo=True)

    def _apply(self, record_id, *, undo=False):
        if self._busy or self.store is None or self.watcher is None or not record_id:
            return
        self._busy = True
        safety, applied = None, False
        self.panel.set_available(False, tr("Applying saved styling…"))
        try:
            self.store.refresh(return_records=False)
            if undo and self.store.undo_target() != record_id:
                raise HistoryError("Undo target is no longer available; refresh history")
            target = self.store.get_record(record_id)
            if target is None:
                raise HistoryError("The selected checkpoint was deleted by another session")
            view_enabled = self.settings.value("checkpoint/restore_view", True, type=bool)
            # Preflight rejects special trees and malformed styles before safety or mutation.
            prepare_restore(self.project, self.iface.mapCanvas(), target["state"], restore_view=view_enabled)
            title = target["name"] or target["description"]
            event = uuid4().hex
            safety = self.store.append_restore(capture(self.project, self.iface.mapCanvas()),
                before=True, event_id=event, target=(tr("Undo application") if undo else title),
                operation="undo" if undo else "apply", undo_of=record_id if undo else None)
            if not undo:
                self._last_recovery_id = safety["id"]
            with self.watcher.suppress():
                notices = restore(self.project, self.iface.mapCanvas(), target["state"], restore_view=view_enabled)
                applied = True
                result = self.store.append_restore(capture(self.project, self.iface.mapCanvas()),
                    event_id=event, target=target["id"], description=tr("Applied: ") + title
                    + ("; " + "; ".join(notices) if notices else ""))
                self.store.finish_recovery(safety["id"], "partial" if notices else "complete")
                if undo and not notices:
                    self.store.finish_recovery(target["id"], "undone")
                self.watcher.acknowledge(True)
            self._save_error = ""
            self._capture_preview(result, safety["state"])
            self._info(tr("Undo complete. Current edits were saved in a recovery checkpoint.") if undo and not notices else tr("Saved styling applied. Undo last application is available.")
                       + (" " + "; ".join(notices) if notices else ""), warning=bool(notices))
        except Exception as exc:
            if isinstance(exc, (HistoryError, OSError)):
                self._save_error = str(exc)
            if safety is None:
                title = tr("Application cancelled before map changes")
            elif applied:
                title = tr("Styling applied, but result could not be recorded; recovery and Undo are available")
            else:
                title = tr("Application partially failed; recovery and Undo are available")
            self._error(title, exc)
        finally:
            self._busy = False
            self._refresh()
            self._update_details()

    def _info(self, message, *, warning=False):
        self.iface.messageBar().pushMessage("Checkpoint", message,
            level=Qgis.MessageLevel.Warning if warning else Qgis.MessageLevel.Info, duration=0 if warning else 5)

    def _error(self, title, exc, *, disable=False):
        if disable:
            self._stop_watcher()
        self.panel.set_available(not disable and self.watcher is not None and not self._busy, f"{title}: {exc}")
        QgsMessageLog.logMessage(traceback.format_exc(), "Checkpoint", Qgis.MessageLevel.Critical)
        self.iface.messageBar().pushMessage(title, str(exc), level=Qgis.MessageLevel.Critical, duration=0)

    def unload(self):
        self._unloaded = True
        self._details_timer.stop()
        if self.options_factory is not None:
            self.iface.unregisterOptionsWidgetFactory(self.options_factory)
            self.options_factory = None
        self._cancel_preview()
        self._stop_watcher()
        disconnect(self._connections)
        if self.action is not None:
            self.iface.removePluginMenu("Checkpoint", self.action)
            self.iface.removeToolBarIcon(self.action)
        if self.panel is not None:
            self.iface.removeDockWidget(self.panel)
            self.panel.deleteLater()
        self.panel = self.action = self.store = None
