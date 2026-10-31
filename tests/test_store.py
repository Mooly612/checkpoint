from copy import deepcopy
import json

import pytest

from checkpoint.core.store import HistoryError, HistoryStore, project_key


def test_ring_evicts_oldest_unpinned(tmp_path, variant):
    store = HistoryStore(tmp_path, limit=2)
    records = [store.append(variant(index)) for index in range(4)]
    assert [r["id"] for r in store.records] == [r["id"] for r in records[-2:]]


def test_pinned_records_do_not_count_toward_limit(tmp_path, variant):
    store = HistoryStore(tmp_path, limit=1)
    pinned = [store.append(variant(index), pinned=True) for index in range(3)]
    store.append(variant(3))
    latest = store.append(variant(4))
    assert [r["id"] for r in store.records] == [r["id"] for r in pinned + [latest]]
    store.set_limit(2)
    assert len(store.records) == 4


def test_duplicate_and_view_only_changes_skipped(tmp_path, state):
    store = HistoryStore(tmp_path)
    original = store.append(state)
    assert store.append(state) is None
    moved = deepcopy(state)
    moved.update(extent=[1, 2, 3, 4], scale=500)
    assert store.append(moved) is None
    assert store.records == [original]


def test_return_to_earlier_state_is_recorded(tmp_path, variant):
    store = HistoryStore(tmp_path)
    for index in (1, 2, 1):
        assert store.append(variant(index)) is not None
    assert len(store.records) == 3


def test_unsaved_projects_are_isolated_and_never_write(tmp_path, state):
    root = tmp_path / "history"
    first, second = HistoryStore(root), HistoryStore(root)
    first.append(state)
    assert first.key != second.key
    assert not second.records
    assert not root.exists()


def test_migration_preserves_ids_names_pins_and_view(tmp_path, state):
    store = HistoryStore(tmp_path / "settings" / "checkpoint")
    original = store.append(state, pinned=True, name="Good map")
    temporary_key = store.key
    project = str(tmp_path / "map.qgz")
    store.migrate(project)
    assert store.key == project_key(project)
    assert store.saved
    assert store.records == [original]
    assert HistoryStore(store.root, project).records == [original]
    assert not (store.root / temporary_key).exists()
    assert not (tmp_path / "map.qgz").exists()


def test_migration_preserves_existing_history(tmp_path, variant):
    project = str(tmp_path / "existing.qgz")
    saved = HistoryStore(tmp_path / "history", project)
    existing = saved.append(variant(1), pinned=True)
    memory = HistoryStore(saved.root)
    new = memory.append(variant(2))
    memory.migrate(project)
    assert memory.records == [existing, new]
    assert HistoryStore(saved.root, project).records == [existing, new]


def test_pin_rename_unpin_delete_are_persisted(tmp_path, variant):
    store = HistoryStore(tmp_path, "/projects/map.qgz", limit=1)
    first = store.append(variant(1))
    store.set_pinned(first["id"], True)
    store.rename(first["id"], "  Presentation  ")
    second = store.append(variant(2), pinned=True)
    assert HistoryStore(tmp_path, "/projects/map.qgz").records[0]["name"] == "Presentation"
    store.set_pinned(first["id"], False)
    store.append(variant(3))
    assert first["id"] not in [r["id"] for r in store.records]
    store.delete(second["id"])
    assert len(HistoryStore(tmp_path, "/projects/map.qgz").records) == 1


def test_data_is_detached(tmp_path, state):
    store = HistoryStore(tmp_path)
    record = store.append(state)
    state["layers"].clear()
    record["state"]["layers"].clear()
    exposed = store.records
    exposed[0]["state"]["layers"].clear()
    assert len(store.records[0]["state"]["layers"]) == 2


@pytest.mark.parametrize("limit", [0, -1, 2.5, True])
def test_invalid_buffer_size(tmp_path, limit):
    with pytest.raises(ValueError):
        HistoryStore(tmp_path, limit=limit)


def test_limit_change_immediately_evicts(tmp_path, variant):
    store = HistoryStore(tmp_path)
    for index in range(4):
        store.append(variant(index), pinned=index == 0)
    store.set_limit(1)
    assert len(store.records) == 2
    assert store.records[0]["pinned"]


def test_project_key_uses_absolute_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert project_key("map.qgz") == project_key(str(tmp_path / "map.qgz"))
    assert project_key("map.qgz") != project_key("renamed.qgz")
    with pytest.raises(ValueError):
        project_key("")


@pytest.mark.parametrize("operation", ["delete", "rename", "set_pinned"])
def test_unknown_record_raises(tmp_path, operation):
    store = HistoryStore(tmp_path)
    args = {"delete": (), "rename": ("Name",), "set_pinned": (True,)}
    with pytest.raises(KeyError):
        getattr(store, operation)("missing", *args[operation])


@pytest.mark.parametrize("damage", ["json", "version", "state_hash", "state"])
def test_corrupt_history_is_reported_without_overwriting(tmp_path, state, damage):
    store = HistoryStore(tmp_path, "/projects/map.qgz")
    store.append(state)
    payload = json.loads(store.path.read_text())
    if damage == "version":
        payload["version"] = 900
    elif damage == "state_hash":
        payload["records"][0]["state_hash"] = "wrong"
    elif damage == "state":
        del payload["records"][0]["state"]["tree"]
    content = "broken JSON" if damage == "json" else json.dumps(payload)
    store.path.write_text(content)
    with pytest.raises(HistoryError):
        HistoryStore(tmp_path, "/projects/map.qgz")
    assert store.path.read_text() == content


def test_failed_atomic_write_keeps_disk_and_memory(tmp_path, variant, monkeypatch):
    store = HistoryStore(tmp_path, "/projects/map.qgz")
    store.append(variant(1))
    old_records, old_file = store.records, store.path.read_bytes()

    def fail(*args):
        raise OSError("Disk full")

    monkeypatch.setattr("checkpoint.core.store.os.replace", fail)
    with pytest.raises(OSError, match="Disk full"):
        store.append(variant(2))
    assert store.records == old_records
    assert store.path.read_bytes() == old_file
    assert list(store.path.parent.iterdir()) == [store.path]


def test_failed_migration_keeps_memory(tmp_path, state, monkeypatch):
    store = HistoryStore(tmp_path)
    store.append(state)
    original, key = store.records, store.key

    def fail(*args):
        raise OSError("Permission denied")

    monkeypatch.setattr("checkpoint.core.store.os.replace", fail)
    with pytest.raises(OSError):
        store.migrate("/projects/map.qgz")
    assert not store.saved
    assert store.key == key
    assert store.records == original


def test_migration_requires_first_save(tmp_path):
    with pytest.raises(ValueError):
        HistoryStore(tmp_path).migrate("")
    with pytest.raises(ValueError):
        HistoryStore(tmp_path, "/projects/map.qgz").migrate("/projects/renamed.qgz")
