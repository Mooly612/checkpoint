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

### Milestone 3

- Added the plugin entry point, toolbar/menu toggle, and native history dock.
- Added Auto/Manual mode, adjustable minimum gap, and manual save in both modes.
- Added one signal-driven scheduling timer with two-second debounce and no
  periodic snapshots. Pan/zoom events are not watched.
- Added nested restore suppression through the following event-loop turn.
- Connected new layers and disconnected removed layers and unloaded plugins.
- Added project lifecycle handling, first-save migration, and isolated histories
  after Save As or opening another project.
- Added an explicit maximum QGIS version of 4.99 and exact macOS install steps.
- Ran all 37 pure-core tests and three real-QGIS smoke scripts on QGIS 3.44.8,
  Qt 5.15.18, Python 3.12.11 using offscreen Qt.

This is now an installable development build. Restore history orchestration,
thumbnails, settings, and release packaging remain pending. Testing in the real
QGIS main window, plus QGIS 3.28 and Qt6/4.x runtime checks, is still required.
