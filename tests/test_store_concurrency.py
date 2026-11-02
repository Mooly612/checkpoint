"""Independent writers and process contention exercise real SQLite transactions."""
from copy import deepcopy
import json
import multiprocessing
import sqlite3
import time

import pytest

from checkpoint.core.store import HistoryError, HistoryStore


def _writer(root, path, state, ready, start, result):
    try:
        store = HistoryStore(root, path)
        ready.put(True)
        start.wait(10)
        for i in range(5):
            changed = deepcopy(state)
            changed['layers']['roads']['filter'] = str(i) + str(multiprocessing.current_process().pid)
            for attempt in range(10):
                try:
                    store.append(changed, pinned=True)
                    break
                except HistoryError:
                    time.sleep(.03)
            else:
                raise RuntimeError('Writer starved')
        result.put(None)
    except Exception as exc:
        result.put(repr(exc))


def test_independent_writers_preserve_pins_and_merge_operations(tmp_path, variant):
    a, b = [HistoryStore(tmp_path, '/map.qgz') for _ in range(2)]
    first = a.append(variant(1), pinned=True)
    second = b.append(variant(2))
    a.rename(second['id'], 'renamed by A')
    b.set_pinned(second['id'], True)
    a.set_preview(first['id'], {'maps': {'after': 'immutable'}, 'samples': []})
    b.set_limit(1)
    a.append(variant(3))
    records = b.refresh()
    assert len(records) == 3
    assert records[0]['pinned'] and records[0]['preview']['maps']['after'] == 'immutable'
    assert records[1]['pinned'] and records[1]['name'] == 'renamed by A'
    assert a.limit == b.limit == 1


@pytest.mark.parametrize('operation,args', [('rename', ('no resurrection',)), ('set_pinned', (True,)),
                                          ('set_preview', ({'maps': {'after': 'late callback'}},)), ('delete', ())])
def test_delete_wins_over_stale_update(tmp_path, state, operation, args):
    a = HistoryStore(tmp_path, '/map.qgz')
    record = a.append(state)
    b = HistoryStore(tmp_path, '/map.qgz')
    a.delete(record['id'])
    with pytest.raises(KeyError):
        getattr(b, operation)(record['id'], *args)
    assert a.refresh() == []


def test_process_writers(tmp_path, state):
    ctx = multiprocessing.get_context('spawn')
    ready, result, start = ctx.Queue(), ctx.Queue(), ctx.Event()
    processes = [ctx.Process(target=_writer, args=(str(tmp_path), '/map.qgz', state, ready, start, result)) for _ in range(2)]
    for process in processes:
        process.start()
    try:
        for _ in processes:
            assert ready.get(timeout=10)
        start.set()
        for _ in processes:
            assert result.get(timeout=15) is None
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        records = HistoryStore(tmp_path, '/map.qgz').records
        assert len(records) == 10 and all(r['pinned'] for r in records)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join()


def test_busy_timeout_preserves_local_history_and_can_retry(tmp_path, variant):
    store = HistoryStore(tmp_path, '/map.qgz')
    store.append(variant(1))
    original = store.records
    db = sqlite3.connect(store.path)
    try:
        db.execute('BEGIN IMMEDIATE')
        started = time.monotonic()
        with pytest.raises(HistoryError, match='busy or storage error'):
            store.append(variant(2))
        assert time.monotonic() - started < 1
        assert store.records == original
    finally:
        db.rollback()
        db.close()
    store.append(variant(2))
    assert len(store.records) == 2


def test_real_sqlite_failure_rolls_back_memory_and_disk(tmp_path, variant):
    store = HistoryStore(tmp_path, '/map.qgz')
    record = store.append(variant(1))
    with sqlite3.connect(store.path) as db:
        db.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON records BEGIN SELECT RAISE(ABORT, 'injected storage failure'); END")
    with pytest.raises(HistoryError, match='injected storage failure'):
        store.append(variant(2))
    assert store.records == HistoryStore(tmp_path, '/map.qgz').records == [record]


def test_legacy_migrates_once_without_altering_original(tmp_path, variant):
    memory = HistoryStore(tmp_path)
    first = memory.append(variant(1), pinned=True, name='before restore')
    saved = HistoryStore(tmp_path, '/map.qgz')
    saved.legacy_path.parent.mkdir(parents=True)
    legacy = json.dumps({'version': 1, 'records': [first]})
    saved.legacy_path.write_text(legacy)
    a, b = [HistoryStore(tmp_path, '/map.qgz') for _ in range(2)]
    a.append(variant(2))
    b.append(variant(3))
    assert saved.refresh()[0] == first and len(saved.records) == 3
    assert saved.legacy_path.read_text() == legacy
    saved.cleanup_recovery(keep=1)
    assert saved.records[0]['pinned']


def test_recovery_cleanup_never_removes_unresolved_or_user_pins(tmp_path, variant):
    store = HistoryStore(tmp_path, '/map.qgz', limit=1)
    unresolved = store.append_restore(variant(0), before=True)
    partial = store.append_restore(variant(1), before=True)
    store.finish_recovery(partial['id'], 'partial')
    pinned = store.append_restore(variant(2), before=True)
    store.finish_recovery(pinned['id'], 'complete')
    store.set_pinned(pinned['id'], True)
    for i in range(3, 16):
        record = store.append_restore(variant(i), before=True, target='Map ' + str(i))
        store.finish_recovery(record['id'], 'complete')
    assert store.cleanup_recovery(keep=10) == 3
    ids = {r['id'] for r in store.records}
    assert {unresolved['id'], partial['id'], pinned['id'], record['id']} <= ids


def test_saved_maps_are_immutable_and_export_is_detached(tmp_path, state):
    store = HistoryStore(tmp_path, '/map.qgz')
    record = store.append(state)
    store.set_preview(record['id'], {'maps': {'after': 'first'}})
    with pytest.raises(HistoryError, match='immutable'):
        store.set_preview(record['id'], {'maps': {'after': 'different'}})
    output = tmp_path / 'export.json'
    store.export(output)
    assert json.loads(output.read_text())['records'] == store.records


def test_save_as_copy_keeps_source_and_refuses_existing_destination(tmp_path, variant):
    source = HistoryStore(tmp_path, '/one.qgz')
    first = source.append(variant(1), pinned=True)
    copy = source.copy_to('/two.qgz')
    copy.append(variant(2))
    assert source.refresh() == [first] and len(copy.records) == 2
    with pytest.raises(HistoryError, match='already has history'):
        source.copy_to('/two.qgz')


def test_failed_refresh_does_not_cache_an_invalid_revision(tmp_path, state):
    store = HistoryStore(tmp_path, '/map.qgz')
    record = store.append(state)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE settings SET value='999' WHERE key='revision'")
        db.execute("UPDATE records SET payload='{}'")
    for _ in range(2):
        with pytest.raises(HistoryError):
            store.refresh()
        assert store.records == [record]
