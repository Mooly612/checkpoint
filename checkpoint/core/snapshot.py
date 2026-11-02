"""Capture/apply styling on the GUI thread; schema 2 retains native group metadata."""
from __future__ import annotations
from ..i18n import tr

import math
from uuid import uuid4
from xml.etree import ElementTree

from qgis.core import (
    Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsLayerTree, QgsLayerTreeGroup, QgsLayerTreeLayer, QgsMapLayerStyle, QgsPointCloudLayer,
    QgsPointXY, QgsReadWriteContext, QgsRectangle, QgsVectorLayer,
)
from qgis.PyQt.QtCore import QThread, QT_VERSION_STR
from qgis.PyQt.QtXml import QDomDocument

GROUP_ID = "checkpoint/group-id"


class SnapshotError(ValueError):
    """A snapshot cannot be captured or safely prepared for application."""


def _main_thread():
    if not 34400 <= Qgis.QGIS_VERSION_INT < 40000 or not QT_VERSION_STR.startswith("5."):
        raise SnapshotError(tr("Checkpoint 0.2 requires QGIS 3.44 or newer in the 3.x series with Qt5. No styling was applied."))
    app = QgsApplication.instance()
    if app is None or QThread.currentThread() != app.thread():
        raise RuntimeError(tr("Checkpoint capture and apply require the QGIS GUI thread"))


def _element(xml):
    doc = QDomDocument()
    result = doc.setContent(xml)
    if not (result[0] if isinstance(result, tuple) else result):
        raise SnapshotError(tr("Invalid tree metadata"))
    return doc, doc.documentElement()


def _group_xml(node):
    doc = QDomDocument()
    wrapper = doc.createElement("checkpoint")
    doc.appendChild(wrapper)
    # QgsLayerTree overrides writeXml and omits inherited exclusivity/WMS fields.
    # Explicit base dispatch includes root fields without cloning its entire tree.
    if isinstance(node, QgsLayerTree):
        QgsLayerTreeGroup.writeXml(node, wrapper, QgsReadWriteContext())
    else:
        node.writeXml(wrapper, QgsReadWriteContext())
    element = wrapper.firstChildElement()
    child = element.firstChildElement()
    while not child.isNull():
        following = child.nextSiblingElement()
        if child.tagName().startswith("layer-tree-"):
            element.removeChild(child)
        child = following
    # Qt's attribute iteration order is not stable between processes.
    return ElementTree.canonicalize(doc.toString()).removeprefix("<checkpoint>").removesuffix("</checkpoint>").strip()


def _check_supported(root):
    if root.customProperty("embedded", 0):
        raise SnapshotError(tr("Embedded tree nodes are not supported. No styling was applied."))
    if isinstance(root, QgsLayerTreeGroup):
        if root.groupLayer() is not None:
            raise SnapshotError(tr("Group layers are not supported. No styling was applied."))
        for child in root.children():
            _check_supported(child)
    elif not isinstance(root, QgsLayerTreeLayer):
        raise SnapshotError(tr("Custom tree nodes are not supported. No styling was applied."))


def _capture_tree(node, seen=None):
    seen = set() if seen is None else seen
    result = dict(visible=node.itemVisibilityChecked(), expanded=node.isExpanded())
    if isinstance(node, QgsLayerTreeLayer):
        result.update(type="layer", id=node.layerId())
    else:
        identity = node.customProperty(GROUP_ID, "")
        if not identity or identity in seen:
            identity = uuid4().hex
            node.setCustomProperty(GROUP_ID, identity)
        seen.add(identity)
        result.update(type="group", id=identity, name=node.name(),
                      children=[_capture_tree(child, seen) for child in node.children()],
                      metadata=_group_xml(node))
    return result


def adopt_tree_identity(root, saved):
    """Reopen a project not yet saved after UUID tagging, without duplicate baselines.

    Only adopt missing IDs when the entire ordered tree, names and layer IDs match.
    Never infer identity from a group name alone or replace an existing identity.
    """
    def matches(node, state):
        if isinstance(node, QgsLayerTreeLayer):
            return state["type"] == "layer" and node.layerId() == state["id"]
        return (state["type"] == "group" and node.name() == state["name"]
                and len(node.children()) == len(state["children"])
                and all(matches(n, child) for n, child in zip(node.children(), state["children"])))
    if not matches(root, saved):
        return
    def adopt(node, state):
        if isinstance(node, QgsLayerTreeGroup):
            if not node.customProperty(GROUP_ID, ""):
                node.setCustomProperty(GROUP_ID, state["id"])
            for child, child_state in zip(node.children(), state["children"]):
                adopt(child, child_state)
    adopt(root, saved)


