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

### Milestone 2

- Added QGIS capture and restore with a plain-data boundary.
- Captured nested groups, layer order, local visibility, and expanded state.
- Added full style XML and vector/point-cloud subset filter restoration.
- Added optional extent and scale restoration, including scale-locked canvases.
- Preserved later layers and skipped deleted IDs with plain notices for the UI.
- Prepared replacement trees before mutation and inserted new references before
  removing old nodes to avoid layer registry deletion.
- Added API references and an opt-in real-QGIS smoke script, not yet executed.

The pure core passes 37 tests. Snapshot integration is not runtime-tested in
QGIS. Watcher, UI, restore history orchestration, thumbnails, settings, and
release packaging are still pending. This is not an installable plugin release.
