"""Generate a real QGIS project and screenshots of native running Qt/QGIS widgets.

Run via run_qgis_checks.py --demo --only demo, inside its disposable QGIS profile.
This is an isolated iface harness, not a screenshot of the user's QGIS desktop.
"""
import json
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory

from qgis.core import (QgsProject, QgsVectorLayer, QgsRectangle, QgsLineSymbol, QgsFillSymbol,
                      QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
                      QgsVectorLayerSimpleLabeling, QgsLayerTreeModel)
from qgis.gui import QgsLayerTreeView, QgsLayerTreeMapCanvasBridge
from qgis.PyQt.QtGui import QColor, QFont
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QSplitter
from checkpoint import classFactory

ROOT = Path(__file__).resolve().parents[1]
Harness = runpy.run_path(str(ROOT / 'tests/qgis_plugin_smoke.py'))['InterfaceHarness']


def feature(geometry, **properties):
    return {'type': 'Feature', 'properties': properties, 'geometry': geometry}


def write_layer(path, features):
    path.write_text(json.dumps({'type': 'FeatureCollection', 'name': path.stem,
        'crs': {'type': 'name', 'properties': {'name': 'urn:ogc:def:crs:EPSG::3857'}},
        'features': features}, indent=2), encoding='utf-8')


def wait_render(canvas):
    canvas.refresh()
    for _ in range(250):
        QTest.qWait(20)
        if not canvas.isDrawing():
            QTest.qWait(100)
            return
    raise AssertionError('Demo render did not finish')


