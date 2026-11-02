"""Audit regressions against real group/CRS/Qt properties, not snapshot hashes."""
from copy import deepcopy
import math
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsGroupLayer,
    QgsProject, QgsRectangle, QgsVectorLayer)
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtTest import QTest

from checkpoint import classFactory
from checkpoint.core.snapshot import GROUP_ID, SnapshotError, adopt_tree_identity, capture, restore
from checkpoint.core.store import HistoryStore

Harness = runpy.run_path(str(Path(__file__).with_name('qgis_plugin_smoke.py')))['InterfaceHarness']


def run():
    p, c = QgsProject(), QgsMapCanvas()
    c.resize(640, 480)
    c.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
    c.setExtent(QgsRectangle(9, 19, 11, 21))
    root = p.layerTreeRoot()
    one, two = root.addGroup('Same'), root.addGroup('Same')
    nested = one.addGroup('Nested')
    roads = QgsVectorLayer('Point?crs=EPSG:4326', 'Roads', 'memory')
    buildings = QgsVectorLayer('Point?crs=EPSG:4326', 'Buildings', 'memory')
    p.addMapLayer(roads, False); p.addMapLayer(buildings, False)
    one.addLayer(roads); two.addLayer(buildings)
    one.setCustomProperty('plugin/data', {'list': [1, 2], 'number': 3})
    one.setCustomProperty('plugin/color', QColor('#a23928'))
    root.setName('Root snapshot name')
    root.setCustomProperty('root/property', 'kept')
    one.serverProperties().setTitle('Saved group title')
    one.setHasWmsTimeDimension(True)
    root.serverProperties().setAbstract('Saved root description')
    root.setHasWmsTimeDimension(True)
    one.setIsMutuallyExclusive(True, 1)
    one.setExpanded(False)
    original = capture(p, c)
    identity = one.customProperty(GROUP_ID)
    one.serverProperties().setTitle('Changed group title')
    one.setHasWmsTimeDimension(False)
    root.setName('Changed root name')
    root.serverProperties().setAbstract('Changed root description')
    root.setHasWmsTimeDimension(False)
    try:
        assert restore(p, c, original) == []
        one, two = root.children()
        assert one.isMutuallyExclusive() and one.children()[1].itemVisibilityChecked()
        assert not one.children()[0].itemVisibilityChecked() and not one.isExpanded()
        assert one.customProperty('plugin/data') == {'list': [1, 2], 'number': 3}
        assert one.customProperty('plugin/color') == QColor('#a23928')
        assert root.name() == 'Root snapshot name'
        assert root.customProperty('root/property') == 'kept'
        assert one.serverProperties().title() == 'Saved group title'
        assert one.hasWmsTimeDimension()
        assert root.serverProperties().abstract() == 'Saved root description'
        assert root.hasWmsTimeDimension()
        for node in [root, *root.findGroups(True)]:
            node.removeCustomProperty(GROUP_ID)
        adopt_tree_identity(root, original['tree'])
        assert one.customProperty(GROUP_ID) == identity
        assert root.customProperty(GROUP_ID) == original['tree']['id']
        one.setName('Renamed')
        one.setCustomProperty('introduced/later', 12)
        one.setCustomProperty('plugin/data', 'changed')
        later = QgsVectorLayer('Point', 'Later', 'memory')
        p.addMapLayer(later, False)
        one.insertLayer(0, later)
        one.setIsMutuallyExclusive(False)
        mutated = capture(p, c)
        restore(p, c, original)
        QgsApplication.processEvents()
        matched = [g for g in root.findGroups(True) if g.customProperty(GROUP_ID) == identity][0]
        assert matched.name() == 'Same' and matched.isMutuallyExclusive()
        assert matched.customProperty('introduced/later') == 12
        assert root.findLayer(later.id()).parent() == matched
        assert p.mapLayer(later.id()) is later
        assert matched.customProperty('plugin/data')['number'] == 3
        restore(p, c, mutated)
        matched = [g for g in root.findGroups(True) if g.customProperty(GROUP_ID) == identity][0]
        assert matched.name() == 'Renamed' and not matched.isMutuallyExclusive()
        assert matched.customProperty('plugin/data') == 'changed'

        # Metadata and runtime guards agree; unsupported environments fail before mutation.
        for namespace, replacement in (
            ('checkpoint.core.snapshot.Qgis', SimpleNamespace(QGIS_VERSION_INT=34000)),
            ('checkpoint.core.snapshot.Qgis', SimpleNamespace(QGIS_VERSION_INT=40000)),
            ('checkpoint.core.snapshot.QT_VERSION_STR', '6.8.0'),
        ):
            roads.setOpacity(.42)
            p.setDirty(False)
            with patch(namespace, replacement):
                try:
                    restore(p, c, original)
                except SnapshotError as exc:
                    assert 'requires QGIS 3.44' in str(exc)
                else:
                    raise AssertionError('Unsupported runtime was allowed to apply styling')
            assert roads.opacity() == .42 and not p.isDirty()

        # Old records remain usable for styles, but never erase current metadata.
        legacy = deepcopy(original); legacy.pop('schema'); legacy.pop('view_crs')
        roads.setOpacity(.2)
        notices = restore(p, c, legacy)
        assert roads.opacity() == 1
        assert any('Legacy checkpoint' in n for n in notices)
        assert any('CRS is unknown' in n for n in notices)
        assert matched.customProperty('plugin/data') == 'changed'

        c.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:3857'))
        restore(p, c, original)
        assert math.isclose(c.center().x(), 1113194.9079, abs_tol=.1)
        assert math.isclose(c.center().y(), 2273030.9270, abs_tol=.1)
        assert math.isclose(c.scale(), original['scale'], rel_tol=1e-6)
        assert c.mapSettings().destinationCrs().authid() == 'EPSG:3857'
        c.resize(1000, 400)
        restore(p, c, original)
        assert math.isclose(c.scale(), original['scale'], rel_tol=1e-6)
        assert math.isclose(c.center().x(), 1113194.9079, abs_tol=.1)
        view = capture(p, c)
        roads.setOpacity(.3)
        with patch('checkpoint.core.snapshot.QgsCoordinateTransform', side_effect=RuntimeError('transform failed')):
            notices = restore(p, c, original)
        assert roads.opacity() == 1 and any('transform failed' in n for n in notices)
        assert capture(p, c)['extent'] == view['extent']
        with patch('checkpoint.core.snapshot.QgsCoordinateTransform', side_effect=AssertionError('disabled view transformed')):
            restore(p, c, original, restore_view=False)
        assert capture(p, c)['extent'] == view['extent']
        invalid = deepcopy(original); invalid['view_crs'] = 'not a CRS'
        assert any('invalid CRS' in n for n in restore(p, c, invalid))

        rejected = deepcopy(original)
        rejected['layers'][roads.id()]['filter'] = '('
        roads.setOpacity(.4)
        notices = restore(p, c, rejected, restore_view=False)
        assert roads.opacity() == 1 and any('provider rejected' in n for n in notices)

        # Later-only mutually exclusive groups preserve the selected child.
        extra_group = root.addGroup('Later exclusive')
        later_one = QgsVectorLayer('Point', 'Later one', 'memory')
        later_two = QgsVectorLayer('Point', 'Later two', 'memory')
        p.addMapLayer(later_one, False); p.addMapLayer(later_two, False)
        extra_group.addLayer(later_one); extra_group.addLayer(later_two)
        extra_group.setIsMutuallyExclusive(True, 1)
        extra_group.setCustomProperty('extra', 99)
        capture(p, c)  # Assign persistent group identity.
        restore(p, c, original, restore_view=False)
        extra_group = root.findGroup('Later exclusive')
        assert extra_group.isMutuallyExclusive() and extra_group.customProperty('extra') == 99
        assert not extra_group.children()[0].itemVisibilityChecked()
        assert extra_group.children()[1].itemVisibilityChecked()

        # Reject linked group layers before changing any style or project flags.
        group = root.addGroup('Rendered group')
        group_layer = group.convertToGroupLayer(QgsGroupLayer.LayerOptions(p.transformContext()))
        p.addMapLayer(group_layer, False)
        roads.setOpacity(.25)
        p.setDirty(False)
        try:
            restore(p, c, original)
            raise AssertionError('Group layer accepted')
        except SnapshotError:
            pass
        assert roads.opacity() == .25 and not p.isDirty()
    finally:
        c.stopRendering(); c.setLayers([]); p.clear(); c.close()

    # Enable in an open project, then inspect selection and failed startup saves.
    for fail in (False, True):
        iface, project = Harness(), QgsProject()
        layer = QgsVectorLayer('Point?crs=EPSG:4326', 'Long road layer ' * 12, 'memory')
        project.addMapLayer(layer)
        iface.canvas.setDestinationCrs(layer.crs())
        iface.canvas.setExtent(QgsRectangle(0, 0, 10, 10))
        plugin = classFactory(iface); plugin.project = project
        with TemporaryDirectory() as directory:
            plugin.root = Path(directory)
            try:
                if fail:
                    with patch.object(HistoryStore, '_commit', side_effect=OSError('initial disk full')):
                        plugin.initGui()
                    assert not plugin.store.records
                    assert 'Saving unavailable' in plugin.panel.status.text()
                    assert 'Auto history active' not in plugin.panel.status.text()
                    plugin.panel.save_button.click()
                else:
                    plugin.initGui()
                assert len(plugin.store.records) == 1
                first = plugin.store.records[0]
                assert 'Auto history active' in plugin.panel.status.text()
                plugin._initial_checkpoint()
                assert len(plugin.store.records) == 1
                layer.setOpacity(.2)
                plugin.panel.history.setCurrentRow(0)
                assert plugin.panel._dialog is None and layer.opacity() == .2
                assert 'style / labels' in plugin.panel.details.toPlainText()
                plugin.panel.restore_button.click()
                assert layer.opacity() == 1
                assert plugin.panel.undo_button.isEnabled()
                QTest.qWait(30)
                plugin.panel.undo_button.click()
                assert layer.opacity() == .2
                assert any(r['id'] == first['id'] for r in plugin.store.records)
                plugin.panel.history.setCurrentRow(0)
                plugin.panel.pin_button.click()
                assert plugin.panel.pin_button.text() == 'Unpin'
                selected = plugin.panel.selected_id()
                plugin.panel.history.setFocus()
                QTest.keyClick(plugin.panel.history, Qt.Key.Key_Down)
                assert plugin.panel.selected_id() != selected
                assert plugin.panel._dialog is None and layer.opacity() == .2
            finally:
                plugin.unload(); iface.canvas.stopRendering(); project.clear(); iface.window.close()
    print('Checkpoint audit regression checks passed', flush=True)


run()
