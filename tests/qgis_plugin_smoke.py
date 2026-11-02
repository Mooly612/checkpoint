"""Real QGIS/Qt checks with a small iface harness, not the live QGIS main window."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from qgis.core import QgsProject, QgsRectangle, QgsVectorLayer
from qgis.gui import QgsMapCanvas, QgsMessageBar
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QMainWindow

from checkpoint import classFactory
from checkpoint.core.store import HistoryStore, project_key


class InterfaceHarness(QObject):
    projectRead = pyqtSignal()
    newProjectCreated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.window = QMainWindow()
        self.canvas = QgsMapCanvas(self.window)
        self.bar = QgsMessageBar(self.window)
        self.toolbar = self.window.addToolBar("Plugins")
        self.menu = self.window.menuBar().addMenu("Plugins")

    def registerOptionsWidgetFactory(self, factory):
        self.factory = factory

    def unregisterOptionsWidgetFactory(self, factory):
        assert self.factory is factory
        self.factory = None

    def showOptionsDialog(self, parent):
        pass

    def mainWindow(self):
        return self.window

    def mapCanvas(self):
        return self.canvas

    def messageBar(self):
        return self.bar

    def addDockWidget(self, area, panel):
        self.window.addDockWidget(area, panel)

    def removeDockWidget(self, panel):
        self.window.removeDockWidget(panel)

    def addPluginToMenu(self, name, action):
        self.menu.addAction(action)

    def removePluginMenu(self, name, action):
        self.menu.removeAction(action)

    def addToolBarIcon(self, action):
        self.toolbar.addAction(action)

    def removeToolBarIcon(self, action):
        self.toolbar.removeAction(action)


def run():
    iface, project = InterfaceHarness(), QgsProject()
    plugin = classFactory(iface)
    plugin.project = project
    with TemporaryDirectory(prefix="checkpoint-test-") as directory:
        plugin.root = Path(directory) / "history"
        first_path = str(Path(directory) / "first.qgz")
        try:
            plugin.initGui()
            panel = plugin.panel
            panel.mode.setCurrentText("Manual")
            layer = QgsVectorLayer("Point?crs=EPSG:4326", "Roads", "memory")
            project.addMapLayer(layer)
            iface.canvas.setDestinationCrs(layer.crs())
            iface.canvas.setExtent(QgsRectangle(0, 0, 10, 10))
            panel.save_button.click()
            assert len(plugin.store.records) == panel.history.count() == 1
            panel.save_button.click()
            assert len(plugin.store.records) == 1
            assert "No styling changes" in iface.bar.currentItem().text()
            assert not plugin.root.exists(), "Unsaved history was written to disk"

            panel.interval.setValue(1)
            panel.mode.setCurrentText("Auto")
            layer.setOpacity(0.5)
            QTest.qWait(2200)
            assert len(plugin.store.records) == panel.history.count() == 2
            iface.canvas.setExtent(QgsRectangle(20, 20, 30, 30))
            QTest.qWait(2200)
            assert len(plugin.store.records) == 2, "Panning created a checkpoint"

            project.setFileName(first_path)
            assert plugin.watcher is None and not panel.save_button.isEnabled()
            assert project.write()
            assert plugin.store.saved and plugin.store.path.exists()
            assert len(plugin.store.records) == 2
            assert panel.save_button.isEnabled()
            first_records = plugin.store.records

            second_path = str(Path(directory) / "second.qgz")
            project.setFileName(second_path)
            with patch.object(plugin, "_choose_save_as", return_value="new"):
                assert project.write()
            assert plugin.store.key == project_key(second_path)
            assert len(plugin.store.records) == 1  # New project starting point
            assert HistoryStore(plugin.root, first_path).records == first_records

            # An in-flight Auto save must not write into the next project.
            project.clear()
            assert plugin.watcher is None and plugin.store is None
            assert project.read(first_path)
            iface.projectRead.emit()
            QTest.qWait(2200)
            assert plugin.store.records == first_records
            assert len(plugin.watcher._layers) == len(project.mapLayers())

            project.clear()
            iface.newProjectCreated.emit()
            assert not plugin.store.saved and not plugin.store.records
            plugin.watcher.mark_dirty()
            plugin.unload()
            QTest.qWait(2200)
            assert not iface.toolbar.actions() and not iface.menu.actions()
            project.addMapLayer(QgsVectorLayer("Point", "After unload", "memory"))
            assert plugin.store is None
            print("Checkpoint plugin smoke checks passed", flush=True)
        finally:
            if not plugin._unloaded:
                plugin.unload()
            iface.canvas.stopRendering()
            iface.canvas.setLayers([])
            project.clear()
            iface.window.close()


if __name__ == "__main__":
    run()
