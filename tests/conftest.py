from copy import deepcopy

import pytest


@pytest.fixture
def state():
    return {
        "tree": {"type": "group", "name": "", "visible": True, "expanded": True,
                 "children": [
                     {"type": "layer", "id": key, "visible": True, "expanded": True}
                     for key in ("roads", "parcels")]},
        "layers": {
            "roads": {"name": "Roads", "style": "<style color='red'/>", "filter": ""},
            "parcels": {"name": "Parcels", "style": "<style/>", "filter": ""},
        },
        "extent": [0, 0, 100, 100],
        "scale": 1000,
    }


@pytest.fixture
def variant(state):
    def make(index):
        result = deepcopy(state)
        result["layers"]["roads"]["style"] = f"<style version='{index}'/>"
        return result
    return make
