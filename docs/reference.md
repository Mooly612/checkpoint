# Checkpoint 0.2.0 reference

## Snapshot contract

| Saved state | Application behavior |
| --- | --- |
| Existing layer IDs and opaque `QgsMapLayerStyle` XML | Apply full saved style, including supported labels and rendering properties |
| Vector/point-cloud subset strings | Ask the provider to apply the filter; report rejection |
| Tree order, nesting, group names, local visibility, expansion | Rebuild supported nodes; retain later layers and groups |
| Native group XML metadata | Restore mutually exclusive selection, typed custom properties and QGIS-serialized server/WMS properties |
| Group UUID in `checkpoint/group-id` | Identify renamed/moved/duplicate-named groups; persists in the project on normal save |
| Extent, scale, destination CRS WKT | Transform center/extent if needed, preserve scale denominator, never switch project CRS |

Newly introduced group custom-property keys absent from a snapshot are retained.
Existing keys in the snapshot revert to their saved values. This is deliberately
not an exact rollback of arbitrary third-party plugin state. Layer-tree layer
nodes clone their current custom metadata; their supported saved flags are then
applied. Root capture explicitly dispatches the base group XML writer, because the root
tree writer omits inherited group fields. Application uses QGIS native
common/server-property APIs.

Group layers, embedded nodes and unknown custom nodes are unsupported. Capture
or application refuses these before changing styling. No layer is recreated from
its name. Later layers remain in the registry; a saved parent group's visibility
or exclusive selection can hide them. Empty later groups are retained as well.
Custom drawing order remains current, independently of tree order.

Legacy schema 1 snapshots contain neither group identity nor complete properties.
Their styles/filters can still be applied; the whole current tree is preserved
with a notice. Unknown-CRS views are skipped. Legacy history remains readable and
original JSON files are never overwritten.

For views, an unchanged CRS restores center and scale. A changed CRS transforms
the center and bounding box with the project's transform context, then restores
the saved scale denominator in the current CRS. A resized canvas has different
coverage at that scale. An invalid/unknown CRS, empty extent or transformation
error skips the view only. **Restore map view** off leaves it untouched.

## Session and Auto

Missing group identities after reopening an as-yet-unsaved UUID update can be
adopted from the latest entry only when the complete ordered tree, group names
and layer IDs match. Existing identities are never replaced.

A completed project opening or enabling in an already open project creates a
starting checkpoint when needed. The latest identical styling snapshot is not
appended again. During project loading/path changes, capture is paused. Empty
projects show that there is no starting point yet. Adding the first layers in
Auto schedules capture after that layer-add event completes.

Auto waits for a 2-second quiet period in tracked changes, and also for the
configured minimum gap since the last save. Changes are coalesced. Idle time,
pan/zoom and expanding/collapsing a group alone do not create entries. Expansion
is retained when another change or an explicit save captures the snapshot.

A failed starting save leaves a clear unavailable state. Save checkpoint retries;
no protected/active state is shown until a capture succeeds. Manual, Auto and
memory-only unsaved-project states are explicit. Closing the dock does not pause
Auto; selecting Manual does.

## Apply, Undo and cleanup

Selection updates the prospective summary from the current project. The list
text and Preview describe historical changes. Application validates first, then
commits a recovery state before any styling mutation. Safety-write failure aborts.
After application, the resulting state is recorded. Provider notices, partial
exceptions and failed result writes leave recovery available. There is no automatic
rollback that might itself fail silently.

Every application has an event UUID. Its `recovery` record is separate from user
`pinned` status and names the target. **Undo last application** applies the latest
available recovery, first preserving the current state. It also makes undoing that
operation possible. A previous recovery is marked undone only on complete success.

Ordinary entries use the configured limit (default 20). All recovery records are
protected from ordinary eviction. Explicit cleanup removes older completed/undone
recoveries, retaining the latest 10, unresolved/partial recoveries and every user
pin. No automatic cleanup deletes old pins. A deliberate per-record Delete asks
for confirmation and explains recovery loss. Pin reflects its selected state.

## Storage, concurrency and portability

`QgsApplication.qgisSettingsDirPath()/checkpoint/<sha256-of-absolute-project-path>/history.sqlite3`
contains database version 2. Snapshot schema 2 is independent of database format.
The legacy `history.json` is imported under the same SQLite transaction as the
first mutation and retained unchanged. Unsupported/corrupt histories are refused. New snapshot style hashes normalize
XML attribute ordering (including native embedded callout symbols), preventing
duplicate startup records across QGIS
processes. The original style XML is still stored verbatim for application; old
schema-1 hashes retain their original validation.

SQLite `BEGIN IMMEDIATE` serializes all mutations. Read the latest revision only
after acquiring the write lock, then append/update/delete against that state.
Busy waits use a 150 ms timeout; filesystem I/O has no hard latency guarantee.
On failure, the transaction rolls back and the previous in-memory view is retained.
Deleting an entry wins over a stale rename/pin/preview update, which raises a
missing-entry error. Same-field edits use the last successful transaction. Pins,
previews, limits, recovery status and first-save migration use this mechanism.

Only changed record rows are written. The persisted revision avoids re-reading
all images on repeated local edits. A changed revision from another process
refreshes the snapshot. Dock items are reused on preview/metadata updates.
**History… → Refresh history** picks up independent changes; mutations always do
so regardless of whether the UI was manually refreshed.

Unsaved projects are independent memory stores. First save persists their history.
If the destination already has independent history, migration refuses to merge and
keeps the memory history available for export. Save As on a saved project offers
copying history, starting new history, or using already-existing destination
history. Decide later pauses tracking until the next save/choice. The old history
remains untouched. A concurrent writer at the destination cannot be overwritten.

Export creates a versioned JSON archive. Import/remapping is deferred: matching
by names risks applying unrelated layers and sources. Sharing the project alone,
renaming/moving it outside QGIS or changing QGIS profiles does not transfer history.
Do not use two plugin major storage versions as writers in one profile.

## Previews and limitations

Text and renderer-XML symbol samples do not need a cloned data provider. Map
preparation clones relevant source layers on the GUI thread and QGIS owns the
render jobs. No QGIS objects are moved into an arbitrary Python worker thread.

Map preparation and render timing are separate in `preview.timings_ms`. The
2-second fuse is soft: a single synchronous source/clone/filter call can exceed
it before control returns. On failure, samples and text survive. A slow map pauses
future map rendering for that project. **Retry maps** creates a new capture using
current data; immutable existing images are not regenerated or relabeled.

Cancelled jobs and their detached layers remain owned until jobs finish. Late
callbacks are ignored after release, project switching or unload. Before/after
images have the same representative extent and use data available at capture time;
they are not a prediction of applying the record later.

Geometry, attributes, sources, project CRS/settings/files, layouts, Map Themes and
custom drawing order are outside the contract. Recovery cannot restore deleted
layers or data edits. There are no accounts, cloud sync or telemetry. UI and error
strings have translation boundaries; English is the only distributed language.

## API references

Native group serialization and exclusivity APIs were compared across the official
3.28, 3.40 and [QGIS 3.44 API](https://api.qgis.org/api/3.44/classQgsLayerTreeGroup.html).
Group server properties and WMS time-dimension methods were introduced in 3.44.
The minimum version is therefore QGIS 3.44, with Qt5; earlier versions and
Qt6/QGIS4 are refused before capture or application.
Execution checks used QGIS 3.44.8 only. See [validation](validation-0.2.0.md).
