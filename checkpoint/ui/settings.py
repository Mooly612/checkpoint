"""Checkpoint controls in the standard QGIS Options dialog."""
from pathlib import Path
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsSettings
from qgis.gui import QgsOptionsPageWidget, QgsOptionsWidgetFactory
from qgis.PyQt.QtWidgets import QCheckBox, QFormLayout, QSpinBox


class OptionsPage(QgsOptionsPageWidget):
    def __init__(self, parent, changed):
        super().__init__(parent)
        self.changed = changed
        settings = QgsSettings()
        layout = QFormLayout(self)
        self.previews = QCheckBox("Save previews", self)
        self.previews.setChecked(settings.value("checkpoint/previews", True, type=bool))
        self.view = QCheckBox("Restore map view", self)
        self.view.setChecked(settings.value("checkpoint/restore_view", True, type=bool))
        self.limit = QSpinBox(self)
        self.limit.setRange(1, 10000)
        self.limit.setValue(settings.value("checkpoint/limit", 20, type=int))
        self.interval = QSpinBox(self)
        self.interval.setRange(1, 86400)
        self.interval.setSuffix(" s")
        self.interval.setValue(settings.value("checkpoint/interval", 60, type=int))
        layout.addRow(self.previews)
        layout.addRow(self.view)
        layout.addRow("Unpinned history limit", self.limit)
        layout.addRow("Default automatic interval", self.interval)

    def apply(self):
        settings = QgsSettings()
        for key, value in (("previews", self.previews.isChecked()),
                           ("restore_view", self.view.isChecked()),
                           ("limit", self.limit.value()), ("interval", self.interval.value())):
            settings.setValue("checkpoint/" + key, value)
        self.changed()


class OptionsFactory(QgsOptionsWidgetFactory):
    def __init__(self, changed):
        super().__init__("Checkpoint", QIcon(str(Path(__file__).resolve().parents[1] / "icon.svg")))
        self.changed = changed

    def createWidget(self, parent):
        return OptionsPage(parent, self.changed)
