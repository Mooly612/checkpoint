"""Real QGIS preview rendering, lifecycle, provider isolation, and deterministic fuse checks."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import runpy
import os

from qgis.core import (QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
                       QgsRectangle, QgsMarkerSymbol, QgsCategorizedSymbolRenderer,
                       QgsRendererCategory, QgsPalLayerSettings, QgsVectorLayerSimpleLabeling,
                       QgsLineSymbol, QgsFillSymbol)
from qgis.PyQt.QtCore import QObject, pyqtSignal, Qt
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QLabel

from checkpoint import classFactory
from checkpoint.core.snapshot import capture
from checkpoint.core.store import HistoryStore
from checkpoint.core.thumbnail import PreviewTask, _RUNNING
from checkpoint.ui.preview import pixmap

InterfaceHarness = runpy.run_path(str(Path(__file__).with_name("qgis_plugin_smoke.py")))["InterfaceHarness"]


def wait_for(predicate, timeout=4000):
    for _ in range(timeout // 20):
        if predicate():
            return
        QTest.qWait(20)
    raise AssertionError("Timed out waiting for preview")


def preview(project, canvas, before, after):
    results = []
    task = PreviewTask(project, canvas, before, after, results.append)
    task.start()
    wait_for(lambda: bool(results))
    result = results[0]
    assert result["status"] == "Saved preview", result
    return result


class StalledJob(QObject):
    finished = pyqtSignal()
    instances = []

    def __init__(self, config):
        super().__init__()
        self.active, self.cancelled = False, False
        self.instances.append(self)

    def start(self):
        self.active = True

    def isActive(self):
        return self.active

    def cancelWithoutBlocking(self):
        self.cancelled = True
        # Keep running until the test explicitly acknowledges completion.

    def finish(self):
        self.active = False
        self.finished.emit()


def run():
    iface, project = InterfaceHarness(), QgsProject()
    plugin = classFactory(iface)
    plugin.project = project
    with TemporaryDirectory(prefix="checkpoint-preview-") as directory:
        plugin.root = Path(directory) / "history"
        try:
            plugin.initGui()
            panel = plugin.panel
            panel.mode.setCurrentText("Manual")
            panel.previews.setChecked(True)
            plugin.settings.remove("checkpoint/heavy/" + plugin.store.key)
            layer = QgsVectorLayer("Point?crs=EPSG:4326&field=kind:integer", "Sparse points", "memory")
            feature = QgsFeature(layer.fields())
            feature.setAttributes([1])
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(10, 20)))
            layer.dataProvider().addFeatures([feature])
            layer.updateExtents()
            project.addMapLayer(layer)
            iface.canvas.setDestinationCrs(layer.crs())
            iface.canvas.setExtent(QgsRectangle(-180, -80, 180, 80))
            layer.renderer().setSymbol(QgsMarkerSymbol.createSimple({"name": "circle", "color": "red", "size": "3"}))
            before = capture(project, iface.canvas)
            layer.renderer().setSymbol(QgsMarkerSymbol.createSimple({"name": "square", "color": "blue", "size": "5"}))
            after = capture(project, iface.canvas)
            result = preview(project, iface.canvas, before, after)
            assert result["maps"]["before"] != result["maps"]["after"]
            assert result["samples"][0]["before"] != result["samples"][0]["after"]
            assert result["extent"][2] - result["extent"][0] < 2
            assert "Sparse points" in result["note"]
            assert capture(project, iface.canvas) == after, "Preview modified live state"
            assert pixmap(result["maps"]["after"]).width() == 400

            # Samples are bounded; the note explicitly discloses uninspected categories.
            def categories(colors):
                return QgsCategorizedSymbolRenderer("kind", [QgsRendererCategory(i,
                    QgsMarkerSymbol.createSimple({"color": color}), f"Category {i}")
                    for i, color in enumerate(colors)])
            layer.setRenderer(categories(["red"] * 4))
            before = capture(project, iface.canvas)
            layer.setRenderer(categories(["blue"] * 4))
            after = capture(project, iface.canvas)
            result = preview(project, iface.canvas, before, after)
            assert len(result["samples"]) == 2 and result["more"] == 0
            assert "Other changes may exist" in result["note"]
            layer.setRenderer(categories(["blue", "green", "blue", "blue"]))
            one = preview(project, iface.canvas, after, capture(project, iface.canvas))
            assert len(one["samples"]) == 1 and "Category 1" in one["samples"][0]["label"]

            before = capture(project, iface.canvas)
            layer.setSubsetString('"kind" = 999')
            after = capture(project, iface.canvas)
            filtered = preview(project, iface.canvas, before, after)
            assert not filtered["samples"] and "filter:" in filtered["summary"]
            assert filtered["maps"]["before"] != filtered["maps"]["after"]
            layer.setSubsetString("")
            before = capture(project, iface.canvas)
            project.layerTreeRoot().findLayer(layer.id()).setItemVisibilityChecked(False)
            after = capture(project, iface.canvas)
            hidden = preview(project, iface.canvas, before, after)
            assert not hidden["samples"] and "visible → hidden" in hidden["note"]
            assert hidden["maps"]["before"] != hidden["maps"]["after"]
            project.layerTreeRoot().findLayer(layer.id()).setItemVisibilityChecked(True)

            # Label-only changes use context, not identical symbol samples.
            before = capture(project, iface.canvas)
            label_settings = QgsPalLayerSettings()
            label_settings.fieldName = "kind"
            layer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))
            layer.setLabelsEnabled(True)
            label_result = preview(project, iface.canvas, before, capture(project, iface.canvas))
            assert not label_result["samples"] and "style:" in label_result["summary"]

            # Multiple changed layers and QGIS-native line/polygon samples.
            line = QgsVectorLayer("LineString?crs=EPSG:4326", "Route", "memory")
            area = QgsVectorLayer("Polygon?crs=EPSG:4326", "Area", "memory")
            project.addMapLayer(line)
            project.addMapLayer(area)
            before = capture(project, iface.canvas)
            line.renderer().setSymbol(QgsLineSymbol.createSimple({"line_color": "red", "line_width": "1"}))
            area.renderer().setSymbol(QgsFillSymbol.createSimple({"color": "green"}))
            multi = preview(project, iface.canvas, before, capture(project, iface.canvas))
            assert set(multi["affected"]) == {"Route", "Area"}
            assert len(multi["samples"]) == 2
            before = capture(project, iface.canvas)
            node = project.layerTreeRoot().findLayer(line.id())
            project.layerTreeRoot().insertChildNode(0, node.clone())
            project.layerTreeRoot().removeChildNode(node)
            order = preview(project, iface.canvas, before, capture(project, iface.canvas))
            assert "layer order" in order["summary"] and not order["samples"]
            project.removeMapLayer(line.id())
            project.removeMapLayer(area.id())

            # Artifacts survive migration and predecessor eviction, never rerender on click.
            plugin.store.set_limit(1)
            panel.save_button.click()
            panel._open_preview(panel.history.item(0))
            wait_for(lambda: plugin.preview_task is None)
            assert any("Saved preview" in label.text() for label in panel._dialog.findChildren(QLabel))
            panel._dialog.close()
            QTest.qWait(20)
            layer.setOpacity(0.5)
            panel.save_button.click()
            wait_for(lambda: plugin.preview_task is None)
            record = plugin.store.records[-1]
            assert record["preview"]["maps"] and len(plugin.store.records) == 1
            project.setFileName(str(Path(directory) / "map.qgz"))
            assert project.write()
            assert HistoryStore(plugin.root, project.fileName()).records == plugin.store.records
            # Optional images for developer visual inspection, outside the repository.
            if os.environ.get("CHECKPOINT_SCREENSHOTS"):
                output = Path(os.environ["CHECKPOINT_SCREENSHOTS"])
                output.mkdir(parents=True, exist_ok=True)
                iface.window.resize(640, 660)
                iface.window.show()
                QTest.qWait(30)
                panel.grab().save(str(output / "preview-panel.png"))
                panel._open_preview(panel.history.item(0))
                QTest.qWait(30)
                panel._dialog.grab().save(str(output / "preview-dialog.png"))
                panel._dialog.close()
                QTest.qWait(20)
            saved_preview = deepcopy(record["preview"])
            layer.setOpacity(0.8)
            with patch("checkpoint.core.thumbnail.QgsMapRendererParallelJob", side_effect=AssertionError("Unexpected render")):
                panel._open_preview(panel.history.item(0))
                assert panel._dialog is not None
                panel._dialog.close()
                QTest.qWait(20)
            assert plugin.store.records[-1]["preview"] == saved_preview

            # Off disables expensive maps; lightweight samples/details remain.
            panel.previews.setChecked(False)
            with patch("checkpoint.core.thumbnail.QgsMapRendererParallelJob", side_effect=AssertionError("Map render while disabled")):
                panel.save_button.click()
                assert not plugin.store.records[-1]["preview"]["maps"]
                assert plugin.store.records[-1]["preview"]["samples"]
                panel.history.setCurrentRow(0)
                panel.restore_button.click()
                assert not plugin.store.records[-1]["preview"]["maps"]
                assert plugin.store.records[-1]["preview"]["summary"]
            panel.previews.setChecked(True)
            panel._open_preview(panel.history.item(0))  # An old/missing artifact stays unavailable.
            assert panel._dialog is not None
            panel._dialog.close()
            QTest.qWait(20)

            # Exercise real timer timeout with deliberately stalled jobs.
            with patch("checkpoint.core.thumbnail.QgsMapRendererParallelJob", StalledJob):
                layer.setOpacity(0.3)
                panel.save_button.click()
                task = plugin.preview_task
                wait_for(lambda: plugin.preview_task is None, 3000)
                assert plugin.settings.value("checkpoint/heavy/" + plugin.store.key, False, type=bool)
                assert "paused after a slow render" in panel.preview_status.text()
                assert task in _RUNNING and task.layers, "Cancelled jobs lost their layers too early"
                assert all(j.cancelled for j in StalledJob.instances)
                for job in StalledJob.instances:
                    job.finish()
                assert task not in _RUNNING
                layer.setOpacity(0.2)
                panel.save_button.click()
                assert not plugin.store.records[-1]["preview"]["maps"]
            panel.retry_button.click()
            wait_for(lambda: plugin.preview_task is None)
            assert not plugin.settings.value("checkpoint/heavy/" + plugin.store.key, False, type=bool)

            # Closing a project/unloading cancels without waiting and discards callbacks.
            StalledJob.instances.clear()
            with patch("checkpoint.core.thumbnail.QgsMapRendererParallelJob", StalledJob):
                layer.setOpacity(0.1)
                panel.save_button.click()
                task = plugin.preview_task
                project.clear()
                assert plugin.store is None and plugin.preview_task is None
                assert task in _RUNNING
                plugin.unload()
                for job in StalledJob.instances:
                    job.finish()
                assert task not in _RUNNING
            print("Checkpoint thumbnail smoke checks passed", flush=True)
        finally:
            if not plugin._unloaded:
                plugin.unload()
            iface.canvas.stopRendering()
            iface.canvas.setLayers([])
            project.clear()
            iface.window.close()


run()
