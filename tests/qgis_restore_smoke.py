"""Exercise Restore through actual Qt buttons, including storage failures."""

import math
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import runpy

from qgis.core import QgsProject, QgsRectangle, QgsVectorLayer, QgsCoordinateReferenceSystem
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtTest import QTest

from checkpoint import classFactory
from checkpoint.core.snapshot import capture
from checkpoint.core.store import HistoryStore

InterfaceHarness = runpy.run_path(str(Path(__file__).with_name("qgis_plugin_smoke.py")))["InterfaceHarness"]


def select(panel, record):
    for index in range(panel.history.count()):
        item = panel.history.item(index)
        if item.data(Qt.ItemDataRole.UserRole) == record["id"]:
            panel.history.setCurrentItem(item)
            return
    raise AssertionError("Record missing from history")


def run():
    iface, project = InterfaceHarness(), QgsProject()
    plugin = classFactory(iface)
    plugin.project = project
    with TemporaryDirectory(prefix="checkpoint-restore-") as directory:
        plugin.root = Path(directory) / "history"
        try:
            iface.canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
            plugin.initGui()
            panel = plugin.panel
            panel.previews.setChecked(False)
            assert not panel.restore_button.isEnabled()
            panel.mode.setCurrentText("Manual")
            layer = QgsVectorLayer("Point?crs=EPSG:4326", "Points", "memory")
            project.addMapLayer(layer)
            iface.canvas.setExtent(QgsRectangle(0, 0, 10, 10))
            panel.save_button.click()
            target = plugin.store.records[-1]
            select(panel, target)
            assert panel.restore_button.isEnabled()
            assert layer.opacity() == 1.0  # Selecting alone does not restore.
            layer.setOpacity(0.4)
            iface.canvas.setExtent(QgsRectangle(20, 20, 30, 30))
            before = capture(project, iface.canvas)
            panel.interval.setValue(1)
            panel.mode.setCurrentText("Auto")
            panel.restore_button.click()
            assert layer.opacity() == 1.0
            safety = next(r for r in plugin.store.records if r.get("kind") == "recovery")
            assert not safety["pinned"] and safety["state"] == before
            assert not plugin.store.records[-1]["pinned"]
            assert "Applied" in plugin.store.records[-1]["description"]
            assert plugin.store.records[0]["state"] == target["state"]
            count = len(plugin.store.records)
            QTest.qWait(2300)
            assert len(plugin.store.records) == count, "Restore signals created an Auto entry"
            panel.undo_button.click()
            assert layer.opacity() == 0.4
            restored_view = capture(project, iface.canvas)
            assert math.isclose(restored_view["scale"], before["scale"], rel_tol=1e-6)
            assert all(math.isclose(a, b, abs_tol=1e-6) for a, b in zip(
                restored_view["extent"], before["extent"]))
            QTest.qWait(50)

            # An unchanged restore still records two events. Manual stays deduplicated.
            select(panel, plugin.store.records[-1])
            count = len(plugin.store.records)
            panel.restore_button.click()
            assert len(plugin.store.records) == count + 2
            panel.save_button.click()
            assert len(plugin.store.records) == count + 2
            QTest.qWait(50)

            # Saved histories must persist safety before touching the map.
            project.setFileName(str(Path(directory) / "map.qgz"))
            assert project.write()
            select(panel, target)
            old = plugin.store.records
            with patch.object(plugin.store, "_commit", side_effect=OSError("Disk full")):
                panel.restore_button.click()
            assert layer.opacity() == 0.4 and plugin.store.records == old
            assert "Disk full" in iface.bar.currentItem().text()

            # Failure of the second commit must leave the persisted safety usable.
            commit = plugin.store._commit
            writes = []

            def fail_result(records):
                writes.append(records)
                if len(writes) == 2:
                    raise OSError("Result disk full")
                commit(records)

            with patch.object(plugin.store, "_commit", side_effect=fail_result):
                panel.restore_button.click()
            assert layer.opacity() == 1.0
            assert plugin.store.records[-1]["kind"] == "recovery"
            assert "result could not be recorded" in iface.bar.currentItem().title()
            assert HistoryStore(plugin.root, project.fileName()).records == plugin.store.records
            QTest.qWait(50)
            select(panel, plugin.store.records[-1])
            panel.restore_button.click()
            assert layer.opacity() == 0.4
            QTest.qWait(50)
            select(panel, target)

            # On partial application, retain the safety entry and release the guard.
            def partial_failure(*args, **kwargs):
                layer.setOpacity(0.2)
                raise RuntimeError("Provider failed")

            with patch("checkpoint.plugin.restore", side_effect=partial_failure):
                panel.restore_button.click()
            assert any(r.get("kind") == "recovery" and r["state"]["layers"][layer.id()]["style"] == before["layers"][layer.id()]["style"] for r in plugin.store.records)
            assert "Provider failed" in iface.bar.currentItem().text()
            QTest.qWait(50)
            assert plugin.watcher._suppression == 0 and not plugin._busy
            assert panel.restore_button.isEnabled()

            # Missing IDs are reported; newly added layers remain intact.
            extra = QgsVectorLayer("Point", "Later layer", "memory")
            project.addMapLayer(extra)
            extra.setOpacity(0.7)
            project.removeMapLayer(layer.id())
            select(panel, target)
            panel.restore_button.click()
            assert "not restored: layer Points (deleted)" in iface.bar.currentItem().text()
            assert extra.opacity() == 0.7
            QTest.qWait(2300)
            assert project.mapLayer(extra.id()) is not None
            assert HistoryStore(plugin.root, project.fileName()).records == plugin.store.records
            print("Checkpoint restore smoke checks passed", flush=True)
        finally:
            plugin.unload()
            iface.canvas.stopRendering()
            iface.canvas.setLayers([])
            project.clear()
            iface.window.close()


run()
