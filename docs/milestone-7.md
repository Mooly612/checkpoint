# Milestone 7: experimental release build

Version: 0.1.0. All seven implementation milestones are complete. This milestone
creates a local installable release artifact; it does not publish a catalog entry,
GitHub release, or git tag.

The metadata now describes implemented functionality instead of pending features.
The README focuses on installation, use, storage, preview behavior, recovery, and
limitations; detailed data/API material moved to architecture.md. The existing
small SVG layer-stack icon is retained and validated through QGIS's Qt SVG loader.

`python3 scripts/package.py` produces `dist/checkpoint.zip` and its SHA-256 sidecar.
The archive contains one checkpoint directory with runtime Python, metadata, icon,
GPL license, changelog, README, and Markdown documentation. Sorted members, fixed
ZIP timestamps and permissions make builds reproducible. Python syntax, required
metadata/files, and ZIP integrity are checked before atomic replacement. Tests,
bytecode, hidden files, history, source data, and development scripts are excluded.

Validation comprises 44 pytest tests and all six real-QGIS smoke scripts, using
QGIS 3.44.8 / Qt 5.15.18 / Python 3.12.11. The QGIS runner extracts the release ZIP,
asserts imports resolve inside that extracted copy, and uses a disposable profile.
It checks settings/history actions, snapshot restoration, watcher timing, lifecycle,
safe Restore, previews and cancellation. It does not automate the interactive QGIS
plugin install dialog. No user project or active profile is modified by these checks.

The name search on 2026-11-02 found no indexed QGIS plugin called Checkpoint.
The catalog's direct search endpoint was inaccessible through the search tool;
absence from search results is not definitive name clearance. Recheck at upload.
Reference: https://plugins.qgis.org/plugins/

Remaining validation limits: QGIS 3.28 and QGIS 4/Qt6 have not been run; slow remote
providers and the user's original heavy project still need interactive testing.
The release remains experimental and the README discloses these limits.
