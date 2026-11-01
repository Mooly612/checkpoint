from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import runpy
from qgis.core import QgsProject, QgsVectorLayer
from qgis.PyQt.QtWidgets import QMessageBox
from checkpoint import classFactory
Harness = runpy.run_path(str(Path(__file__).with_name('qgis_plugin_smoke.py')))['InterfaceHarness']
iface = Harness()
plugin = classFactory(iface)
plugin.project = QgsProject()
with TemporaryDirectory() as directory:
    plugin.root = Path(directory)
    plugin.initGui()
    try:
        page = iface.factory.createWidget(iface.window)
        page.previews.setChecked(False)
        page.limit.setValue(3)
        page.interval.setValue(17)
        page.view.setChecked(False)
        page.apply()
        assert plugin.store.limit == 3 and plugin.panel.interval.value() == 17
        assert not plugin.panel.previews.isChecked()
        assert not plugin.settings.value('checkpoint/restore_view', True, type=bool)
        plugin.project.addMapLayer(QgsVectorLayer('Point','Test','memory'))
        plugin.panel.save_button.click()
        plugin.panel.history.setCurrentRow(0)
        plugin.panel.pin_button.click()
        assert plugin.store.records[0]['pinned']
        with patch('checkpoint.plugin.QInputDialog.getText', return_value=('Named', True)):
            plugin.panel.rename_button.click()
        assert plugin.store.records[0]['name'] == 'Named'
        with patch('checkpoint.plugin.QMessageBox.question', return_value=QMessageBox.StandardButton.No):
            plugin.panel.delete_button.click()
        assert len(plugin.store.records) == 1
        with patch('checkpoint.plugin.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
            plugin.panel.delete_button.click()
        assert not plugin.store.records
        page.limit.setValue(20)
        page.interval.setValue(60)
        page.view.setChecked(True)
        page.apply()
        print('Checkpoint settings smoke checks passed', flush=True)
    finally:
        plugin.unload()
        assert iface.factory is None
        plugin.project.clear()
        iface.window.close()
