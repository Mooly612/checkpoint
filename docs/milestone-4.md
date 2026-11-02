> Historical 0.1 engineering note. Current behavior is documented in [reference.md](reference.md).

# Milestone 4: restore flow

The dock uses an explicit Restore button. Row selection only chooses its target;
it is reserved for preview interaction in milestone 5.

The controller resolves a detached target, captures and commits a pinned
`before restore` entry, suppresses the watcher, applies the target, captures the
actual resulting state, and commits an unpinned result. The suppression guard
remains active through the next event-loop turn. There are no new QGIS snapshot
or signal APIs in this milestone; it uses the previously verified snapshot and
watcher interfaces documented in milestones 2 and 3.

The user approved an explicit deduplication exception for both restore events.
Auto/Manual append semantics are unchanged. Restore entries have distinct IDs,
retain the exact view, and use the existing version-1 storage schema. Normal ring
retention remains active, but pinned safety entries are never automatically evicted.

Failure boundaries:

- Capture or safety commit failure: abort before changing the map.
- Application failure: retain the safety entry and report possible partial changes.
- Result capture or commit failure: retain the safety entry, keep the applied map,
  and explicitly report that its result was not recorded.
- Deleted layers or rejected filters: show persistent message-bar notices and save
  them in the result description. Capture the actual result, not a copy of the target.

No automatic rollback is attempted after provider failures. The user can select
the pinned safety record and restore it through the same guarded flow. Restoring
map view is enabled; its Options control and pin/delete management follow in
milestone 6.

Validation: 41 pure-core pytest checks and four real-QGIS smoke scripts on
QGIS 3.44.8, Qt 5.15.18, Python 3.12.11. The restore script covers button selection,
unsaved and persisted histories, undoing restore, exact view recovery, unchanged
restore, Auto suppression, safety write failure, result write failure, partial
application, deleted layers, later-added layers, and disk reload. Tests run in an
isolated temporary profile, not the user's live project. QGIS 3.28/4.x runtime
validation and interactive desktop testing of the new Restore button remain open.
