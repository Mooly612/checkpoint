"""Hash plain snapshot data and describe changes without importing QGIS."""

from __future__ import annotations

import hashlib
import json


def digest(value) -> str:
    """Stable hash, independent of dictionary insertion order."""
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def component_hashes(state: dict) -> dict:
    """Map view and display names are deliberately excluded."""
    return {
        "tree": digest(state["tree"]),
        "styles": {key: digest(layer["style"]) for key, layer in state["layers"].items()},
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
        return "Initial checkpoint"
    before, after = component_hashes(previous), component_hashes(current)
    old_layers, layers = previous["layers"], current["layers"]
    parts = []
    for label, ids, source in (
        ("added", layers.keys() - old_layers.keys(), layers),
        ("removed", old_layers.keys() - layers.keys(), old_layers),
    ):
        if ids:
            parts.append(label + ": " + ", ".join(sorted(source[key]["name"] for key in ids)))
    if before["tree"] != after["tree"]:
        old_shape, old_visible, old_expanded = _tree_parts(previous["tree"])
        shape, visible, expanded = _tree_parts(current["tree"])
        if old_shape != shape:
            parts.append("layer order / groups")
        for label, old, new in (("visibility", old_visible, visible),
                                ("expanded state", old_expanded, expanded)):
            changed = [key for key in old.keys() & new.keys() if old[key] != new[key]]
            if changed:
                count = len(changed)
                noun = "layers" if all(key[0] == "layer" for key in changed) else "items"
                if count == 1:
                    noun = "layer" if noun == "layers" else "item"
                parts.append(f"{label}: {count} {noun}")
    for component, label in (("styles", "style"), ("filters", "filter")):
        changed = sorted(layers[key]["name"] for key in layers.keys() & old_layers.keys()
                         if before[component][key] != after[component][key])
        if changed:
            parts.append(label + ": " + ", ".join(changed))
    return "; ".join(parts) or "No styling changes"
