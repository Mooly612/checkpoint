"""Translate live QGIS state to plain data and back on the GUI thread.

APIs reviewed against 3.28/4.0; smoke-tested on QGIS 3.44.8 / Qt 5.15.18.
The caller owns watcher suppression and before/after restore history entries.
"""

from __future__ import annotations

from collections import defaultdict
import math
from xml.etree import ElementTree

from qgis.core import (
    QgsApplication, QgsLayerTreeGroup, QgsLayerTreeLayer, QgsMapLayerStyle,
    QgsPointCloudLayer, QgsRectangle, QgsVectorLayer,
)
from qgis.PyQt.QtCore import QThread


class SnapshotError(ValueError):
    """A snapshot cannot be captured or safely prepared for restoration."""


def _main_thread():
    app = QgsApplication.instance()
    if app is None or QThread.currentThread() != app.thread():
        raise RuntimeError("Checkpoint capture and restore require the QGIS GUI thread")


def _capture_tree(node) -> dict:
    result = {"visible": node.itemVisibilityChecked(), "expanded": node.isExpanded()}
    if isinstance(node, QgsLayerTreeLayer):
        result.update(type="layer", id=node.layerId())
    else:
        result.update(type="group", name=node.name(), children=[
            _capture_tree(child) for child in node.children()
            if isinstance(child, (QgsLayerTreeGroup, QgsLayerTreeLayer))])
    return result


def capture(project, canvas) -> dict:
    """Capture tree, opaque style XML, filters, extent, and scale as plain data."""
    _main_thread()
    layers = {}
    for layer_id, layer in project.mapLayers().items():
        style = QgsMapLayerStyle()
        style.readFromLayer(layer)
        if not style.isValid():
            raise SnapshotError(f"Cannot capture style: {layer.name()}")
        subset = layer.subsetString() if isinstance(
            layer, (QgsVectorLayer, QgsPointCloudLayer)) else ""
        layers[layer_id] = {"name": layer.name(), "style": style.xmlData(), "filter": subset}
    extent = canvas.extent()
    return {
        "tree": _capture_tree(project.layerTreeRoot()), "layers": layers,
        "extent": [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()],
        "scale": canvas.scale(),
    }


def _flags(node, saved: dict):
    node.setItemVisibilityChecked(saved["visible"])
    node.setExpanded(saved["expanded"])


def _build_tree(saved: dict, layers: dict, templates: dict):
    """Build an unattached tree; missing layers never get recreated."""
    if saved["type"] == "layer":
        layer_id = saved["id"]
        if layer_id not in layers:
            return None
        template = templates.get(layer_id)
        node = template.clone() if template is not None else QgsLayerTreeLayer(layers[layer_id])
    elif saved["type"] == "group":
        node = QgsLayerTreeGroup(saved["name"])
        for child in saved["children"]:
            built = _build_tree(child, layers, templates)
            if built is not None:
                node.addChildNode(built)
    else:
        raise SnapshotError("Unknown snapshot tree node type")
    _flags(node, saved)
    return node


def _tree_ids(saved: dict) -> set[str]:
    if saved["type"] == "layer":
        return {saved["id"]}
    return set().union(*(_tree_ids(child) for child in saved["children"]))


def _prune_known(group, known: set[str]):
    """Keep only extra nodes in an unattached clone, retaining their ancestry."""
    for child in group.children():
        if isinstance(child, QgsLayerTreeGroup):
            _prune_known(child, known)
            if not child.children():
                group.removeChildNode(child)
        elif isinstance(child, QgsLayerTreeLayer) and child.layerId() in known:
            group.removeChildNode(child)


