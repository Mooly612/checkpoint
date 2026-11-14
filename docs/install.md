# Install Checkpoint 0.3.1

## From the prepared ZIP

Build the ZIP from a source checkout using `python3 scripts/package.py`. This
creates `dist/checkpoint-0.3.1.zip` and `dist/checkpoint-0.3.1.zip.sha256`.
The `dist/` directory is not committed to GitHub; there is no GitHub Release yet.
From the `dist` directory, verify with `shasum -a 256 -c checkpoint-0.3.1.zip.sha256`
on macOS, or `sha256sum -c checkpoint-0.3.1.zip.sha256` on Linux.
On Windows PowerShell, run `Get-FileHash .\checkpoint-0.3.1.zip -Algorithm SHA256`
and compare the hash with the first field of the `.sha256` file.

1. Open **Plugins → Manage and Install Plugins → Install from ZIP** in QGIS.
2. Choose `checkpoint-0.3.1.zip` and install. Enable Checkpoint under Installed.
3. Restart QGIS after replacing an existing version.
4. Open a project and confirm the starting checkpoint/status before editing.
5. Change two layers, select the starting point, read its inline scope, click
   **Apply saved map styling**, then **Undo last application**.

Targets stable QGIS 3.44 / Qt5 and QGIS 4.0, 4.2 / Qt6 on macOS, Windows and
Linux. Development builds and unvalidated release lines are refused before styling
can change. See [compatibility](compatibility.md) for actual verification status.

The ZIP has one top-level `checkpoint/` directory, includes the synthetic `demo/`
project and its GeoJSON sources, and needs no extra Python
packages. It is experimental. See the compatibility report for native test coverage.
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
python3 scripts/run_qgis_checks.py --package dist/checkpoint-0.3.1.zip
```

For macOS, use the Python bundled with the selected QGIS application:

```sh
python3 scripts/run_qgis_macos.py --app /Applications/QGIS.app \
  --package dist/checkpoint-0.3.1.zip --expected-qgis 3.44 \
  --report dist/reports/macos-3.44.json
```

The runner creates a temporary QGIS profile, extracts the package into a temporary
plugin installation, verifies the imported path, and uses separate projects and
canvases. It never touches the open project or active user profile. This checks
package loading and plugin lifecycle, not the interactive Plugin Manager wizard.

If history saving fails, read the status/message bar and retry **Save checkpoint**.
If maps are unavailable, use **Retry maps** or leave maps off. Full details are in
**View → Panels → Log Messages → Checkpoint**.
