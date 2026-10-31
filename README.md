# Checkpoint

*Undo for your map styling.*

Checkpoint is a QGIS plugin in development. It will record the appearance of
the Layers panel and let you restore an earlier styling state inside the open
session. It is not a backup tool and does not protect against crashes or data loss.

## Development status

Milestone 1 is implemented: plugin metadata and icon, state hashing, change
descriptions, and history storage with pure Python tests. This scaffold is **not
yet installable in QGIS**. There is deliberately no `classFactory` or empty
plugin implementation pretending that integration is complete.

The remaining milestones, in order, are:

1. Capture and restore QGIS layer trees, full styles, filters, and map view.
2. Watcher and minimal dock panel, with Auto/Manual mode and restore suppression.
3. Restore flow, including a pinned pre-restore state and deleted-layer notices.
4. Thumbnail rendering and the per-project two-second safety fuse.
5. Standard QGIS Options integration and history actions in the panel.
6. Release polish and the plugin ZIP packaging script.

The target is QGIS 3.28+ and 4.x using `qgis.PyQt` only. The metadata declares
Qt6 support as specified, but QGIS integration and compatibility have **not**
been run or verified. Exact APIs and signals must be checked against official
3.28 and 4.x documentation before adding integration code. The installed QGIS
version and exact symlink installation steps will be addressed at milestone 3.
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
