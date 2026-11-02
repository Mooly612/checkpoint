from pathlib import Path
from tempfile import TemporaryDirectory
import runpy
from qgis.core import QgsProject, QgsVectorLayer, QgsRectangle
from qgis.PyQt.QtTest import QTest
from checkpoint import classFactory
root = Path(__file__).resolve().parents[1]
Harness = runpy.run_path(str(root / 'tests/qgis_plugin_smoke.py'))['InterfaceHarness']
def run():
    iface, project = Harness(), QgsProject()
    layer = QgsVectorLayer('Point?crs=EPSG:4326', 'Probe', 'memory')
    project.addMapLayer(layer)
    iface.canvas.setDestinationCrs(layer.crs())
    iface.canvas.setExtent(QgsRectangle(0,0,10,10))
    plugin = classFactory(iface)
    plugin.project = project
    with TemporaryDirectory() as directory:
        plugin.root = Path(directory)
        try:
            plugin.settings.setValue("checkpoint/previews", False)
            plugin.initGui()
            plugin.panel.mode.setCurrentText('Manual')
            plugin.panel.previews.setChecked(False)
            first = plugin.store.records[0]['id']
            layer.setOpacity(.2)
            plugin._apply(first)
            QTest.qWait(50)
            values = [layer.opacity()]
            for _ in range(3):
                plugin.panel.undo_button.click()
                QTest.qWait(50)
                values.append(layer.opacity())
            assert values == [1.0, .2, .2, .2]
            assert not plugin.panel.undo_button.isEnabled()
            # Custom properties are captured/restored, but do changes trigger Auto?
            group = project.layerTreeRoot().addGroup('Probe group')
            plugin.panel.save_button.click()
            QTest.qWait(50)
            plugin.panel.interval.setValue(1)
            plugin.panel.mode.setCurrentText('Auto')
            count = len(plugin.store.records)
            group.setCustomProperty('probe/value', 'changed')
            QTest.qWait(2300)
            assert len(plugin.store.records) == count + 1
            print('Checkpoint shutdown reproduction passed', flush=True)
        finally:
            plugin.unload()
            iface.canvas.stopRendering()
            iface.canvas.setLayers([])
            project.clear()
            iface.window.close()

run()