def run():
    output = ROOT / 'docs/images'
    output.mkdir(parents=True, exist_ok=True)
    demo = ROOT / 'demo'
    demo.mkdir(exist_ok=True)
    roads = []
    for name, coordinates in [
        ('Canal Street', [[80, 240], [1060, 240]]),
        ('Market Street', [[80, 560], [1060, 560]]),
        ('North Avenue', [[80, 880], [1060, 880]]),
        ('Cedar Road', [[290, 60], [290, 1060]]),
        ('Oak Road', [[730, 60], [730, 1060]]),
        ('River Walk', [[80, 80], [180, 180], [400, 340], [560, 510], [880, 760], [1060, 1040]]),
    ]:
        roads.append(feature({'type': 'LineString', 'coordinates': coordinates}, name=name))
    buildings = []
    for row, y in enumerate((95, 350, 670, 955)):
        for col, x in enumerate((110, 360, 530, 810, 950)):
            w, h = (90, 75) if col % 2 else (105, 90)
            buildings.append(feature({'type': 'Polygon', 'coordinates': [[[x,y],[x+w,y],[x+w,y+h],[x,y+h],[x,y]]]},
                                     name='Block ' + str(row*5+col+1), floors=1+(row+col)%5))
    write_layer(demo / 'roads.geojson', roads)
    write_layer(demo / 'buildings.geojson', buildings)
    project, iface = QgsProject(), Harness()
    project.setTitle('Checkpoint synthetic neighborhood')
    road = QgsVectorLayer(str(demo / 'roads.geojson'), 'Roads', 'ogr')
    building = QgsVectorLayer(str(demo / 'buildings.geojson'), 'Buildings', 'ogr')
    assert road.isValid() and building.isValid()
    project.addMapLayer(building); project.addMapLayer(road)
    road.renderer().setSymbol(QgsLineSymbol.createSimple({'line_color': '#315b77', 'line_width': '1.2'}))
    building.renderer().setSymbol(QgsFillSymbol.createSimple({'color': '#b9b4a0', 'outline_color': '#666457', 'outline_width': '.2'}))
    labels = QgsPalLayerSettings(); labels.fieldName = 'name'
    labels.placement = QgsPalLayerSettings.Placement.Line
    text = QgsTextFormat(); text.setFont(QFont('Arial', 10)); text.setSize(10); text.setColor(QColor('#33372f'))
    buffer = QgsTextBufferSettings(); buffer.setEnabled(True); buffer.setSize(.6); buffer.setColor(QColor('#e9e6dd'))
    text.setBuffer(buffer); labels.setFormat(text)
    road.setLabeling(QgsVectorLayerSimpleLabeling(labels)); road.setLabelsEnabled(True)
    canvas = iface.canvas
    canvas.setDestinationCrs(road.crs()); project.setCrs(road.crs())
    canvas.setCanvasColor(QColor('#e9e6dd'))
    splitter = QSplitter(iface.window)
    tree = QgsLayerTreeView(splitter)
    tree.setModel(QgsLayerTreeModel(project.layerTreeRoot(), tree))
    splitter.addWidget(tree); splitter.addWidget(canvas); splitter.setSizes([180, 900])
    iface.window.setCentralWidget(splitter)
    bridge = QgsLayerTreeMapCanvasBridge(project.layerTreeRoot(), canvas)
    bridge.setCanvasLayers()
    iface.window.setWindowTitle('Checkpoint 0.2.0 - QGIS runtime demonstration')
    iface.window.resize(1370, 940)
    iface.window.statusBar().showMessage('Synthetic neighborhood generated for this demo. Native QGIS widgets in an isolated test window.')
    canvas.setExtent(QgsRectangle(0, 0, 1160, 1120))
    project.setFileName(str(demo / 'checkpoint-demo.qgz'))
    # Persist the native view through QgsReferencedRectangle.
    from qgis.core import QgsReferencedRectangle
    project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(canvas.extent(), road.crs()))
    assert project.write()
    plugin = classFactory(iface); plugin.project = project
    with TemporaryDirectory(prefix='checkpoint-demo-history-') as history:
        plugin.root = Path(history)
        try:
            plugin.settings.setValue('checkpoint/previews', True)
            plugin.settings.setValue('checkpoint/restore_view', True)
            plugin.initGui(); panel = plugin.panel
            panel.mode.setCurrentIndex(1)
            iface.window.show()
            iface.window.resizeDocks([panel], [390], Qt.Orientation.Horizontal)
            wait_render(canvas)
            for _ in range(100):
                if plugin.preview_task is None:
                    break
                QTest.qWait(20)
            baseline = plugin.store.records[0]
            plugin.store.rename(baseline['id'], 'Blue roads and all buildings')
            road.renderer().setSymbol(QgsLineSymbol.createSimple({'line_color': '#a84c2f', 'line_width': '2'}))
            road.triggerRepaint()
            building.renderer().setSymbol(QgsFillSymbol.createSimple({'color': '#a9b18b', 'outline_color': '#535f41'}))
            assert building.setSubsetString('"floors" >= 3')
            panel.save_button.click()
            wait_render(canvas)
            for _ in range(100):
                if plugin.preview_task is None:
                    break
                QTest.qWait(20)
            for i in range(panel.history.count()):
                if panel.history.item(i).data(Qt.ItemDataRole.UserRole) == baseline['id']:
                    panel.history.setCurrentRow(i)
            QTest.qWait(200)
            iface.window.grab().save(str(output / 'history.png'))
            panel.grab().save(str(output / 'dock.png'))
            panel.restore_button.click(); wait_render(canvas)
            iface.window.grab().save(str(output / 'applied.png'))
            QTest.qWait(50)
            panel.undo_button.click(); wait_render(canvas)
            iface.window.grab().save(str(output / 'undo.png'))
            # Historical comparison of the deliberate two-layer edit.
            edited = next(r for r in plugin.store.records if r['description'].startswith('style:'))
            for i in range(panel.history.count()):
                if panel.history.item(i).data(Qt.ItemDataRole.UserRole) == edited['id']:
                    panel.history.setCurrentRow(i)
            panel.preview_button.click(); QTest.qWait(100)
            panel._dialog.grab().save(str(output / 'comparison.png'))
            panel._dialog.close(); QTest.qWait(50)
            qa = ROOT / 'dist/qa'
            qa.mkdir(parents=True, exist_ok=True)
            plugin.store.rename(edited['id'], 'Very long building and road layer presentation checkpoint ' * 8)
            plugin._refresh()
            iface.window.resizeDocks([panel], [360], Qt.Orientation.Horizontal)
            QTest.qWait(100)
            panel.grab().save(str(qa / 'long-name.png'))
            panel.previews.setChecked(False)
            road.setOpacity(.7)
            panel.save_button.click()
            panel.history.setCurrentRow(0)
            panel.preview_button.click()
            QTest.qWait(50)
            panel._dialog.grab().save(str(qa / 'maps-off.png'))
            panel._dialog.close()
            project.clear(); iface.newProjectCreated.emit()
            QTest.qWait(100)
            panel.grab().save(str(qa / 'empty.png'))
            print('Demo project:', demo / 'checkpoint-demo.qgz', flush=True)
            print('Real QGIS widget screenshots:', output, flush=True)
        finally:
            plugin.unload(); canvas.stopRendering(); canvas.setLayers([])
            project.clear(); iface.window.close()


run()