def _merge_extras(current, restored, known: set[str]):
    """Insert later layers at current sibling positions among restored nodes."""
    groups = defaultdict(list)
    for child in restored.children():
        if isinstance(child, QgsLayerTreeGroup):
            groups[child.name()].append(child)
    occurrences = defaultdict(int)
    for index, child in enumerate(current.children()):
        if isinstance(child, QgsLayerTreeGroup):
            occurrence = occurrences[child.name()]
            occurrences[child.name()] += 1
            matches = groups[child.name()]
            if occurrence < len(matches):
                _merge_extras(child, matches[occurrence], known)
                continue
            extra = child.clone()
            _prune_known(extra, known)
            if not extra.children():
                continue
        elif isinstance(child, QgsLayerTreeLayer) and child.layerId() in known:
            continue
        else:
            # This also preserves QGIS 4 custom nodes outside the snapshot schema.
            extra = child.clone()
        restored.insertChildNode(min(index, len(restored.children())), extra)


def _prepare_view(state: dict):
    extent, scale = state["extent"], state["scale"]
    if len(extent) != 4 or not all(math.isfinite(value) for value in [*extent, scale]):
        raise SnapshotError("Invalid map view in snapshot")
    if extent[0] > extent[2] or extent[1] > extent[3] or scale < 0:
        raise SnapshotError("Invalid map view in snapshot")
    # An empty project may not have a meaningful map view yet.
    if extent[0] == extent[2] or extent[1] == extent[3] or scale == 0:
        return None
    return QgsRectangle(*extent), scale


def restore(project, canvas, state: dict, *, restore_view: bool = True) -> list[str]:
    """Apply a snapshot and return plain notices for the caller's message bar.

    Call under the watcher's restore guard. This is not a history transaction:
    the controller must pin the current state before calling, even on partial failure.
    """
    _main_thread()
    layers, root = project.mapLayers(), project.layerTreeRoot()
    templates = {node.layerId(): node for node in root.findLayers()}
    known = _tree_ids(state["tree"])
    if state["tree"]["type"] != "group" or not known <= state["layers"].keys():
        raise SnapshotError("Snapshot tree does not match its layer records")
    restored = _build_tree(state["tree"], layers, templates)
    _merge_extras(root, restored, known)
    # Never remove the last tree reference to a live layer in the registry.
    if not (set(templates) & layers.keys()) <= set(restored.findLayerIds()):
        raise SnapshotError("Restoring this tree would remove a live layer")
    view = _prepare_view(state) if restore_view else None
    styles, notices = {}, []
    for layer_id, saved in state["layers"].items():
        if layer_id not in layers:
            notices.append(f"not restored: layer {saved['name']} (deleted)")
            continue
        try:
            if ElementTree.fromstring(saved["style"]).tag != "qgis":
                raise ValueError("Expected a QGIS style document")
        except (ElementTree.ParseError, ValueError) as exc:
            raise SnapshotError(f"Invalid style: {saved['name']}") from exc
        styles[layer_id] = QgsMapLayerStyle(saved["style"])

    frozen = canvas.isFrozen()
    canvas.freeze(True)
    try:
        canvas.stopRendering()
        # Partial application must also leave the project marked as modified.
        project.setDirty(True)
        for layer_id, style in styles.items():
            layer, saved = layers[layer_id], state["layers"][layer_id]
            style.writeToLayer(layer)
            if isinstance(layer, (QgsVectorLayer, QgsPointCloudLayer)):
                if (layer.subsetString() != saved["filter"]
                        and not layer.setSubsetString(saved["filter"])):
                    notices.append(f"not restored: filter for {saved['name']} (provider rejected it)")
            layer.triggerRepaint()

        previous = root.children()
        # Add all replacements BEFORE removing originals. Disabling the registry
        # bridge alone is not sufficient protection against queued deletion.
        root.insertChildNodes(0, [child.clone() for child in restored.children()])
        for child in previous:
            root.removeChildNode(child)
        _flags(root, state["tree"])
        if view is not None:
            extent, scale = view
            canvas.setExtent(extent)
            canvas.zoomScale(scale, True)
        elif restore_view:
            notices.append("not restored: map view (empty extent or scale)")
    finally:
        canvas.freeze(frozen)
        if not frozen:
            canvas.refresh()
    return notices