def capture(project, canvas):
    _main_thread()
    root = project.layerTreeRoot()
    _check_supported(root)
    layers = {}
    for key, layer in project.mapLayers().items():
        style = QgsMapLayerStyle()
        style.readFromLayer(layer)
        if not style.isValid():
            raise SnapshotError(tr("Cannot capture style: ") + layer.name())
        subset = layer.subsetString() if isinstance(layer, (QgsVectorLayer, QgsPointCloudLayer)) else ""
        layers[key] = dict(name=layer.name(), style=style.xmlData(), filter=subset)
    extent = canvas.extent()
    return dict(schema=2, tree=_capture_tree(root), layers=layers,
                extent=[extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()],
                scale=canvas.scale(), view_crs=canvas.mapSettings().destinationCrs().toWkt())


def _flags(node, saved):
    node.setItemVisibilityChecked(saved["visible"])
    node.setExpanded(saved["expanded"])


def _groups(root):
    return {node.customProperty(GROUP_ID, ""): node for node in [root, *root.findGroups(True)]
            if node.customProperty(GROUP_ID, "")}


def _build_tree(saved, layers, templates, groups):
    if saved["type"] == "layer":
        key = saved["id"]
        if key not in layers:
            return None
        template = templates.get(key)
        node = template.clone() if template is not None else QgsLayerTreeLayer(layers[key])
    elif saved["type"] == "group":
        doc, element = _element(saved["metadata"])
        if element.tagName() != "layer-tree-group" or element.attribute("groupLayer"):
            raise SnapshotError(tr("Unsupported saved group metadata; no styling was applied"))
        node = QgsLayerTreeGroup.readXml(element, QgsReadWriteContext())
        if node is None or node.children():
            raise SnapshotError(tr("Invalid group metadata"))
        _check_supported(node)
        exclusive = node.isMutuallyExclusive()
        selected = int(element.attribute("mutually-exclusive-child", "-1"))
        node.setIsMutuallyExclusive(False)
        template = groups.get(saved["id"])
        if template is not None:
            # Preserve newly introduced third-party keys not present in the snapshot.
            for key in template.customProperties():
                if key not in node.customProperties():
                    node.setCustomProperty(key, template.customProperty(key))
        node.setCustomProperty(GROUP_ID, saved["id"])
        node.setName(saved["name"])
        selected_node = None
        for index, child in enumerate(saved["children"]):
            built = _build_tree(child, layers, templates, groups)
            if built is not None:
                node.addChildNode(built)
                if index == selected:
                    selected_node = built
        selected_index = node.children().index(selected_node) if selected_node is not None else -1
        if exclusive:
            node.setIsMutuallyExclusive(True, selected_index)
    else:
        raise SnapshotError(tr("Unknown snapshot tree node type"))
    _flags(node, saved)
    return node


def _tree_ids(saved):
    if saved["type"] == "layer":
        return {saved["id"]}
    return set().union(*(_tree_ids(child) for child in saved["children"]))


def _merge_extras(current, restored, known):
    """Match UUIDs globally, including renamed/moved/duplicate-named groups."""
    destinations = _groups(restored)
    def key(node):
        return ("group", node.customProperty(GROUP_ID, "")) if isinstance(node, QgsLayerTreeGroup) else ("layer", node.layerId())

    def merge(source, destination, preserve_source_selection=False):
        # Temporarily suspend exclusivity so inserting later children preserves the
        # previously selected child instead of interpreting a stale child index.
        exclusive = destination.isMutuallyExclusive()
        selected = next((key(c) for c in (source if preserve_source_selection else destination).children()
                         if c.itemVisibilityChecked()), None)
        destination.setIsMutuallyExclusive(False)
        for index, child in enumerate(source.children()):
            if isinstance(child, QgsLayerTreeGroup):
                match = destinations.get(child.customProperty(GROUP_ID, ""))
                if match is not None:
                    merge(child, match)
                    continue
                extra = child.clone()
                extra.removeAllChildren()
                merge(child, extra, preserve_source_selection=True)
                # Retain later empty groups and their metadata as well.
            elif child.layerId() in known:
                continue
            else:
                extra = child.clone()
            destination.insertChildNode(min(index, len(destination.children())), extra)
        if exclusive:
            position = next((i for i, child in enumerate(destination.children()) if key(child) == selected), -1)
            destination.setIsMutuallyExclusive(True, position)
    merge(current, restored)


