from copy import deepcopy

import pytest

from checkpoint.core.differ import component_hashes, describe, digest, state_hash


def test_hash_is_independent_of_dict_order(state):
    reordered = dict(reversed(list(state.items())))
    reordered["layers"] = dict(reversed(list(state["layers"].items())))
    assert state_hash(state) == state_hash(reordered)
    assert len(state_hash(state)) == 64


def test_view_and_display_names_do_not_affect_hash(state):
    changed = deepcopy(state)
    changed.update(extent=[100, 100, 200, 200], scale=2000)
    changed["layers"]["roads"]["name"] = "Renamed roads"
    assert state_hash(state) == state_hash(changed)
    assert describe(state, changed) == "No styling changes"


@pytest.mark.parametrize("field,value,label", [
    ("style", "<style color='blue'/>", "style: Roads"),
    ("filter", '"area" > 100', "filter: Roads"),
])
def test_layer_changes(state, field, value, label):
    changed = deepcopy(state)
    changed["layers"]["roads"][field] = value
    assert state_hash(state) != state_hash(changed)
    assert describe(state, changed) == label


@pytest.mark.parametrize("field,label", [
    ("visible", "visibility: 1 layer"), ("expanded", "expanded state: 1 layer")])
def test_tree_flags(state, field, label):
    changed = deepcopy(state)
    changed["tree"]["children"][0][field] = False
    assert state_hash(state) != state_hash(changed)
    assert describe(state, changed) == label


def test_layer_order(state):
    changed = deepcopy(state)
    changed["tree"]["children"].reverse()
    assert state_hash(state) != state_hash(changed)
    assert describe(state, changed) == "layer order / groups"


def test_nested_group_structure_and_flags(state):
    changed = deepcopy(state)
    changed["tree"]["children"] = [dict(type="group", name="Land", visible=True,
                                        expanded=True, children=changed["tree"]["children"])]
    assert "layer order / groups" in describe(state, changed)
    hidden = deepcopy(changed)
    hidden["tree"]["children"][0]["visible"] = False
    assert describe(changed, hidden) == "visibility: 1 item"


def test_added_removed_layers(state):
    changed = deepcopy(state)
    changed["tree"]["children"].pop()
    del changed["layers"]["parcels"]
    assert describe(state, changed) == "removed: Parcels; layer order / groups"
    assert describe(changed, state) == "added: Parcels; layer order / groups"


def test_combined_changes_and_component_isolation(state):
    changed = deepcopy(state)
    for layer in changed["layers"].values():
        layer["style"] = "<new/>"
    changed["layers"]["parcels"]["filter"] = "id > 5"
    for node in changed["tree"]["children"]:
        node["visible"] = False
    assert describe(state, changed) == (
        "visibility: 2 layers; style: Parcels, Roads; filter: Parcels")
    before, after = component_hashes(state), component_hashes(changed)
    assert before["filters"]["roads"] == after["filters"]["roads"]
    assert before["styles"]["roads"] != after["styles"]["roads"]


def test_initial_description(state):
    assert describe(None, state) == "Initial checkpoint"


def test_invalid_float_is_rejected():
    with pytest.raises(ValueError):
        digest(float("nan"))
