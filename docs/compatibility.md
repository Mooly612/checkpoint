# Checkpoint 0.3.0 compatibility

One pure-Python ZIP targets macOS, Windows and Linux. It uses the Qt binding
provided by QGIS through `qgis.PyQt`; QGIS, Qt and Python are not included in it.
The plugin remains experimental while the new matrix is being validated.

## Release policy

Targets: stable QGIS 3.44 / Qt5 and QGIS 4.0, 4.2 / Qt6. No QGIS 2, older 3.x,
nightly, Master, beta or RC builds. The runtime gate rejects odd development
minor versions, patch 99, explicit prerelease markers and unvalidated release
lines. Metadata caps discovery at 4.2.99; patch 99 is still rejected at runtime.
The range shown by the QGIS Plugin Manager cannot express all these exclusions.
Future releases require native verification and an explicit policy update.

## Verification status

The table records completed execution, not just intended compatibility.

| Environment | Target | Status |
| --- | --- | --- |
| macOS arm64, local QGIS.app | 3.44.8 / Qt 5.15.18 / Python 3.12.11 | All 11 native ZIP scenarios passed; process exit 0 |
| Linux, official QGIS Docker images | 3.44-noble and 4.2 | CI configured; execution pending |
| Windows, official standalone MSI | 3.44.15, 4.0.3, 4.2.3 | CI configured; execution pending |
| macOS, Homebrew official QGIS bundles | 3.44 LTR and 4.2 | CI configured; execution pending |

The workflow also runs pure Python tests, SQLite concurrency, malicious XML checks,
Bandit and reproducible packaging across all three OS runners and Python
3.10/3.12/3.14. Passing these alone does not establish QGIS/Qt runtime compatibility.

Native jobs install the extracted release ZIP into a temporary directory and
create an isolated QGIS profile. They exercise capture/apply, recovery and Undo,
group metadata, filtering, CRS, preview rendering, UI/settings, reopen and teardown.
They use real QGIS widgets with a small interface harness, not a live desktop
session. Installation wizard clicks, display-specific rendering, macOS Intel,
Windows ARM, every Linux distribution and remote data sources are not covered.
CI logs and `runtime.json` artifacts identify the actual OS, QGIS, Qt and Python.
A missing report, failed installation, failed check or process crash is not a pass.

The macOS jobs follow the stable Homebrew casks. An unexpected release fails
the version assertion instead of silently expanding support. Windows MSI versions
are pinned and their SHA-256 checksums verified against QGIS's sidecar files.
Linux images follow pinned release lines, never `latest` or nightly.

## Existing history

The SQLite and snapshot schemas are unchanged. Existing history remains in its
QGIS profile, and JSON export remains available. QGIS 4 can use a separate profile
directory from QGIS 3: seeing empty history there does not mean it was deleted.
This update does not migrate profiles or merge histories between installations.
QGIS's own style XML may evolve; history created by a newer QGIS is not promised
to round-trip into an older QGIS. Retain the original project and profile backup
when moving between major versions.

## Run locally

```sh
python3 scripts/package.py
python3 scripts/run_qgis_macos.py --app /Applications/QGIS.app \
  --package dist/checkpoint-0.3.0.zip --expected-qgis 3.44 \
  --report dist/reports/macos-3.44.json
```

Use `scripts/run_qgis_checks.py` directly from a configured QGIS Python environment
on Linux or an OSGeo4W Shell on Windows. The Windows CI installer script is for
disposable runners only; normal users should use QGIS's standard installer.
