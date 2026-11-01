"""Immutable preview artifacts from detached layers; render jobs stay on Qt's GUI thread."""

import base64
from collections import defaultdict
from time import monotonic
from xml.etree import ElementTree

from qgis.core import (
    QgsCoordinateTransform, QgsFeatureRequest, QgsMapLayerStyle, QgsMapSettings,
    QgsMapRendererParallelJob, QgsPointCloudLayer, QgsRectangle, QgsSymbolLayerUtils,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QBuffer, QIODevice, QObject, QSize, QTimer, Qt
from qgis.PyQt.QtGui import QColor, QImage, QPainter

from .differ import describe
from .snapshot import _main_thread

# Cancel is asynchronous: retain jobs AND their detached layers until finished,
# including after the plugin is unloaded or its project has been closed.
_RUNNING = set()


def encode(image, fmt="PNG", quality=-1):
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, fmt, quality):
        raise ValueError("Cannot encode preview image")
    return base64.b64encode(bytes(buffer.data())).decode("ascii")


def visible_ids(node, parent=True):
    visible = parent and node["visible"]
    if node["type"] == "layer":
        return [node["id"]] if visible else []
    return [key for child in node["children"] for key in visible_ids(child, visible)]


def changed_ids(before, after):
    if before is None:
        return list(after["layers"])
    old, new = before["layers"], after["layers"]
    changed = {key for key in old.keys() | new.keys() if old.get(key) != new.get(key)}
    changed.update(set(visible_ids(before["tree"])) ^ set(visible_ids(after["tree"])))
    return sorted(changed)