def prepare_view(project, canvas, state):
    """Same CRS: saved center and scale. Different CRS: transformed center and scale.

    Bounding-box transformation validates the full saved area. Preserve the saved
    denominator, so resizing changes coverage but not symbol scale. Never set CRS.
    View errors are nonfatal and independent of layer styling.
    """
    try:
        extent, scale = state["extent"], state["scale"]
        if len(extent) != 4 or not all(math.isfinite(v) for v in [*extent, scale]):
            raise ValueError(tr("invalid extent or scale"))
        rect = QgsRectangle(*extent)
        if rect.isEmpty() or scale <= 0 or extent[0] >= extent[2] or extent[1] >= extent[3]:
            raise ValueError(tr("empty extent or scale"))
        if not state.get("view_crs"):
            raise ValueError(tr("saved CRS is unknown (legacy checkpoint)"))
        source = QgsCoordinateReferenceSystem()
        source.createFromWkt(state["view_crs"])
        destination = canvas.mapSettings().destinationCrs()
        if not source.isValid() or not destination.isValid():
            raise ValueError(tr("invalid CRS"))
        center = QgsPointXY(rect.center())
        if source != destination:
            transform = QgsCoordinateTransform(source, destination, project)
            if not transform.isValid():
                raise ValueError(tr("coordinate transformation is unavailable"))
            center = transform.transform(center)
            rect = transform.transformBoundingBox(rect)
            if rect.isEmpty() or not rect.isFinite():
                raise ValueError(tr("coordinate transformation produced an invalid extent"))
        if not (math.isfinite(center.x()) and math.isfinite(center.y())):
            raise ValueError(tr("coordinate transformation produced an invalid center"))
        return (rect, center, scale), None
    except Exception as exc:
        return None, "Map view skipped: " + str(exc)


def prepare_restore(project, canvas, state, *, restore_view=True):
    """Validate before any styling mutation, also used by the Apply controller."""
    _main_thread()
    if state.get("schema", 1) not in (1, 2):
        raise SnapshotError(tr("Unsupported snapshot schema"))
    layers, root = project.mapLayers(), project.layerTreeRoot()
    _check_supported(root)
    known = _tree_ids(state["tree"])
    if state["tree"]["type"] != "group" or not known <= state["layers"].keys():
        raise SnapshotError(tr("Snapshot tree does not match its layer records"))
    notices, restored = [], None
    if state.get("schema", 1) < 2:
        # Old snapshots have no identities or native group properties. Keep the
        # entire current tree, instead of guessing group matches by name/path.
        notices.append(tr("Legacy checkpoint: tree unchanged because group identities and properties were not saved"))
    else:
        templates = {node.layerId(): node for node in root.findLayers()}
        restored = _build_tree(state["tree"], layers, templates, _groups(root))
        _merge_extras(root, restored, known)
        if not (set(templates) & layers.keys()) <= set(restored.findLayerIds()):
            raise SnapshotError(tr("Applying this tree would remove a live layer"))
    view = None
    if restore_view:
        view, notice = prepare_view(project, canvas, state)
        if notice:
            notices.append(notice)
    styles = {}
    for key, saved in state["layers"].items():
        if key not in layers:
            notices.append(f"not restored: layer {saved['name']} (deleted)")
            continue
        try:
            if ElementTree.fromstring(saved["style"]).tag != "qgis":
                raise ValueError(tr("Expected a QGIS style document"))
        except (ElementTree.ParseError, ValueError) as exc:
            raise SnapshotError(tr("Invalid style: ") + saved["name"]) from exc
        styles[key] = QgsMapLayerStyle(saved["style"])
    return restored, styles, view, notices


def restore(project, canvas, state, *, restore_view=True):
    restored, styles, view, notices = prepare_restore(project, canvas, state, restore_view=restore_view)
    root, layers = project.layerTreeRoot(), project.mapLayers()
    frozen = canvas.isFrozen()
    canvas.freeze(True)
    try:
        canvas.stopRendering()
        project.setDirty(True)
        for key, style in styles.items():
            layer, saved = layers[key], state["layers"][key]
            style.writeToLayer(layer)
            if isinstance(layer, (QgsVectorLayer, QgsPointCloudLayer)):
                if layer.subsetString() != saved["filter"] and not layer.setSubsetString(saved["filter"]):
                    notices.append(f"not restored: filter for {saved['name']} (provider rejected it)")
            layer.triggerRepaint()
        if restored is not None:
            previous = root.children()
            root.setIsMutuallyExclusive(False)
            root.insertChildNodes(0, [child.clone() for child in restored.children()])
            for child in previous:
                root.removeChildNode(child)
            # Root cannot be replaced; apply its native common/server properties.
            doc, element = _element(_group_xml(restored))
            root.readCommonXml(element)
            if hasattr(root, "serverProperties"):
                root.serverProperties().readXml(element)
            root.setHasWmsTimeDimension(restored.hasWmsTimeDimension())
            selected = int(element.attribute("mutually-exclusive-child", "-1"))
            root.setIsMutuallyExclusive(restored.isMutuallyExclusive(), selected)
            root.setName(restored.name())
            _flags(root, state["tree"])
        if view is not None:
            extent, center, scale = view
            canvas.setExtent(extent)
            canvas.setCenter(center)
            canvas.zoomScale(scale, True)
    finally:
        canvas.freeze(frozen)
        if not frozen:
            canvas.refresh()
    return notices
