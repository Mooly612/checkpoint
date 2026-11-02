# Install Checkpoint 0.2.2

## From the prepared ZIP

The local artifact is `dist/checkpoint-0.2.2.zip`. Its checksum is in
`dist/checkpoint-0.2.2.zip.sha256`. No hosted release download is available.
From the `dist` directory, verify with `shasum -a 256 -c checkpoint-0.2.2.zip.sha256`
on macOS, or `sha256sum -c checkpoint-0.2.2.zip.sha256` on Linux.

1. Open **Plugins → Manage and Install Plugins → Install from ZIP** in QGIS.
2. Choose `checkpoint-0.2.2.zip` and install. Enable Checkpoint under Installed.
3. Restart QGIS after replacing an existing version.
4. Open a project and confirm the starting checkpoint/status before editing.
5. Change two layers, select the starting point, read its inline scope, click
   **Apply saved map styling**, then **Undo last application**.

QGIS 3.44 or newer within the 3.x series, with Qt5, is required. Earlier QGIS
versions and Qt6/QGIS4 are refused before styling can change.

The ZIP has one top-level `checkpoint/` directory, includes the synthetic `demo/`
project and its GeoJSON sources, and needs no extra Python
packages. It is experimental. Runtime-verified here on QGIS 3.44.8 / Qt5 on macOS.
Do not install over a development symlink; use a separate QGIS profile for ZIP
validation.

## Build from source

Python 3.9+ can package the plugin without QGIS:

```sh
python3 scripts/package.py
```

The builder reads the version from metadata, validates Python syntax and required
files, excludes development artifacts, fixes ZIP timestamps/permissions, and
writes the SHA-256 sidecar. Repeated builds from unchanged input are byte-identical.

## Existing history

Version 0.1 JSON is validated and imported transactionally on the first change.
The original `history.json` is retained. Old pins, names, IDs, images and snapshots
are preserved. Old snapshots keep the current tree and skip unknown-CRS views,
with notices. Do not run 0.1 and 0.2 writers against the same profile: the old
plugin does not know about SQLite or newer entries.

## Development and checks

The source-symlink workflow belongs in a development profile. Find its directory
with `QgsApplication.qgisSettingsDirPath()` in the QGIS Python console. With that
QGIS instance closed, link the repository's inner `checkpoint` package into the
profile's `python/plugins/checkpoint`, without overwriting an existing directory.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
python3 scripts/package.py
# Use the Python interpreter supplied by a working QGIS installation:
python3 scripts/run_qgis_checks.py --package dist/checkpoint-0.2.2.zip
```

For the tested macOS QGIS.app bundle (its executable is named python3.12):

```sh
env PYTHONHOME=/Applications/QGIS.app/Contents/Frameworks \
  PYTHONPATH=/Applications/QGIS.app/Contents/Resources/python3.11/site-packages \
  /Applications/QGIS.app/Contents/MacOS/python3.12 \
  scripts/run_qgis_checks.py --package dist/checkpoint-0.2.2.zip
```

The runner creates a temporary QGIS profile, extracts the package into a temporary
plugin installation, verifies the imported path, and uses separate projects and
canvases. It never touches the open project or active user profile. This checks
package loading and plugin lifecycle, not the interactive Plugin Manager wizard.

If history saving fails, read the status/message bar and retry **Save checkpoint**.
If maps are unavailable, use **Retry maps** or leave maps off. Full details are in
**View → Panels → Log Messages → Checkpoint**.
