"""Real Qt event-loop checks, run explicitly with an initialized QgsApplication."""

from time import monotonic

from qgis.core import QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtTest import QTest

from checkpoint.core.watcher import Watcher


def run():
    project = QgsProject()
    layer = QgsVectorLayer("Point?crs=EPSG:4326", "Watched", "memory")
    project.addMapLayer(layer)
    watcher = Watcher(project, interval=3)
    saves = []

    def save():
        saves.append(monotonic())
        watcher.acknowledge(True)

    watcher.saveRequested.connect(save)
    try:
        layer.setOpacity(0.8)
        QTest.qWait(1200)
        layer.setOpacity(0.7)
        QTest.qWait(1200)
        assert not saves, "Debounce did not restart on the second change"
        QTest.qWait(1000)
        assert len(saves) == 1

        layer.setOpacity(0.6)
        QTest.qWait(2200)
        assert len(saves) == 1, "Debounce ignored the minimum gap"
        QTest.qWait(1000)
        assert len(saves) == 2 and saves[-1] - saves[-2] >= 3
        QTest.qWait(3200)
        assert len(saves) == 2, "An idle timer created a checkpoint"

        watcher.configure(False, 1)
        layer.setOpacity(0.5)
        QTest.qWait(2100)
        assert len(saves) == 2
        watcher.configure(True, 1)
        QTest.qWait(100)
        assert len(saves) == 3, "Pending Manual changes were lost on entering Auto"

        extra = QgsVectorLayer("Point?crs=EPSG:4326", "Added later", "memory")
        project.addMapLayer(extra)
        watcher.acknowledge(False)
        assert extra.setSubsetString("1 = 1")
        QTest.qWait(2100)
        assert len(saves) == 4, "A newly added layer's filter was not watched"
        project.removeMapLayer(extra.id())
        QTest.qWait(2100)
        assert len(saves) == 5

        try:
            with watcher.suppress():
                with watcher.suppress():
                    layer.setOpacity(0.4)
                QTimer.singleShot(0, lambda: layer.setOpacity(0.3))
                raise RuntimeError("Simulated restore failure")
        except RuntimeError:
            pass
        QTest.qWait(2100)
        assert len(saves) == 5 and not watcher.dirty
        project.layerTreeRoot().findLayer(layer.id()).setItemVisibilityChecked(False)
        QTest.qWait(2100)
        assert len(saves) == 6, "Watcher did not resume after restore failure"

        project.layerTreeRoot().addGroup("Expansion test")
        watcher.acknowledge(False)
        project.layerTreeRoot().findGroup("Expansion test").setExpanded(False)
        QTest.qWait(2200)
        assert len(saves) == 6, "Expanding a group alone created a checkpoint"

        layer.setOpacity(0.2)
        watcher.close()
        QTest.qWait(2100)
        assert len(saves) == 6, "A pending callback survived watcher shutdown"
        print("Checkpoint watcher smoke checks passed", flush=True)
    finally:
        watcher.close()
        project.clear()


run()
