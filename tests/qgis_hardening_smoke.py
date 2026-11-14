"""Native regressions for paused sessions, transient failures and navigation cost."""
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsRectangle, QgsVectorLayer
from qgis.PyQt.QtTest import QTest

from checkpoint import classFactory
from checkpoint.core.snapshot import GROUP_ID, SnapshotError, capture

Harness = runpy.run_path(str(Path(__file__).with_name('qgis_plugin_smoke.py')))['InterfaceHarness']


def run():
    iface, project = Harness(), QgsProject()
    layer = QgsVectorLayer('Point?crs=EPSG:4326', 'Дороги 道路', 'memory')
    project.addMapLayer(layer)
    iface.canvas.setDestinationCrs(layer.crs())
    iface.canvas.setExtent(QgsRectangle(0, 0, 10, 10))
    plugin = classFactory(iface)
    plugin.project = project
    with TemporaryDirectory() as directory:
        root = Path(directory)
        plugin.root = root / 'История 历史 with spaces'
        project_path = str(root / 'Проект 地图 with spaces.qgz')
        project.setFileName(project_path)
        plugin.settings.setValue('checkpoint/previews', False)
        plugin.settings.setValue('checkpoint/restore_view', True)
        try:
            plugin.initGui()
            plugin.panel.mode.setCurrentText('Manual')
            plugin.panel.history.setCurrentRow(0)
            QTest.qWait(200)

            # Recover Apply after a temporary failure, without making a new save.
            with patch('checkpoint.plugin.capture', side_effect=SnapshotError('temporary failure')):
                plugin._update_details()
            assert not plugin.panel.restore_button.isEnabled()
            plugin._update_details()
            assert plugin.panel.restore_button.isEnabled()

            # The scope does not depend on the current center/zoom. Navigation
            # must not serialize every layer's style; CRS changes still refresh it.
            with patch('checkpoint.plugin.capture', wraps=capture) as spy:
                iface.canvas.setExtent(QgsRectangle(20, 20, 30, 30))
                iface.canvas.zoomScale(10000)
                QTest.qWait(250)
                assert spy.call_count == 0, spy.call_count
                iface.canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:3857'))
                QTest.qWait(250)
                assert spy.call_count == 1, spy.call_count
            assert 'transform saved center' in plugin.panel.details.toPlainText()

            # A queued details refresh or row click while Save As is paused must
            # not capture a partially loaded project or assign new group IDs.
            plugin._schedule_details()
            project.setFileName(str(root / 'Save As.qgz'))
            assert plugin.watcher is None and not plugin._details_timer.isActive()
            project.layerTreeRoot().removeCustomProperty(GROUP_ID)
            with patch('checkpoint.plugin.capture', wraps=capture) as spy:
                plugin._update_details()
                iface.canvas.setDestinationCrs(layer.crs())
                QTest.qWait(250)
                assert spy.call_count == 0
            assert not project.layerTreeRoot().customProperty(GROUP_ID, '')

            # Stored IDs must not be adopted before the runtime guard. The saved
            # history above exists and would otherwise tag the live project.
            project.setFileName(project_path)
            project.setDirty(False)
            with patch('checkpoint.core.snapshot.Qgis', SimpleNamespace(
                QGIS_VERSION_INT=40200, QGIS_VERSION='4.2.0-nightly'
            )):
                plugin._session_ready()
            assert plugin.store is None and plugin.watcher is None
            assert not plugin.panel.save_button.isEnabled()
            assert not project.layerTreeRoot().customProperty(GROUP_ID, '')
            assert not project.isDirty()

            # Returning to a supported runtime reopens the same Unicode-path history.
            plugin._session_ready()
            assert plugin.store.saved and plugin.store.has_records
            assert plugin.panel.save_button.isEnabled()
            print('Checkpoint session hardening checks passed', flush=True)
        finally:
            plugin.unload()
            iface.canvas.stopRendering()
            iface.canvas.setLayers([])
            project.clear()
            iface.window.close()


if __name__ == '__main__':
    run()
