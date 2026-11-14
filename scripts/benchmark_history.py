#!/usr/bin/env python3
"""Compare legacy whole-file replacement with a transaction updating one record."""
from pathlib import Path
import json
import os
import sys
import tempfile
from time import perf_counter
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from checkpoint.core.store import HistoryStore

with tempfile.TemporaryDirectory(prefix='checkpoint-benchmark-') as directory:
    root = Path(directory)
    store = HistoryStore(root, '/benchmark.qgz')
    # 100 pinned/recovery-like records, each with 400 KB of image payload.
    records = []
    memory = HistoryStore(root)
    state = {'tree': {'type': 'group', 'name': '', 'visible': True, 'expanded': True, 'children': []},
             'layers': {}, 'extent': [0, 0, 1, 1], 'scale': 100}
    for i in range(100):
        record = memory.append_restore(state, before=True, target=str(i))
        record['preview'] = {'maps': {'after': 'x' * 400_000}}
        records.append(record)
    with store._transaction():
        store._commit(records)
    legacy = root / 'legacy.json'
    db_before = store.path.stat().st_size
    def legacy_rename():
        current = json.loads(legacy.read_text())
        current['records'][0]['name'] += 'x'
        data = json.dumps(current, separators=(',', ':'))
        candidate = root / 'candidate.json'
        with candidate.open('w') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(candidate, legacy)
    legacy.write_text(json.dumps({'version': 1, 'records': records}, separators=(',', ':')))
    results = {}
    for label, operation in [('legacy_json_rename', legacy_rename), ('sqlite_rename', lambda: store.rename(records[0]['id'], 'renamed'))]:
        timings = []
        for _ in range(3):
            started = perf_counter(); operation(); timings.append(round((perf_counter()-started)*1000, 2))
        results[label + '_ms'] = timings
    results.update(records=100, image_bytes_per_record=400_000, database_bytes=db_before,
                   legacy_bytes=legacy.stat().st_size)
    print(json.dumps(results, indent=2))
