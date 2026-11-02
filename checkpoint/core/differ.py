"""Hash plain snapshot data and describe changes without importing QGIS."""

from __future__ import annotations

import hashlib
import json
from xml.etree import ElementTree

from ..i18n import tr


def digest(value) -> str:
    """Stable hash, independent of dictionary insertion order."""
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def normalized_style(xml):
    """Ignore XML attribute order/quoting while retaining all actual style data."""
    try:
        root = ElementTree.fromstring(xml)
        # QGIS callouts embed a serialized symbol inside a QString attribute.
        # Ordinary C14N treats that as literal text, so normalize known symbol
        # options there too. Leave user custom-property/text strings untouched.
        changed = False
        for option in root.findall(".//callout//Option"):
            if option.get("name") not in {"lineSymbol", "fillSymbol", "markerSymbol"}:
                continue
            value = option.get("value", "")
            if not value.lstrip().startswith("<symbol"):
                continue
            try:
                if ElementTree.fromstring(value).tag != "symbol":
                    continue
                option.set("value", ElementTree.canonicalize(value))
                changed = True
            except ElementTree.ParseError:
                pass
        if changed:
            xml = ElementTree.tostring(root, encoding="unicode")
        return ElementTree.canonicalize(xml)
    except (ElementTree.ParseError, TypeError):
        # Keep malformed data distinguishable; application preflight rejects it.
        return xml


def styles_equal(first, second):
    return normalized_style(first) == normalized_style(second)


def component_hashes(state: dict) -> dict:
    """Map view and display names are deliberately excluded."""
    return {
        "tree": digest(state["tree"]),
        "styles": {key: digest(normalized_style(layer["style"]) if state.get("schema", 1) >= 2
                               else layer["style"]) for key, layer in state["layers"].items()},
        "filters": {key: digest(layer["filter"]) for key, layer in state["layers"].items()},
    }


def state_hash(state: dict) -> str:
    return digest(component_hashes(state))


def _tree_parts(node: dict, path: tuple = ()) -> tuple:
    """Separate structure, local visibility, and expansion for descriptions."""
    key = ("layer", node["id"]) if node["type"] == "layer" else ("group", path)
    visible = {key: node["visible"]}
    expanded = {key: node["expanded"]}
    if node["type"] == "layer":
        return ("layer", node["id"]), visible, expanded
    children = []
    for index, child in enumerate(node["children"]):
        shape, child_visible, child_expanded = _tree_parts(child, path + (index,))
        children.append(shape)
        visible.update(child_visible)
        expanded.update(child_expanded)
    return ("group", node["name"], children), visible, expanded


def describe(previous: dict | None, current: dict) -> str:
    if previous is None:
        return tr("Initial checkpoint")
    before, after = component_hashes(previous), component_hashes(current)
    old_layers, layers = previous["layers"], current["layers"]
    parts = []
    for label, ids, source in (
        (tr("added"), layers.keys() - old_layers.keys(), layers),
        (tr("removed"), old_layers.keys() - layers.keys(), old_layers),
    ):
        if ids:
            parts.append(label + ": " + ", ".join(sorted(source[key]["name"] for key in ids)))
    if before["tree"] != after["tree"]:
        old_shape, old_visible, old_expanded = _tree_parts(previous["tree"])
        shape, visible, expanded = _tree_parts(current["tree"])
        if old_shape != shape:
            parts.append(tr("layer order / groups"))
        elif old_visible == visible and old_expanded == expanded:
            parts.append(tr("group properties"))
        for label, old, new in ((tr("visibility"), old_visible, visible),
                                (tr("expanded state"), old_expanded, expanded)):
            changed = [key for key in old.keys() & new.keys() if old[key] != new[key]]
            if changed:
                count = len(changed)
                noun = "layers" if all(key[0] == "layer" for key in changed) else "items"
                if count == 1:
                    noun = "layer" if noun == "layers" else "item"
                parts.append(f"{label}: {count} {noun}")
    for component, label in (("styles", tr("style")), ("filters", tr("filter"))):
        changed = sorted(layers[key]["name"] for key in layers.keys() & old_layers.keys()
                         if (not styles_equal(old_layers[key]["style"], layers[key]["style"])
                             if component == "styles" else before[component][key] != after[component][key]))
        if changed:
            parts.append(label + ": " + ", ".join(changed))
    return "; ".join(parts) or tr("No styling changes")


def application_summary(current, saved, *, restore_view=True):
    """Prospective scope, independent of the entry's historical description/images."""
    current_layers, target = current["layers"], saved["layers"]
    common = current_layers.keys() & target.keys()
    lines = [tr("Apply saved styling to {count} existing layers.").format(count=len(common))]
    for key in sorted(common, key=lambda k: target[k]["name"]):
        changes = []
        if not styles_equal(current_layers[key]["style"], target[key]["style"]):
            changes.append(tr("style / labels"))
        if current_layers[key]["filter"] != target[key]["filter"]:
            changes.append(tr("filter"))
        lines.append(target[key]["name"] + ": " + (", ".join(changes) or tr("style and filter unchanged")))
    old_shape, old_visible, old_expanded = _tree_parts(current["tree"])
    shape, visible, expanded = _tree_parts(saved["tree"])
    if saved.get("schema", 1) < 2:
        lines.append(tr("Legacy entry: keep the current tree; group properties and identities were not recorded."))
    else:
        lines.append(tr("Layer order / groups: ") + (tr("change") if old_shape != shape else tr("unchanged")))
        lines.append(tr("Visibility: ") + (tr("change") if old_visible != visible else tr("unchanged")))
        lines.append(tr("Expanded groups: ") + (tr("change") if old_expanded != expanded else tr("unchanged")))
        if component_hashes(current)["tree"] != component_hashes(saved)["tree"]:
            lines.append(tr("Saved group properties will also be applied; later layers/groups remain."))
    if not restore_view:
        lines.append(tr("Map view: keep current view (setting disabled)."))
    elif not saved.get("view_crs"):
        lines.append(tr("Map view: skip; saved CRS is unknown."))
    elif current.get("view_crs") != saved["view_crs"]:
        lines.append(tr("Map view: transform saved center into current CRS and restore saved scale."))
    else:
        lines.append(tr("Map view: restore saved center and scale."))
    missing = [target[k]["name"] for k in target.keys() - current_layers.keys()]
    extra = [current_layers[k]["name"] for k in current_layers.keys() - target.keys()]
    if missing:
        lines.append(tr("Missing layers, skipped: ") + ", ".join(sorted(missing)))
    if extra:
        lines.append(tr("Later layers, kept: ") + ", ".join(sorted(extra)))
    lines.append(tr("No geometry, attributes, data sources or project files are restored. Provider filters may fail; recovery stays available."))
    return "\n".join(lines)
