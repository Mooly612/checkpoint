"""Signal-driven debounce and minimum gap. Requires a real QGIS event loop."""

from __future__ import annotations

from contextlib import contextmanager
import math
from time import monotonic

from qgis.core import QgsPointCloudLayer, QgsVectorLayer
from qgis.PyQt.QtCore import QObject, QTimer, Qt, pyqtSignal


def disconnect(connections):
    """Disconnect only our slots, tolerating already deleted Qt senders."""
    for signal, slot in connections:
        try:
            signal.disconnect(slot)
        except (TypeError, RuntimeError):
            pass
    connections.clear()


class Watcher(QObject):
    saveRequested = pyqtSignal()
    stateChanged = pyqtSignal()

    def __init__(self, project, parent=None, *, interval=60, last_saved=None):
        super().__init__(parent)
        self.auto, self.dirty, self.closed = True, False, False
        self.interval, self.last_saved = interval, last_saved
        self.last_change, self._suppression = 0.0, 0
        self._connections, self._layers = [], {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._due)
        try:
            root = project.layerTreeRoot()
            for signal in (root.addedChildren, root.removedChildren, root.visibilityChanged,
                           root.nameChanged):
                self._connect(signal, self.mark_dirty, self._connections)
            self._connect(root.customPropertyChanged, self._custom_property, self._connections)
            self._connect(project.layersAdded, self._added, self._connections)
            self._connect(project.layersWillBeRemoved, self._removing, self._connections)
            self._watch_layers(project.mapLayers().values())
        except Exception:
            self.close()
            self.deleteLater()
            raise

    @staticmethod
    def _connect(signal, slot, connections):
        signal.connect(slot)
        connections.append((signal, slot))

    def _watch_layers(self, layers):
        for layer in layers:
            if layer.id() in self._layers:
                continue
            connections = self._layers.setdefault(layer.id(), [])
            for signal in (layer.styleChanged, layer.rendererChanged):
                self._connect(signal, self.mark_dirty, connections)
            if isinstance(layer, (QgsVectorLayer, QgsPointCloudLayer)):
                self._connect(layer.subsetStringChanged, self.mark_dirty, connections)

    def _added(self, layers):
        self._watch_layers(layers)
        self.mark_dirty()

    def _removing(self, layers):
        # Both documented signal overloads are accepted: IDs or layer objects.
        for layer in layers:
            layer_id = layer if isinstance(layer, str) else layer.id()
            disconnect(self._layers.pop(layer_id, []))
        self.mark_dirty()

    def _custom_property(self, node, key):
        # Root receives propagated descendant signals, including newly added groups.
        if key != "checkpoint/group-id":
            self.mark_dirty()

    def mark_dirty(self, *args):
        if self.closed or self._suppression:
            return
        self.dirty, self.last_change = True, monotonic()
        self.stateChanged.emit()
        self._schedule()

    def configure(self, auto: bool, interval: int):
        if interval < 1:
            raise ValueError("Auto interval must be at least one second")
        self.auto, self.interval = auto, interval
        self._schedule()

    def _remaining(self):
        due = self.last_change + 2.0
        if self.last_saved is not None:
            due = max(due, self.last_saved + self.interval)
        return due - monotonic()

    def _schedule(self):
        self._timer.stop()
        if self.auto and self.dirty and not (self.closed or self._suppression):
            self._timer.start(max(1, math.ceil(self._remaining() * 1000)))

    def _due(self):
        if self.closed or self._suppression or not (self.auto and self.dirty):
            return
        if self._remaining() > 0:
            self._schedule()
        else:
            # The controller acknowledges successful capture, including a duplicate.
            # Errors leave dirty state intact without creating a retry timer loop.
            self.saveRequested.emit()

    def acknowledge(self, stored: bool):
        self._timer.stop()
        self.dirty = False
        if stored:
            self.last_saved = monotonic()

    @contextmanager
    def suppress(self):
        """Ignore restore signals through the next event-loop turn, also on error."""
        self._suppression += 1
        self._timer.stop()
        self.dirty = False
        try:
            yield
        finally:
            QTimer.singleShot(0, self._resume)

    def _resume(self):
        if not self.closed:
            self._suppression -= 1

    def close(self):
        self.closed = True
        self._timer.stop()
        disconnect(self._connections)
        for connections in self._layers.values():
            disconnect(connections)
        self._layers.clear()
