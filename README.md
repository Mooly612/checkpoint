# Checkpoint

*Undo for your map styling.*

Checkpoint is a QGIS plugin in development. It will record the appearance of
the Layers panel and let you restore an earlier styling state inside the open
session. It is not a backup tool and does not protect against crashes or data loss.

## Development status

Milestones 1 through 3 are implemented. This is an installable development build
with a native history dock, Auto/Manual capture, and a signal-driven watcher.
The pure core has 37 passing tests. Three additional smoke scripts passed using
the installed QGIS 3.44.8 / Qt 5.15.18 / Python 3.12.11 runtime with offscreen Qt:
snapshot restoration, watcher scheduling, and plugin wiring with an iface harness.
The main QGIS desktop window has not yet been tested with the plugin enabled.

[Install and test the development build](docs/install.md).
The current panel captures and lists checkpoints. Restore actions are deliberately
introduced with the complete pre-restore safety flow in milestone 4.

The remaining milestones, in order, are:

4. Restore flow, including a pinned pre-restore state and message-bar integration.
5. Thumbnail rendering and the per-project two-second safety fuse.
6. Standard QGIS Options integration and history actions in the panel.
7. Release polish and the plugin ZIP packaging script.

The target is QGIS 3.28+ and 4.x using `qgis.PyQt` only. Metadata declares Qt6
support and an explicit maximum version of 4.99; QGIS 3.28 and 4.x runtime checks
are still outstanding. Snapshot APIs and watcher signals were checked against
the versioned 3.28 and 4.0 documentation. See the
[milestone 2](docs/milestone-2.md) and [milestone 3](docs/milestone-3.md) notes.
The plugin name must be checked on plugins.qgis.org before publication.

## Run the core tests

From this repository, with Python 3.10 or newer for the development tools:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Runtime core code uses only the Python standard library. Tests require pytest
and do not import or require QGIS. They cover changes and descriptions, view-only
deduplication, ring eviction, pins, migration, persistence, corruption, and
atomic-write failures.

The separate `tests/qgis_smoke.py`, `tests/qgis_watcher_smoke.py`, and
`tests/qgis_plugin_smoke.py` scripts are real-QGIS checks, not pytest tests. They
passed on 3.44.8. The plugin script substitutes only the desktop iface surface,
using actual QGIS projects, providers, canvas, message bar, and Qt widgets. It
checks project switching without modifying the user's open project.

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
pinning, renaming, deleting, and changing the limit for the future UI.

Saved history uses an atomic JSON replacement at
`root/<SHA-256 of absolute project path>/history.json`. The integration will
supply `QgsApplication.qgisSettingsDirPath()/checkpoint/` as `root`. No project
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
watcher guard is implemented; the user-facing restore controller is milestone 4.

View restoration applies the saved center/extent and then the saved scale,
ignoring the canvas scale lock for that operation. If the canvas size has
changed, its final extent can differ to accommodate the saved scale. No CRS
transformation is attempted because CRS history is outside v1.

## Planned v1 behavior and limitations

- Auto mode responds to changes with about two seconds of debounce. Its interval
  is a minimum gap, not a second periodic trigger. Manual save works in both modes.
- Restore matches layer IDs. Deleted layers are skipped with a notice. Layers
  added after a snapshot are left untouched.
- Every restore preserves a pinned before-restore state and records its result.
- Renaming or moving a project file loses access to its history because the
  storage key is the absolute project path. History is never stored inside a
  `.qgz` or alongside the project file.
- Memory and scratch layer features are not copied. A deleted memory layer cannot
  be recovered, and history cannot recreate its data after the session ends.
- Thumbnails of WMS/XYZ layers may be blank or partial.
- CRS, project settings, custom layer order, Map Themes, and data versioning
  are outside v1.

## Project

Author: Alen Alimzhanov, <mooly612@gmail.com>.

[Repository](https://github.com/Mooly612/checkpoint) ·
[Issue tracker](https://github.com/Mooly612/checkpoint/issues)

Copyright (C) 2026 Alen Alimzhanov. Licensed under the GNU General Public License,
version 2 or, at your option, any later version (`GPL-2.0-or-later`). See `LICENSE`.
