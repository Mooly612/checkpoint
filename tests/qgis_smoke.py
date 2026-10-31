"""Run explicitly in the QGIS Python console; not a headless pytest test.

Uses a separate project and canvas. Does not modify the user's open project.
This script has not yet been executed against a real QGIS installation.
"""

from copy import deepcopy
import json

from qgis.core import QgsApplication, QgsProject, QgsRectangle, QgsVectorLayer
from qgis.gui import QgsMapCanvas

from checkpoint.core.differ import state_hash
from checkpoint.core.snapshot import SnapshotError, capture, restore


def run():
    project, canvas = QgsProject(), QgsMapCanvas()
    canvas.resize(640, 480)
    try:
        roads = QgsVectorLayer("Point?crs=EPSG:4326&field=kind:integer", "Roads", "memory")
        parcels = QgsVectorLayer("Polygon?crs=EPSG:4326&field=kind:integer", "Parcels", "memory")
        assert roads.isValid() and parcels.isValid()
        project.addMapLayer(roads)
        project.addMapLayer(parcels)
        root = project.layerTreeRoot()
        group = root.addGroup("Land")
        old = root.findLayer(parcels.id())
        group.addChildNode(old.clone())
        root.removeChildNode(old)
        group.setExpanded(False)
        group.setItemVisibilityChecked(False)
        canvas.setLayers([roads, parcels])
        # Use an explicit nonempty view even though these memory layers are empty.
        canvas.setExtent(QgsRectangle(0, 0, 10, 10))
        original = capture(project, canvas)
        assert json.loads(json.dumps(original)) == original

        roads.setOpacity(0.25)
        group.setExpanded(True)
        group.setItemVisibilityChecked(True)
        old = root.findLayer(roads.id())
        group.addChildNode(old.clone())
        root.removeChildNode(old)
        canvas.setExtent(QgsRectangle(30, 30, 40, 40))
        assert restore(project, canvas, original) == []
        QgsApplication.processEvents()
        assert state_hash(capture(project, canvas)) == state_hash(original)
        assert set(project.mapLayers()) == {roads.id(), parcels.id()}
        assert abs(canvas.scale() / original["scale"] - 1) < 0.001

        # Check that the restore option leaves the user's current view intact.
        canvas.setExtent(QgsRectangle(60, 60, 80, 80))
        view = capture(project, canvas)
        assert restore(project, canvas, original, restore_view=False) == []
        unchanged_view = capture(project, canvas)
        assert unchanged_view["extent"] == view["extent"]
        assert unchanged_view["scale"] == view["scale"]

        # A later layer survives under a group absent from the saved snapshot.
        extra = QgsVectorLayer("Point?crs=EPSG:4326", "Later layer", "memory")
        project.addMapLayer(extra, False)
        later = root.addGroup("Later group")
        later.addLayer(extra).setItemVisibilityChecked(False)
        extra.setOpacity(0.4)
        extra_before = capture(project, canvas)["layers"][extra.id()]
        assert restore(project, canvas, original) == []
        QgsApplication.processEvents()
        assert project.mapLayer(extra.id()) is not None
        assert root.findLayer(extra.id()).parent().name() == "Later group"
        assert not root.findLayer(extra.id()).itemVisibilityChecked()
        assert capture(project, canvas)["layers"][extra.id()] == extra_before

        # Deleted layers stay deleted, including after queued registry updates.
        removed_id = parcels.id()
        project.removeMapLayer(removed_id)
        assert restore(project, canvas, original) == ["not restored: layer Parcels (deleted)"]
        QgsApplication.processEvents()
        assert set(project.mapLayers()) == {roads.id(), extra.id()}

        # Malformed XML must fail before changing either styles or the tree.
        invalid = deepcopy(original)
        invalid["layers"][roads.id()]["style"] = "<broken"
        before = capture(project, canvas)
        try:
            restore(project, canvas, invalid)
        except SnapshotError:
            pass
        else:
            raise AssertionError("Malformed style was accepted")
        assert capture(project, canvas) == before

        canvas.freeze(True)
        restore(project, canvas, original)
        assert canvas.isFrozen()
        print("Checkpoint QGIS smoke checks passed")
    finally:
        canvas.stopRendering()
        canvas.setLayers([])
        project.clear()
        canvas.close()


run()
