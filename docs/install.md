# Installation and first test

## Install from ZIP

1. Build with `python3 scripts/package.py` or obtain the release ZIP.
2. Open QGIS **Plugins → Manage and Install Plugins → Install from ZIP**.
3. Select `checkpoint.zip`, install it, and enable Checkpoint under Installed.
4. Restart QGIS after replacing an existing version so Python modules are reloaded.

If using a source symlink, keep it for development. Test ZIP installation in a
separate QGIS profile rather than replacing the symlink.

## Development installation

Find the active profile directory in the QGIS Python Console:

```python
from qgis.core import QgsApplication
print(QgsApplication.qgisSettingsDirPath())
```

With QGIS closed, link the repository's inner `checkpoint` package into that
profile's `python/plugins/checkpoint` directory. Do not overwrite an existing
folder or symlink. Start QGIS and enable the plugin. Restart after code updates.

## First test

Use a disposable project with two vector layers:

1. Choose Manual and save a checkpoint. Save again unchanged; no new entry appears.
2. Change a symbol, layer filter, and visibility; save another checkpoint.
3. With Previews enabled, inspect symbol samples and click a row to compare maps.
4. Select the first record and click Restore. Verify styling returns and two new
   entries appear, including pinned before restore. Restore that entry to undo.
5. Delete a layer, then restore a snapshot that included it. Check the skipped-layer
   message; data must not be recreated.
6. Pin and rename an entry. Cancel a deletion, then confirm another deletion.
7. Open Settings… and select Checkpoint. Change the buffer, interval, and map-view
   preference. Cancel once to verify settings are not applied; then apply them.
8. Turn previews off and save a changed state. History should work without new images.
9. Switch to Auto with a 5-second minimum gap. Make rapid changes, then wait. One
   settled checkpoint should appear; idle time and pan/zoom must not create more.
10. Save an unsaved project, reopen it, then use Save As to a new path. Original
    history persists at the original path and does not mix with the new path.

If previews time out, toggle Previews off/on and create a new checkpoint. Existing
empty previews are not regenerated. If errors occur, inspect **View → Panels →
Log Messages → Checkpoint** and report the traceback, QGIS version, and provider.
