"""Immutable preview artifacts from detached layers; render jobs stay on Qt's GUI thread."""

import base64
from collections import defaultdict
from time import monotonic
from . import safe_xml as ElementTree

from qgis.core import (
    QgsCoordinateTransform, QgsFeatureRequest, QgsFeatureRenderer, QgsMapLayerStyle, QgsMapSettings,
    QgsReadWriteContext,
    QgsMapRendererParallelJob, QgsPointCloudLayer, QgsRectangle, QgsSymbolLayerUtils,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QBuffer, QIODevice, QObject, QSize, QTimer, Qt
from qgis.PyQt.QtGui import QColor, QImage, QPainter

from .differ import _tree_parts, describe, styles_equal
from ..i18n import tr
from .snapshot import _element, _main_thread, prepare_view

# Cancel is asynchronous: retain jobs AND their detached layers until finished,
# including after the plugin is unloaded or its project has been closed.
_RUNNING = set()


def encode(image, fmt="PNG", quality=-1):
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, fmt, quality):
        raise ValueError(tr("Cannot encode preview image"))
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
    changed = set(old.keys() ^ new.keys())
    changed.update(key for key in old.keys() & new.keys()
                   if old[key]["filter"] != new[key]["filter"]
                   or not styles_equal(old[key]["style"], new[key]["style"]))
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


