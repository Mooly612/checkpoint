"""Wire the QGIS dock, per-project history, and watcher."""

from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
import traceback

from qgis.core import Qgis, QgsApplication, QgsMessageLog, QgsProject
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon

from .core.snapshot import capture
from .core.store import HistoryStore, project_key
from .core.watcher import Watcher, disconnect
from .ui.panel import HistoryPanel


class CheckpointPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.project = QgsProject.instance()
        self.root = Path(QgsApplication.qgisSettingsDirPath()) / "checkpoint"
        self.panel = self.action = self.store = self.watcher = None
        self._connections = []
        self._busy, self._unloaded = False, False

    def initGui(self):
        self.panel = HistoryPanel(self.iface.mainWindow())
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.panel)
        self.action = self.panel.toggleViewAction()
        self.action.setIcon(QIcon(str(Path(__file__).with_name("icon.svg"))))
        self.iface.addPluginToMenu("Checkpoint", self.action)
        self.iface.addToolBarIcon(self.action)
        self.panel.save_button.clicked.connect(self._manual_save)
        self.panel.mode.currentIndexChanged.connect(self._configure)
        self.panel.interval.valueChanged.connect(self._configure)
        for signal, slot in (
            (self.project.cleared, self._cleared),
            (self.project.fileNameChanged, self._path_changed),
            (self.project.projectSaved, self._project_saved),
            (self.iface.projectRead, self._session_ready),
            (self.iface.newProjectCreated, self._session_ready),
        ):
            signal.connect(slot)
            self._connections.append((signal, slot))
        self._session_ready()

    def _stop_watcher(self):
        if self.watcher is not None:
            self.watcher.close()
            self.watcher.deleteLater()
            self.watcher = None

    def _cleared(self):
        self._stop_watcher()
        self.store = None
        self.panel.set_records([])
        self.panel.set_available(False, "Waiting for the project to finish opening.")

    def _session_ready(self):
        if self._unloaded:
            return
        self._stop_watcher()
        self.store = None
        self.panel.set_records([])
        try:
            self.store = HistoryStore(self.root, self.project.fileName())
            self._start_watcher()
        except Exception as exc:
            self._error("Cannot open checkpoint history", exc, disable=True)

    def _start_watcher(self):
        self._stop_watcher()
        records = self.store.records
        last_saved = None
        if records:
            stamp = datetime.fromisoformat(records[-1]["created_at"])
            age = max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds())
            last_saved = monotonic() - age
        self.watcher = Watcher(self.project, self.panel, last_saved=last_saved)
        self.watcher.saveRequested.connect(self._auto_save)
        self._configure()
        self._refresh()

    def _path_changed(self):
        # Also emitted during opening. Wait for projectSaved or iface.projectRead
        # before deciding whether to migrate or switch to another history.
        self._stop_watcher()
        self.panel.set_available(False, "Project path changed. Complete saving or opening to resume history.")

    def _project_saved(self):
        path = self.project.fileName()
        if self.store is None or not path:
            return
        try:
            if not self.store.saved:
                self.store.migrate(path)
            elif self.store.key != project_key(path):
                self.store = HistoryStore(self.root, path)
            else:
                if self.watcher is not None:
                    return
            self._start_watcher()
            # Catch any styling change made while a path transition was paused.
            self.watcher.mark_dirty()
        except Exception as exc:
            self._error("Cannot save checkpoint history", exc, disable=True)

    def _configure(self, *args):
        auto = self.panel.mode.currentText() == "Auto"
        self.panel.interval.setEnabled(auto and self.watcher is not None)
        if self.watcher is not None:
            self.watcher.configure(auto, self.panel.interval.value())

    def _refresh(self):
        records = self.store.records
        self.panel.set_records(records)
        message = "Project history." if self.store.saved else "Unsaved project: history stays in memory."
        if not records:
            message += " Save the current style to start."
        self.panel.set_available(True, message)

    def _manual_save(self, *args):
        self._save(manual=True)

    def _auto_save(self):
        self._save(manual=False)

    def _save(self, *, manual: bool):
        if self._busy or self.store is None or self.watcher is None:
            return
        self._busy = True
        try:
            record = self.store.append(capture(self.project, self.iface.mapCanvas()))
            self.watcher.acknowledge(record is not None)
            self._refresh()
            if manual:
                text = "Checkpoint saved." if record is not None else "No styling changes. Checkpoint not saved."
                self.iface.messageBar().pushMessage("Checkpoint", text, level=Qgis.MessageLevel.Info, duration=4)
        except Exception as exc:
            self._error("Cannot save checkpoint", exc)
        finally:
            self._busy = False

    def _error(self, title, exc, *, disable=False):
        if disable:
            self._stop_watcher()
        self.panel.set_available(not disable and self.watcher is not None, f"{title}: {exc}")
        QgsMessageLog.logMessage(traceback.format_exc(), "Checkpoint", Qgis.MessageLevel.Critical)
        self.iface.messageBar().pushMessage(title, str(exc), level=Qgis.MessageLevel.Critical, duration=0)

    def unload(self):
        self._unloaded = True
        self._stop_watcher()
        disconnect(self._connections)
        if self.action is not None:
            self.iface.removePluginMenu("Checkpoint", self.action)
            self.iface.removeToolBarIcon(self.action)
        if self.panel is not None:
            self.iface.removeDockWidget(self.panel)
            self.panel.deleteLater()
        self.panel = self.action = self.store = None
