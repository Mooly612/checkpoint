"""Native history dock with explicit save and restore actions."""

from datetime import datetime

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QComboBox, QDockWidget, QFormLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)


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
        self.status = QLabel(body)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.history = QListWidget(body)
        self.history.setWordWrap(True)
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

    def set_records(self, records: list):
        current = self.history.currentItem()
        selected = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        self.history.clear()
        for record in reversed(records):
            try:
                stamp = datetime.fromisoformat(record["created_at"]).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                stamp = record["created_at"]
            title = record["name"] or record["description"]
            prefix = "[Pinned] " if record["pinned"] else ""
            item = QListWidgetItem(f"{stamp}\n{prefix}{title}", self.history)
            item.setData(Qt.ItemDataRole.UserRole, record["id"])
            item.setToolTip(record["description"])
            if record["id"] == selected:
                self.history.setCurrentItem(item)
