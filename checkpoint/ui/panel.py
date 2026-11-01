"""Native history dock with explicit save and restore actions."""

from datetime import datetime

from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDockWidget, QFormLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)


from .preview import PreviewDialog, sample_icon


class HistoryPanel(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Checkpoint", parent)
        self.setObjectName("CheckpointHistoryDock")
        body = QWidget(self)
        layout = QVBoxLayout(body)
        layout.addWidget(QLabel("Undo for your map styling.", body))
        form = QFormLayout()
        self.mode = QComboBox(body)
        self.mode.addItems(["Auto", "Manual"])
        self.interval = QSpinBox(body)
        self.interval.setRange(1, 86400)
        self.interval.setValue(60)
        self.interval.setSuffix(" s")
        self.interval.setToolTip("Minimum gap between automatic checkpoints, after styling changes settle.")
        form.addRow("Mode", self.mode)
        form.addRow("Minimum gap", self.interval)
        layout.addLayout(form)
        self.save_button = QPushButton("Save checkpoint", body)
        layout.addWidget(self.save_button)
        self.previews = QCheckBox("Previews", body)
        self.previews.setToolTip("Save symbol samples and before/after maps for new checkpoints.")
        layout.addWidget(self.previews)
        self.preview_status = QLabel(body)
        self.preview_status.setWordWrap(True)
        self.preview_status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.preview_status)
        self.status = QLabel(body)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.history = QListWidget(body)
        self.history.setWordWrap(False)
        self.history.setIconSize(QSize(76, 60))
        self.history.itemClicked.connect(self._open_preview)
        self.history.itemActivated.connect(self._open_preview)
        self._records = {}
        self._dialog = None
        self.history.setAccessibleName("Checkpoint history")
        layout.addWidget(self.history)
        self.restore_button = QPushButton("Restore selected checkpoint", body)
        self.restore_button.setToolTip("Pin the current state, then restore the selected checkpoint.")
        self.restore_button.setEnabled(False)
        layout.addWidget(self.restore_button)
        self._available = False
        self.history.currentItemChanged.connect(self._selection_changed)
        self.setWidget(body)

    def set_available(self, available: bool, message: str):
        self._available = available
        self._selection_changed()
        self.save_button.setEnabled(available)
        self.mode.setEnabled(available)
        self.interval.setEnabled(available and self.mode.currentText() == "Auto")
        self.status.setText(message)

    def selected_id(self):
        item = self.history.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _selection_changed(self, *args):
        self.restore_button.setEnabled(self._available and self.selected_id() is not None)

    def _open_preview(self, item):
        record = self._records.get(item.data(Qt.ItemDataRole.UserRole))
        if record is None or not self.previews.isChecked():
            return
        if self._dialog is not None:
            self._dialog.close()
        self._dialog = PreviewDialog(record, self)
        dialog = self._dialog
        dialog.destroyed.connect(lambda: self._dialog_closed(dialog))
        self._dialog.show()

    def _dialog_closed(self, dialog):
        if self._dialog is dialog:
            self._dialog = None

    def set_records(self, records: list):
        current = self.history.currentItem()
        selected = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        self.history.clear()
        self._records = {r["id"]: r for r in records}
        if self._dialog is not None and self._dialog.record_id in self._records:
            self._dialog.set_record(self._records[self._dialog.record_id])
        day = None
        for record in reversed(records):
            try:
                date = datetime.fromisoformat(record["created_at"]).astimezone()
                stamp = date.strftime("%H:%M:%S")
                record_day = date.strftime("%Y-%m-%d")
            except ValueError:
                stamp = record["created_at"]
                record_day = ""
            title = record["name"] or record["description"]
            prefix = "[Pinned] " if record["pinned"] else ""
            heading = record_day + "\n" if record_day != day else ""
            day = record_day
            preview = record.get("preview", {})
            more = f" (+{preview['more']} symbols)" if preview.get("more") else ""
            item = QListWidgetItem(f"{heading}{stamp}  {prefix}{title}{more}", self.history)
            if self.previews.isChecked():
                item.setIcon(sample_icon(preview))
            item.setData(Qt.ItemDataRole.UserRole, record["id"])
            details = "\n".join(s["label"] for s in preview.get("samples", []))
            item.setToolTip(record["description"] + "\nBefore → After\n" + details
                            + "\n" + preview.get("status", "No saved preview")
                            + "\nClick to open saved maps. Restore uses the separate button.")
            if record["id"] == selected:
                self.history.setCurrentItem(item)
