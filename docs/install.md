# Install the milestone 6 development build

The local installation is QGIS 3.44.8-Solothurn with Qt 5.15.18 and Python 3.12.11.
The discovered profile is `default`. The current build saves, lists, and restores history with a pinned safety snapshot.

## Symlink into the QGIS profile on this Mac

1. In the QGIS Python Console, confirm the profile directory:

   ```python
   from qgis.core import QgsApplication
   print(QgsApplication.qgisSettingsDirPath())
   ```

   For the discovered profile, it should be
   `/Users/mooly612/Library/Application Support/QGIS/QGIS3/profiles/default/`.
   If QGIS prints a different path, use that profile's `python/plugins` directory.

2. Close QGIS. In Terminal, run:

   ```sh
   mkdir -p "/Users/mooly612/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins"
   ln -s "/Users/mooly612/Documents/Codex/2026-11-01/files-mentioned-by-the-user-checkpoint/outputs/checkpoint/checkpoint" "/Users/mooly612/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/checkpoint"
   ```

   The linked source is the inner `checkpoint` package containing `metadata.txt`.
   These commands intentionally do not overwrite an existing plugin folder or
   symlink. If `ln` reports that it exists, inspect that entry before replacing it.

3. Start QGIS, open **Plugins → Manage and Install Plugins → Installed**, and
   enable **Checkpoint**. The history dock appears on the right. The toolbar icon
   or **Plugins → Checkpoint** toggles it.

4. Restart QGIS after code updates so imported Python modules are reloaded.
   The symlink means no copying or ZIP installation is needed during development.

## First test

Use a disposable project with two layers:

1. Select **Manual** and click **Save checkpoint** to create an initial state.
2. Click again without changes. The message bar should say no styling changes,
   and the list should still contain one entry.
3. Change a layer's style, filter, visibility, or group position. Save again and
   inspect the time and change description.
4. Select **Auto**, set **Minimum gap** to `5 s`, and make several quick styling
   changes. One entry should appear after the changes settle and the minimum gap
   has elapsed. Leaving the map idle must not create more entries.
5. Pan or zoom without changing styling. No new checkpoint should appear. The
   manual button should also skip this view-only change.
6. Make a manual save while Auto is selected. It should work immediately even
   when the automatic minimum gap has not elapsed.
7. Save an unsaved project to a `.qgz`. Its in-memory history should remain in the
   list and move under the profile's `checkpoint` directory. Reopen it to confirm.
8. Use **Save As** with a new path, then open a different project. Neither should
   inherit the old path's history. Return to the original path to see its records.
9. Disable the plugin, then enable it again. There should be one dock and one
   toolbar action, with no duplicate automatic saves.

If an error appears, send its text and the traceback from
**View → Panels → Log Messages → Checkpoint**. The Python error details dialog
may also contain a traceback if loading the plugin itself fails.

## Test Restore

After restarting QGIS to load the updated code:

1. Save a checkpoint, change a layer's style and the map view, then select the old
   checkpoint. Selection alone must leave the map unchanged.
2. Click **Restore selected checkpoint** at the bottom of the dock. The old style
   and view should return. Two entries appear: pinned **before restore** and the
   new **Restored** result.
3. Select **before restore** and click Restore to recover the state from step 1.
4. In a disposable project, delete a layer after saving a checkpoint, then restore
   that checkpoint. The message bar should name the deleted layer; it is not recreated.
5. Leave Auto enabled and wait. Restore must not generate additional Auto entries.

History is not a backup of project files or layer data. Select a checkpoint to pin/unpin, rename, or delete it. Closing the dock does not turn Auto off. Select Manual or disable
the plugin to stop automatic capture.

## Test Previews

1. Restart QGIS and leave **Previews** checked. Old checkpoints will not acquire
   invented images; create a new checkpoint to start testing.
2. Change a point symbol's shape/color/size and save another checkpoint. Its row
   should show before/after samples even if the layer has only a few points.
3. Click that row. Compare the saved maps at the same extent in a representative
   neighborhood. Restore remains a separate button below the list.
4. Change several categories. At most two changed samples appear, with a count
   of additional symbol changes. Hover for their names.
5. Change only a filter or visibility. The description and map should explain the
   operation without identical symbol samples.
6. Uncheck Previews, change styling, and save. History still works without new
   images. Check it again to enable previews for subsequent checkpoints.
7. If a project exceeds the rendering budget, a persistent panel notice explains
   that previews are disabled for that project. Toggle off/on to retry.

## Settings

Click **Settings…**, then select **Checkpoint** in QGIS Options. Changes apply
when the dialog is accepted. Restart QGIS once after installing this code update.
