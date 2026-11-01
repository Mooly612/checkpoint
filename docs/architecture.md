# Architecture and data contract

## Plain-data contract

`checkpoint/core/differ.py` consumes snapshots with this structure:

```python
{
    "tree": {
        "type": "group", "name": "", "visible": True, "expanded": True,
        "children": [
            {"type": "layer", "id": "layer-id", "visible": True, "expanded": False}
        ],
    },
    "layers": {
        "layer-id": {"name": "Roads", "style": "<qgis>...</qgis>", "filter": ""}
    },
    "extent": [0.0, 0.0, 100.0, 100.0],
    "scale": 1000.0,
}
```

Groups can contain nested groups and layer nodes. `visible` is the node's own
checkbox state. Layer display names live in the layer dictionary, not tree
nodes. SHA-256 hashes cover the tree, each layer's style XML, and each filter.
Extent, scale, and display names do not participate in the state hash. Group
names, child order, visibility, and expanded state do participate.

`HistoryStore(root, project_path="", limit=20)` returns detached plain records.
Its `append` method returns a new record or `None` when its styling hash matches
the latest record. Returning to an older state after an intervening change is
recorded. Records contain UTC timestamps, IDs, component and state hashes,
descriptions, names, pin flags, and the complete plain snapshot.

Only unpinned records count toward the buffer limit. Pins survive automatic
eviction; users can explicitly delete them. The storage API already supports
pinning, renaming, deleting, and changing the limit and the panel actions.

Saved history uses an atomic JSON replacement at
`root/<SHA-256 of absolute project path>/history.json`. The plugin supplies `QgsApplication.qgisSettingsDirPath()/checkpoint/` as `root`. No project
file or data source is modified. Malformed history raises `HistoryError` and is
not silently discarded or overwritten.

Unsaved projects use isolated temporary keys and remain entirely in memory.
`migrate(project_path)` writes them to disk on first save, retaining any history
already present at that path and applying the unpinned limit. Failed writes
leave the in-memory session intact. Merging existing session histories retains
their distinct records, including pins; deduplication applies when appending
a newly captured state.

The plugin pauses capture on `fileNameChanged` and commits migration after
`projectSaved` confirms the save. Opening a project also emits filename changes,
so `iface.projectRead` instead starts a separate history session. A failed save
after a path change leaves capture paused; completing the save resumes it.

## Capture and restore API

`snapshot.capture(project, canvas)` returns the plain snapshot above, including
full `QgsMapLayerStyle` XML for every registered layer. Vector and point-cloud
layers supply `subsetString`; other layer types use an empty filter value.

`snapshot.restore(project, canvas, state, restore_view=True)` restores existing
layers by ID and returns a list of plain notice strings. Deleted layers are
skipped. A rejected provider filter is reported. The caller can disable view
restoration without changing the saved extent or scale. Both functions require
the QGIS GUI thread.

The replacement tree is prepared before changing the live project. All new
nodes are inserted before old nodes are removed, so live layers retain tree
references throughout the replacement. Later layers retain their styles,
filters, local checkboxes, and group paths. Their sibling positions are used as
insertion points among the restored nodes. Group matching uses parent path,
name, and occurrence among same-named siblings, since groups have no layer IDs.
Restoring a shared parent's visibility naturally affects all its descendants.
QGIS 4 custom nodes are preserved but are not captured or hashed.

Canvas rendering is paused during application and its prior frozen state is
restored in `finally`. Style XML is checked before any mutation. QGIS's
`writeToLayer` does not return an import-success flag, so provider-specific
style behavior still requires runtime testing. This low-level API does not
implement transactional rollback or record history: the controller must save
the pinned pre-restore state and suppress the watcher before calling it. The
controller now implements this safety flow and watcher guard.

View restoration applies the saved center/extent and then the saved scale,
ignoring the canvas scale lock for that operation. If the canvas size has
changed, its final extent can differ to accommodate the saved scale. No CRS
transformation is attempted because CRS history is outside v1.

