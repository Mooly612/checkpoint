> Historical 0.1 engineering note. Current behavior is documented in [reference.md](reference.md).

# Milestone 6

Open the standard QGIS Options dialog using **Settings…** in the dock, then select
**Checkpoint**. The page offers previews, Restore map view, unpinned history limit,
and default automatic interval. Applying also updates the active panel and history
limit; lowering the limit immediately evicts the oldest unpinned records. Pinned
entries are retained. Cancelling the options dialog does not apply page edits.

Select a record to use Pin/Unpin, Rename, or Delete. Delete has a confirmation with
No as its default, including an explicit notice for pinned entries. Empty names
restore the generated description. Storage failures leave the old history intact.

The preview checkbox shares its existing QgsSettings key with the dock. A heavy
project's safety fuse is still reset by toggling Previews off/on in the dock.

API references:
- https://api.qgis.org/api/3.28/classQgsOptionsWidgetFactory.html
- https://api.qgis.org/api/4.0/classQgsOptionsPageWidget.html

The new settings smoke script uses actual QGIS options widgets with an iface
harness. It checks apply, persisted settings, pinning, renaming, delete cancellation,
confirmed deletion, and factory unregistering. QGIS 3.28/4.x runtime checks remain
outstanding; local validation uses QGIS 3.44.8 / Qt 5.15.18.
