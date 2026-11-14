"""Single-level Undo, propagated group signals and metadata capture counts."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import runpy
from qgis.core import QgsProject, QgsVectorLayer, QgsRectangle
from qgis.PyQt.QtTest import QTest
from checkpoint import classFactory
from checkpoint.core.snapshot import capture
Harness = runpy.run_path(str(Path(__file__).with_name('qgis_plugin_smoke.py')))['InterfaceHarness']

def run():
    iface, project = Harness(), QgsProject()
    layer=QgsVectorLayer('Point?crs=EPSG:4326','Points','memory')
    project.addMapLayer(layer)
    iface.canvas.setDestinationCrs(layer.crs()); iface.canvas.setExtent(QgsRectangle(0,0,10,10))
    plugin=classFactory(iface); plugin.project=project
    with TemporaryDirectory() as directory:
        plugin.root=Path(directory)
        plugin.settings.setValue('checkpoint/previews',False)
        try:
            plugin.initGui(); plugin.panel.mode.setCurrentText('Manual')
            first=plugin.store.records[0]['id']
            layer.setOpacity(.2); plugin._apply(first); QTest.qWait(50)
            layer.setOpacity(.6) # Manual edits must be protected by Undo's safety.
            plugin._undo(); QTest.qWait(50)
            assert layer.opacity()==.2 and not plugin.panel.undo_button.isEnabled()
            count=len(plugin.store.records); plugin._undo()
            assert len(plugin.store.records)==count
            assert any(r.get('operation')=='undo' and '0.6' in r['state']['layers'][layer.id()]['style'] for r in plugin.store.records)
            layer.setOpacity(.3); plugin._apply(first); QTest.qWait(50)
            layer.setOpacity(.4); plugin._apply(first); QTest.qWait(50)
            plugin._undo(); QTest.qWait(50); assert layer.opacity()==.4
            plugin._apply(first); QTest.qWait(50)
            undo_id = plugin.store.undo_target()
            with patch.object(plugin.store, 'append_restore', side_effect=OSError('Safety unavailable')):
                plugin._undo()
            assert plugin.store.undo_target() == undo_id and layer.opacity() == 1.0
            def partial(*args, **kwargs):
                layer.setOpacity(.7)
                return ['Provider rejected a filter']
            with patch('checkpoint.plugin.restore', side_effect=partial):
                plugin._undo()
            QTest.qWait(50)
            assert plugin.store.undo_target() == undo_id and plugin.panel.undo_button.isEnabled()
            original_append = plugin.store.append_restore
            def fail_result(*args, **kwargs):
                if not kwargs.get('before'):
                    raise OSError('Undo result unavailable')
                return original_append(*args, **kwargs)
            with patch.object(plugin.store, 'append_restore', side_effect=fail_result):
                plugin._undo()
            QTest.qWait(50)
            assert plugin.store.undo_target() == undo_id
            plugin._undo(); QTest.qWait(50)
            assert plugin.store.undo_target() is None
            plugin.panel.history.setCurrentRow(0); QTest.qWait(200)
            with patch('checkpoint.plugin.capture', wraps=capture) as spy:
                plugin.store.rename(first,'Renamed'); plugin._refresh()
                plugin.store.set_pinned(first,True); plugin._refresh()
                assert spy.call_count==0, spy.call_count
            group=project.layerTreeRoot().addGroup('Group'); plugin._manual_save()
            plugin.panel.interval.setValue(1); plugin.panel.mode.setCurrentText('Auto')
            count=len(plugin.store.records)
            group.setCustomProperty('probe/value','a'); group.setCustomProperty('probe/value','b')
            QTest.qWait(2300); assert len(plugin.store.records)==count+1
            count=len(plugin.store.records)
            group.setExpanded(False); capture(project,iface.canvas)
            QTest.qWait(2300); assert len(plugin.store.records)==count
            project.layerTreeRoot().removeChildNode(group)
            plugin._apply(first); QTest.qWait(50)
            assert plugin.watcher._suppression==0
            print('Checkpoint followup checks passed',flush=True)
        finally:
            plugin.unload(); iface.canvas.stopRendering(); iface.canvas.setLayers([])
            project.clear(); iface.window.close()
run()