def symbol_samples(state, key, limit=2):
    """Read renderer XML without cloning or calling the source data provider."""
    saved = state["layers"].get(key) if state else None
    if saved is None:
        return {}
    if len(saved["style"]) > 128_000:
        return {}
    doc, element = _element(saved["style"])
    renderer_element = element.firstChildElement("renderer-v2")
    if renderer_element.isNull():
        return {}
    renderer = QgsFeatureRenderer.load(renderer_element, QgsReadWriteContext())
    if renderer is None:
        return {}
    opacity_text = element.firstChildElement("layerOpacity").text()
    opacity = float(opacity_text) if opacity_text else 1.0
    # Use the same native symbol rendering, without any live QgsMapLayer.
    result, occurrences = {}, defaultdict(int)
    for item in renderer.legendSymbolItems()[:limit]:
        symbol = item.symbol()
        if symbol is None:
            continue
        key = (item.label(), occurrences[item.label()])
        occurrences[item.label()] += 1
        pixmap = QgsSymbolLayerUtils.symbolPreviewPixmap(symbol, QSize(28, 28), 3)
        image = QImage(28, 28, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setOpacity(opacity)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        result[key] = encode(image)
    return result


def lightweight_preview(before, after):
    payload = {"summary": describe(before, after), "samples": [], "more": 0,
               "maps": {}, "status": tr("Map previews off"), "note": tr("Historical comparison, not a simulation of applying this entry now.")}
    samples = []
    for key in changed_ids(before, after)[:2]:
        try:
            old_state = before["layers"].get(key) if before else None
            new_state = after["layers"].get(key)
            if old_state and new_state and styles_equal(old_state["style"], new_state["style"]):
                continue
            old, new = symbol_samples(before, key), symbol_samples(after, key)
            source = after["layers"].get(key) or before["layers"][key]
            for label in sorted(old.keys() | new.keys()):
                if old.get(label) != new.get(label):
                    samples.append({"label": source["name"] + (": " + label[0] if label[0] else ""),
                                    "before": old.get(label), "after": new.get(label)})
        except Exception as exc:
            payload["note"] += " Symbol sample unavailable: " + str(exc)
    payload["samples"] = samples[:2]
    payload["note"] += tr(" Symbol samples are limited to the first two legend items of two changed layers; styles over 128 KB are omitted. Other changes may exist; see the text summary.")
    return payload


class PreviewTask(QObject):
    """GUI-thread preparation and QGIS render jobs; two seconds is a soft budget.

    Synchronous provider calls may exceed it. Preparation and render timings are
    measured separately; cancellation retains resources until jobs finish.
    """
    def __init__(self, project, canvas, before, after, callback, *, maps=True):
        super().__init__()
        self.project, self.canvas = project, canvas
        self.before, self.after, self.callback = before, after, callback
        self.render_maps = maps
        self.layers, self.jobs, self.finished_jobs = {}, [], set()
        self.payload = {"summary": describe(before, after), "samples": [], "more": 0,
                        "maps": {}, "status": tr("Preparing preview"), "note": ""}
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._timeout)
        self.cancelled = False
        self.released = False

    def _check_time(self):
        if monotonic() - self.started >= 2:
            raise TimeoutError(tr("Preview preparation exceeded two seconds"))

    def _prepare(self):
        live = self.project.mapLayers()
        affected = changed_ids(self.before, self.after)
        # Style/filter/visibility comparisons do not need expensive unrelated
        # providers. Order/group changes still require the complete stack.
        focused = bool(affected) and self.before is not None and _tree_parts(self.before["tree"])[0] == _tree_parts(self.after["tree"])[0]
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
                    notes.append(tr("Missing source: ") + saved["name"])
                    continue
                layer = source.clone()
                if layer is None or not layer.isValid():
                    notes.append(tr("Unavailable source: ") + saved["name"])
                    continue
                clones[key] = layer
                QgsMapLayerStyle(saved["style"]).writeToLayer(layer)
                if isinstance(layer, (QgsVectorLayer, QgsPointCloudLayer)):
                    if layer.subsetString() != saved["filter"] and not layer.setSubsetString(saved["filter"]):
                        notes.append(tr("Filter unavailable: ") + saved["name"])
                        del clones[key]
        settings = self.canvas.mapSettings()
        prepared, warning = prepare_view(self.project, self.canvas, self.after)
        if prepared is None:
            raise ValueError(warning)
        extent = prepared[0]
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
        self.payload["note"] += " " + focus + ". Same extent on both sides; not exact changed features. Both styles use data available at capture time."
        if notes:
            self.payload["note"] += " " + "; ".join(sorted(set(notes)))
        self.payload["extent"] = [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()]
        self._check_time()
        if extent.isEmpty() or not extent.isFinite():
            raise ValueError(tr("Map preview unavailable: empty extent"))
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
        waiting_for_job = bool(_RUNNING)
        if waiting_for_job:
            self.render_maps = False
            # A cancelled job still owns its layers until its finished signal.
            # Bound live map jobs globally instead of accumulating detached data.
        _RUNNING.add(self)
        self.started = monotonic()
        self.render_started = None
        try:
            self.payload = lightweight_preview(self.before, self.after)
            if waiting_for_job:
                self.payload["status"] = tr("Map preview skipped while an earlier render finishes; symbol samples remain available")
            self.payload["timings_ms"] = {"symbols": (monotonic() - self.started) * 1000}
            if not self.render_maps:
                self._publish()
                self._release()
                return
            self.started = monotonic()
            self._prepare()
            self.payload["timings_ms"]["preparation"] = (monotonic() - self.started) * 1000
            self.render_started = monotonic()
            self.timer.start(max(1, int((2 - (monotonic() - self.started)) * 1000)))
            for job in self.jobs:
                job.start()
        except TimeoutError:
            self.payload.setdefault("timings_ms", {})["preparation"] = (monotonic() - self.started) * 1000
            self._timeout()
        except Exception as exc:
            self.payload.setdefault("timings_ms", {})["preparation"] = (monotonic() - self.started) * 1000
            self.cancel(tr("Preview unavailable: ") + str(exc))

    def _publish(self):
        if self.render_started is not None:
            self.payload.setdefault("timings_ms", {})["render"] = (monotonic() - self.render_started) * 1000
        callback, self.callback = self.callback, None
        if callback is not None:
            callback(self.payload)

    def _finished(self, side, job):
        if self.released:
            return  # A queued finished signal may follow asynchronous cancellation.
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
                self.payload["status"] = tr("Saved preview")
                self._publish()
            self._release()

    def _timeout(self):
        self.payload["slow"] = True
        self.cancel(tr("Map preview timed out; symbol samples and details remain available"))

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
