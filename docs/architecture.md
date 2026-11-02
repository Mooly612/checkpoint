# Architecture, version 0.2

The plugin is a native Qt/QGIS dock. `plugin.py` owns session readiness, application
recovery, current-state scope, Save As choices and preview lifecycle.

- `core/snapshot.py`: GUI-thread snapshot schema 2; native group shells and stable
  IDs, non-destructive legacy handling, preflight, optional CRS-aware map view.
- `core/store.py`: pure Python SQLite transactions and isolated memory stores;
  legacy JSON validation, bounded ordinary history, separate recovery retention.
- `core/watcher.py`: QGIS signals, 2-second quiet period, minimum interval and
  nested application suppression. Expansion/pan/zoom do not schedule captures.
- `core/differ.py`: deterministic hashes, historical descriptions and prospective
  application scope. Extent/scale do not create styling-only history entries.
- `core/thumbnail.py`: provider-free renderer XML samples, optional cloned map
  providers, QGIS rendering jobs, soft timeout, cancellation ownership.
- `ui/panel.py`: stable list items, inline scope, explicit Preview/Apply/Undo.
- `ui/settings.py`: standard QGIS options page. UI uses the user's native theme.

The controller validates the target, commits a recovery snapshot, applies under
watcher suppression, records the result and marks recovery outcome. On any failure
it keeps the already committed recovery. The view is an independent optional step.

Database format 2 stores one record per row and settings/revision separately.
Every mutation acquires a SQLite write transaction before reading current state.
The original JSON is a retained migration input, never a second active writer.

See [reference](reference.md) for the exact supported contract, conflict policy,
retention, schema compatibility and API sources. Older milestone reports describe
0.1 and are retained as historical engineering notes, not current product behavior.
