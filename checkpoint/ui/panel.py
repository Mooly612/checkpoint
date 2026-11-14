"""Native dock: selection explains scope; only explicit buttons apply or preview."""
from datetime import datetime

from qgis.PyQt.QtCore import QSize, Qt, QSignalBlocker, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDockWidget, QFormLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QSpinBox, QVBoxLayout, QWidget, QHBoxLayout,
    QPlainTextEdit, QMenu, QToolButton, QSplitter,
)
from .preview import PreviewDialog, sample_icon


class HistoryPanel(QDockWidget):
    selectionChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Checkpoint", parent)
        self.setObjectName("CheckpointHistoryDock")
        self._records, self._dialog = {}, None
        self._available, self._undo_available = False, False
        body = QWidget(self)
        layout = QVBoxLayout(body)
        form = QFormLayout()
        self.mode = QComboBox(body)
        self.mode.addItems([self.tr("Auto"), self.tr("Manual")])
        self.interval = QSpinBox(body)
        self.interval.setRange(1, 86400)
        self.interval.setValue(60)
        self.interval.setSuffix(self.tr(" s"))
        self.interval.setToolTip(self.tr("Wait for 2 seconds without styling changes, then save when the minimum gap has elapsed. Panning, zooming and expanding groups alone do not create entries."))
        form.addRow(self.tr("Mode"), self.mode)
        form.addRow(self.tr("Minimum gap"), self.interval)
        layout.addLayout(form)
        self.status = QLabel(body)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.save_button = QPushButton(self.tr("Save checkpoint"), body)
        layout.addWidget(self.save_button)
        previews = QHBoxLayout()
        self.previews = QCheckBox(self.tr("Save map previews"), body)
        self.previews.setToolTip(self.tr("Map rendering is optional. Text and lightweight symbol samples remain available."))
        self.retry_button = QPushButton(self.tr("Retry maps"), body)
        self.retry_button.setToolTip(self.tr("Create a fresh checkpoint with today's data and retry map rendering. Existing images stay unchanged."))
        previews.addWidget(self.previews)
        previews.addWidget(self.retry_button)
        layout.addLayout(previews)
        self.preview_status = QLabel(body)
        self.preview_status.setToolTip(self.tr("Saved images show historical comparisons using data available at capture time. They are not a simulation of applying this entry now."))
        self.preview_status.setWordWrap(True)
        self.preview_status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.preview_status)
        self.history = QListWidget(body)
        self.history.setWordWrap(False)
        self.history.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.history.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.history.setIconSize(QSize(76, 60))
        self.history.setAccessibleName(self.tr("Checkpoint history"))
        self.history.setMinimumHeight(110)
        self.splitter = QSplitter(Qt.Orientation.Vertical, body)
        self.splitter.addWidget(self.history)
        scope = QWidget(body)
        scope_layout = QVBoxLayout(scope)
        scope_layout.setContentsMargins(0, 0, 0, 0)
        scope_layout.addWidget(QLabel(self.tr("Changes relative to the current project"), body))
        self.full_scope = QCheckBox(self.tr("Show full snapshot contents"), scope)
        scope_layout.addWidget(self.full_scope)
        self.details = QPlainTextEdit(body)
        self.details.setReadOnly(True)
        self.details.setAccessibleName(self.tr("Application scope"))
        self.details.setPlaceholderText(self.tr("Select a checkpoint to inspect its scope."))
        self.details.setMinimumHeight(105)
        scope_layout.addWidget(self.details)
        self.splitter.addWidget(scope)
        self.splitter.setSizes([240, 220])
        from qgis.core import QgsSettings
        sizes = QgsSettings().value("checkpoint/splitter", None)
        if sizes:
            self.splitter.restoreState(sizes)
        self.splitter.splitterMoved.connect(lambda *args: QgsSettings().setValue(
            "checkpoint/splitter", self.splitter.saveState()))
        layout.addWidget(self.splitter, 1)
        self.restore_button = QPushButton(self.tr("Apply saved map styling"), body)
        self.restore_button.setToolTip(self.tr("Save a recovery checkpoint, then apply all supported saved styling."))
        layout.addWidget(self.restore_button)
        self.undo_button = QPushButton(self.tr("Undo last application"), body)
        self.undo_button.setToolTip(self.tr("Restore the state before the last Apply, including later manual styling edits. Current styling is saved as a recovery first. Single-level Undo."))
        layout.addWidget(self.undo_button)
        actions = QHBoxLayout()
        self.pin_button = QPushButton(self.tr("Pin"), body)
        self.rename_button = QPushButton(self.tr("Rename"), body)
        self.preview_button = QPushButton(self.tr("Preview"), body)
        for button in (self.pin_button, self.rename_button, self.preview_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        footer = QHBoxLayout()
        self.options_button = QPushButton(self.tr("Settings…"), body)
        self.more_button = QToolButton(body)
        self.more_button.setText(self.tr("History…"))
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.more_button)
        self.delete_button = menu.addAction(self.tr("Delete selected checkpoint…"))
        self.cleanup_action = menu.addAction(self.tr("Clean up completed recoveries…"))
        self.export_action = menu.addAction(self.tr("Export history…"))
        self.refresh_action = menu.addAction(self.tr("Refresh history"))
        self.more_button.setMenu(menu)
        footer.addWidget(self.options_button)
        footer.addWidget(self.more_button)
        layout.addLayout(footer)
        self.history.currentItemChanged.connect(self._selection_changed)
        self.preview_button.clicked.connect(lambda: self._open_preview(self.history.currentItem()))
        self.setWidget(body)
        self._selection_changed()

    def set_available(self, available, message):
        self._available = available
        self._selection_changed(notify=False)
        self.save_button.setEnabled(available)
        self.mode.setEnabled(available)
        self.interval.setEnabled(available and self.mode.currentIndex() == 0)
        self.retry_button.setEnabled(available)
        self.export_action.setEnabled(bool(self._records))
        self.cleanup_action.setEnabled(available)
        self.status.setText(message)

    def set_undo_available(self, available):
        self._undo_available = available
        self.undo_button.setEnabled(self._available and available)

    def selected_id(self):
        item = self.history.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _selection_changed(self, *args, notify=True):
        record = self._records.get(self.selected_id())
        enabled = self._available and record is not None
        for button in (self.restore_button, self.pin_button, self.rename_button, self.delete_button):
            button.setEnabled(enabled)
        self.preview_button.setEnabled(record is not None)
        self.undo_button.setEnabled(self._available and self._undo_available)
        self.pin_button.setText(self.tr("Unpin") if record and record["pinned"] else self.tr("Pin"))
        if record is None:
            self.details.clear()
        if notify:
            self.selectionChanged.emit()

    def _open_preview(self, item):
        if item is None:
            return
        record = self._records.get(item.data(Qt.ItemDataRole.UserRole))
        if record is None:
            return
        if self._dialog is not None:
            self._dialog.close()
        self._dialog = PreviewDialog(record, self)
        dialog = self._dialog
        dialog.destroyed.connect(lambda: self._dialog_closed(dialog))
        dialog.show()

    def _dialog_closed(self, dialog):
        if self._dialog is dialog:
            self._dialog = None

    def set_records(self, records):
        """Reuse unchanged items and preserve selection/scroll during preview updates."""
        selected = self.selected_id()
        old_records = self._records
        self._records = {r["id"]: r for r in records}
        blocker = QSignalBlocker(self.history)
        items = {self.history.item(i).data(Qt.ItemDataRole.UserRole): self.history.item(i)
                 for i in range(self.history.count())}
        for key in items.keys() - self._records.keys():
            self.history.takeItem(self.history.row(items.pop(key)))
        for index, record in enumerate(reversed(records)):
            key = record["id"]
            item = items.get(key)
            if item is None:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, key)
                self.history.insertItem(index, item)
            elif self.history.row(item) != index:
                self.history.takeItem(self.history.row(item))
                self.history.insertItem(index, item)
            if old_records.get(key) != record:
                try:
                    stamp = datetime.fromisoformat(record["created_at"]).astimezone().strftime("%d %b %H:%M:%S")
                except ValueError:
                    stamp = record["created_at"]
                prefix = self.tr("[Pinned] ") if record["pinned"] else ""
                if record.get("kind") == "recovery":
                    prefix += self.tr("[Recovery] ")
                title = record["name"] or record["description"]
                item.setText(f"{stamp}  {prefix}\n{title}")
                preview = record.get("preview", {})
                item.setIcon(sample_icon(preview))
                item.setToolTip(self.tr("Historical change: ") + record["description"]
                                + "\n" + preview.get("status", self.tr("No saved preview")))
            if key == selected:
                self.history.setCurrentItem(item)
        del blocker
        if self._dialog is not None:
            if self._dialog.record_id in self._records:
                self._dialog.set_record(self._records[self._dialog.record_id])
            else:
                self._dialog.close()
        self._selection_changed(notify=selected != self.selected_id())
