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


def test_application_scope_uses_current_project_not_historical_description(state):
    from checkpoint.core.differ import application_summary
    saved = deepcopy(state)
    current = deepcopy(state)
    current['layers']['roads']['style'] = '<changed/>'
    current['layers']['parcels']['filter'] = 'id > 3'
    current['layers']['later'] = {'name': 'Later', 'style': '<style/>', 'filter': ''}
    summary = application_summary(current, saved)
    assert 'Roads: style / labels' in summary
    assert 'Parcels: filter' in summary
    assert 'Later layers, kept: Later' in summary
    assert 'saved CRS is unknown' in summary
    del current['layers']['roads']
    assert 'Missing layers, skipped: Roads' in application_summary(current, saved)
    assert 'setting disabled' in application_summary(current, saved, restore_view=False)


def test_schema_two_deduplicates_equivalent_qgis_xml_and_retains_legacy_hashes(state):
    before, after = deepcopy(state), deepcopy(state)
    before['layers']['roads']['style'] = '<qgis opacity="1" labels="1"><symbol color="red" width="2"/></qgis>'
    after['layers']['roads']['style'] = '<qgis labels="1" opacity="1"><symbol width="2" color="red"></symbol></qgis>'
    # Existing schema-1 records still validate against their original byte hash.
    assert state_hash(before) != state_hash(after)
    before['schema'] = after['schema'] = 2
    assert state_hash(before) == state_hash(after)
    assert describe(before, after) == 'No styling changes'
    from checkpoint.core.differ import application_summary
    assert 'Roads: style and filter unchanged' in application_summary(before, after)
    after['layers']['roads']['style'] = after['layers']['roads']['style'].replace('red', 'blue')
    assert state_hash(before) != state_hash(after)
    assert describe(before, after) == 'style: Roads'


def test_embedded_callout_xml_order_is_ignored_but_values_and_user_text_are_not(state):
    from xml.sax.saxutils import quoteattr
    from checkpoint.core.differ import styles_equal
    first = '<symbol type="line" alpha="1"><layer class="SimpleLine" color="red"/></symbol>'
    second = '<symbol alpha="1" type="line"><layer color="red" class="SimpleLine"/></symbol>'
    def wrap(value, parent='callout'):
        return '<qgis><' + parent + '><Option name="lineSymbol" value=' + quoteattr(value) + '/></' + parent + '></qgis>'
    assert styles_equal(wrap(first), wrap(second))
    assert not styles_equal(wrap(first), wrap(second.replace('red', 'blue')))
    assert not styles_equal(wrap(first, 'customproperties'), wrap(second, 'customproperties'))
