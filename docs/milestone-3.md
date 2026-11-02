> Historical 0.1 engineering note. Current behavior is documented in [reference.md](reference.md).

# Milestone 3 verification

## Implemented behavior

- The native dock contains Auto/Manual, a minimum interval in seconds, a manual
  save button, and a newest-first history list with local times and descriptions.
- One single-shot timer fires only after a dirty signal. Its deadline is the
  later of the last change plus two seconds or the last snapshot plus the chosen
  interval. Early timer delivery is checked against a monotonic clock.
- Manual save bypasses the scheduling delay, but uses the same hash-based
  deduplication. A successful duplicate check clears pending dirty work without
  moving the last-snapshot time. Errors do not start an endless retry loop.
- No canvas pan/zoom signals are connected. Changes made in Manual can be
  captured after switching to Auto. The first baseline can be saved explicitly.
- `Watcher.suppress()` is nestable, cancels pending capture, ignores restore
  signals, and resumes one event-loop turn later, including when restore raises.
  Its caller must handle pre/post restore history in milestone 4.
- Path changes pause capture. A successful project save migrates an unsaved
  history or switches a saved project's history key. The separate desktop
  project-read signal prevents migrating an old session into an opened project.
- Unload disconnects only the plugin's slots and stops pending timers.

## Signal/API references

| Source | Signals/API used | QGIS 3.28 | QGIS 4.0 |
| --- | --- | --- | --- |
| Layer tree | `addedChildren`, `removedChildren`, `visibilityChanged`, `expandedChanged`, `nameChanged` | [Reference](https://api.qgis.org/api/3.28/classQgsLayerTreeNode.html) | [Reference](https://api.qgis.org/api/4.0/classQgsLayerTreeNode.html) |
| Map layers | `styleChanged`, `rendererChanged` | [Reference](https://api.qgis.org/api/3.28/classQgsMapLayer.html) | [Reference](https://api.qgis.org/api/4.0/classQgsMapLayer.html) |
| Vector filters | `subsetStringChanged` | [Reference](https://api.qgis.org/api/3.28/classQgsVectorLayer.html) | [Reference](https://api.qgis.org/api/4.0/classQgsVectorLayer.html) |
| Point-cloud filters | `subsetStringChanged` | [Reference](https://api.qgis.org/api/3.28/classQgsPointCloudLayer.html) | [Members](https://api.qgis.org/api/4.0/classQgsPointCloudLayer-members.html) |
| Project lifecycle | `layersAdded`, `layersWillBeRemoved`, `cleared`, `fileNameChanged`, `projectSaved` | [Reference](https://api.qgis.org/api/3.28/classQgsProject.html) | [Reference](https://api.qgis.org/api/4.0/classQgsProject.html) |
| Desktop interface | `projectRead`, `newProjectCreated`, dock/menu/toolbar registration | [Reference](https://api.qgis.org/api/3.28/classQgisInterface.html) | [Reference](https://api.qgis.org/api/4.0/classQgisInterface.html) |

The layer-removal slot accepts both documented overload argument types. All Qt
imports use `qgis.PyQt`; the dock's own toggle action avoids Qt5/Qt6 QAction
module differences. Enums are fully qualified.

The explicit `qgisMaximumVersion=4.99` avoids the repository's implicit
major-version-plus-.99 upper bound when publishing, as described in the
[official plugin metadata guide](https://docs.qgis.org/3.40/en/docs/pyqgis_developer_cookbook/plugins/plugins.html).

## Results on 2026-11-01

Environment: macOS, QGIS 3.44.8-Solothurn, Qt 5.15.18, Python 3.12.11. The bundled
QGIS Python ran with the offscreen Qt platform, a workspace test profile, and
temporary projects. No plugin installation in the user's active profile was
performed.

| Check | Result |
| --- | --- |
| Pure-core pytest suite | 37 passed |
| `tests/qgis_smoke.py` | Passed: snapshot round trip, view options, extra/deleted layers, malformed XML, frozen canvas |
| `tests/qgis_watcher_smoke.py` | Passed: debounce restart, minimum gap, idle behavior, mode switch, new-layer filter, removal, nested suppression after an exception, shutdown |
| `tests/qgis_plugin_smoke.py` | Passed: factory, real dock widgets, manual/Auto capture, duplicate message, view-only skip, first-save migration, Save As, reopen, new project, unload |
| Python compilation and whitespace check | Passed |

The plugin smoke script uses a small iface harness instead of the real desktop
main window. Its project, memory providers, canvas, message bar, and widgets are
real QGIS/Qt objects. These checks do not establish compatibility with QGIS 3.28
or QGIS 4.x/Qt6. First use in the real desktop, visual style/provider coverage,
and those additional runtimes remain to be checked.

The smoke scripts can also be run from the QGIS Python Console after adding the
repository to `sys.path`, as shown in the milestone 2 notes. Each creates its own
project; the watcher check runs for about 25 seconds while processing Qt events.
