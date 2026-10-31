# Changelog

## 0.1.0 (unreleased)

### Milestone 1

- Added experimental plugin metadata and an SVG icon.
- Added deterministic tree, style, and filter hashing with readable descriptions.
- Excluded extent and scale from styling hashes while retaining them in history.
- Added atomic disk history and isolated in-memory unsaved-project histories.
- Added duplicate skipping, bounded unpinned history, pins, names, and deletion.
- Added migration on first save and preservation of pre-existing project history.
- Added pytest coverage without QGIS dependencies.

QGIS capture, restore, watcher, UI, thumbnails, settings, and release packaging
are not implemented in this milestone. This is not an installable plugin release.