def legend_samples(layer, check_time=lambda: None):
    if not isinstance(layer, QgsVectorLayer) or layer.renderer() is None:
        return {}
    items, occurrences = {}, defaultdict(int)
    for item in layer.renderer().legendSymbolItems():
        check_time()
        symbol = item.symbol()
        if symbol is None:
            continue
        label = item.label()
        key = (label, occurrences[label])
        occurrences[label] += 1
        pixmap = QgsSymbolLayerUtils.symbolPreviewPixmap(symbol, QSize(28, 28), 3)
        image = QImage(28, 28, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setOpacity(layer.opacity())
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        items[key] = encode(image)
    return items


class PreviewTask(QObject):
    """One before/after pair, one total two-second budget, no custom worker thread."""
    def __init__(self, project, canvas, before, after, callback):
        super().__init__()
        self.project, self.canvas = project, canvas
        self.before, self.after, self.callback = before, after, callback
        self.layers, self.jobs, self.finished_jobs = {}, [], set()
        self.payload = {"summary": describe(before, after), "samples": [], "more": 0,
                        "maps": {}, "status": "Preparing preview", "note": ""}
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._timeout)
        self.cancelled = False
        self.released = False

    def _check_time(self):
        if monotonic() - self.started >= 2:
            raise TimeoutError("Preview preparation exceeded two seconds")

    def _prepare(self):
        live = self.project.mapLayers()
        affected = changed_ids(self.before, self.after)
        # Style/filter/visibility comparisons do not need expensive unrelated
        # providers. Order/group changes still require the complete stack.
        focused = bool(affected) and self.before is not None and "layer order / groups" not in self.payload["summary"]
        if focused:
            for key in affected:
                old = self.before["layers"].get(key)
                new = self.after["layers"].get(key)
                if old and new:
                    old_xml, new_xml = ElementTree.fromstring(old["style"]), ElementTree.fromstring(new["style"])
                    if any(old_xml.findtext(tag) != new_xml.findtext(tag)
                           for tag in ("blendMode", "featureBlendMode", "layerOpacity")):
                        focused = False
                        break
        notes = ["Changed layers only; unrelated context omitted"] if focused else []
        self.payload["affected"] = [
            (self.after["layers"].get(key) or self.before["layers"][key])["name"] for key in affected]
        if self.before is not None:
            old_visible, new_visible = set(visible_ids(self.before["tree"])), set(visible_ids(self.after["tree"]))
            for key in sorted(old_visible ^ new_visible):
                saved = self.after["layers"].get(key) or self.before["layers"][key]
                notes.append(saved["name"] + (": visible → hidden" if key in old_visible else ": hidden → visible"))
        for side, state in (("before", self.before), ("after", self.after)):
            clones = self.layers[side] = {}
            if state is None:
                continue
            for key, saved in state["layers"].items():
                if focused and key not in affected:
                    continue
                self._check_time()
                source = live.get(key)
                if source is None:
                    notes.append("Missing source: " + saved["name"])
                    continue
                layer = source.clone()
                if layer is None or not layer.isValid():
                    notes.append("Unavailable source: " + saved["name"])
                    continue
                clones[key] = layer
                QgsMapLayerStyle(saved["style"]).writeToLayer(layer)
                if isinstance(layer, (QgsVectorLayer, QgsPointCloudLayer)):
                    if layer.subsetString() != saved["filter"] and not layer.setSubsetString(saved["filter"]):
                        notes.append("Filter unavailable: " + saved["name"])
                        del clones[key]
        samples = []
        for key in affected:
            self._check_time()
            old = legend_samples(self.layers["before"].get(key), self._check_time)
            new = legend_samples(self.layers["after"].get(key), self._check_time)
            source = self.after["layers"].get(key) or self.before["layers"][key]
            for label in sorted(old.keys() | new.keys()):
                if old.get(label) != new.get(label):
                    samples.append({"label": source["name"] + (": " + label[0] if label[0] else ""),
                                    "before": old.get(label), "after": new.get(label)})
        self.payload["samples"], self.payload["more"] = samples[:2], max(0, len(samples) - 2)
        settings = self.canvas.mapSettings()
        extent = QgsRectangle(*self.after["extent"])
        focus = "Saved map view with layer context"
        # Prefer one real feature neighborhood over a huge project/layer extent.
        # Explicitly label it representative; this is not geometry change detection.
        for key in affected:
            found = False
            for side in ("after", "before"):
                layer = self.layers[side].get(key)
                if not isinstance(layer, QgsVectorLayer):
                    continue
                request = QgsFeatureRequest().setLimit(1)
                feature = next(layer.getFeatures(request), None)
                self._check_time()
                if feature is None or not feature.hasGeometry():
                    continue
                transform = QgsCoordinateTransform(layer.crs(), settings.destinationCrs(), self.project)
                box = transform.transformBoundingBox(feature.geometry().boundingBox())
                if not box.isFinite():
                    continue
                # A small fraction of the saved view also gives a point a nonzero area.
                radius = max(box.width(), box.height(), extent.width() / 1000,
                             extent.height() / 1000, 1e-6)
                center = box.center()
                extent = QgsRectangle(center.x() - radius, center.y() - radius,
                                      center.x() + radius, center.y() + radius)
                focus = "Representative feature neighborhood: " + layer.name()
                found = True
                break
            if found:
                break
        self.payload["note"] = focus + ". Same extent on both sides; not exact changed features. Both styles use data available at capture time."
        if notes:
            self.payload["note"] += " " + "; ".join(sorted(set(notes)))
        self.payload["extent"] = [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()]
        self._check_time()
        if extent.isEmpty() or not extent.isFinite():
            raise ValueError("Map preview unavailable: empty extent")
        for side, state in (("before", self.before), ("after", self.after)):
            if state is None:
                continue
            config = QgsMapSettings(settings)
            config.setOutputSize(QSize(400, 260))
            config.setBackgroundColor(QColor("#e8e6df"))
            config.setExtent(extent)
            config.setLayers([self.layers[side][key] for key in visible_ids(state["tree"])
                              if key in self.layers[side]])
            config.setLayerStyleOverrides({})
            job = QgsMapRendererParallelJob(config)
            self.jobs.append(job)
            job.finished.connect(lambda side=side, job=job: self._finished(side, job))

    def start(self):
        _main_thread()
        _RUNNING.add(self)
        self.started = monotonic()
        try:
            self._prepare()
            self.timer.start(max(1, int((2 - (monotonic() - self.started)) * 1000)))
            for job in self.jobs:
                job.start()
        except TimeoutError:
            self._timeout()
        except Exception as exc:
            self.cancel("Preview unavailable: " + str(exc))

    def _publish(self):
        callback, self.callback = self.callback, None
        if callback is not None:
            callback(self.payload)

    def _finished(self, side, job):
        self.finished_jobs.add(job)
        if not self.cancelled and monotonic() - self.started >= 2:
            self._timeout()
            return
        if not self.cancelled:
            try:
                self.payload["maps"][side] = encode(job.renderedImage(), "JPEG", 70)
                if job.errors():
                    self.payload["note"] += " Some source layers rendered partially."
            except Exception as exc:
                self.payload["note"] += " " + str(exc)
        if len(self.finished_jobs) == len(self.jobs):
            self.timer.stop()
            if not self.cancelled:
                self.payload["status"] = "Saved preview"
                self._publish()
            self._release()

    def _timeout(self):
        self.cancel("thumbnails disabled: project is heavy")

    def cancel(self, reason="Preview interrupted by a newer checkpoint", *, discard=False):
        self.cancelled = True
        self.timer.stop()
        self.payload["status"] = reason
        if discard:
            self.callback = None
        else:
            self._publish()
        for job in tuple(self.jobs):
            if job.isActive():
                job.cancelWithoutBlocking()
        if not any(job.isActive() for job in self.jobs):
            self._release()

    def _release(self):
        if self.released:
            return
        self.released = True
        self.jobs.clear()
        self.finished_jobs.clear()
        self.layers.clear()
        self.before = self.after = None
        self.project = self.canvas = None
        _RUNNING.discard(self)
        self.deleteLater()
