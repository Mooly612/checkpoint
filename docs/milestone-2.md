# Milestone 2 verification

## Status

Implemented `checkpoint/core/snapshot.py`. During milestone 3, the smoke script
below passed against the installed QGIS 3.44.8 / Qt 5.15.18 runtime on the
offscreen Qt platform. The 37 pytest tests still cover only `differ` and `store`.
QGIS 3.28 and 4.x runtime checks and the broader visual/provider checks below
remain outstanding.

## API review

The following official versioned references were checked during implementation:

| Area | QGIS 3.28 | QGIS 4.0 | Calls used |
| --- | --- | --- | --- |
| Full styles | [QgsMapLayerStyle](https://api.qgis.org/api/3.28/classQgsMapLayerStyle.html) | [QgsMapLayerStyle](https://api.qgis.org/api/4.0/classQgsMapLayerStyle.html) | `readFromLayer`, `xmlData`, XML constructor, `isValid`, `writeToLayer` |
| Group construction | [QgsLayerTreeGroup](https://api.qgis.org/api/3.28/classQgsLayerTreeGroup.html) | [QgsLayerTreeGroup](https://api.qgis.org/api/4.0/classQgsLayerTreeGroup.html) | `addChildNode`, `insertChildNode(s)`, `removeChildNode`, `findLayers`, `findLayerIds` |
| Layer nodes | [QgsLayerTreeLayer](https://api.qgis.org/api/3.28/classQgsLayerTreeLayer.html) | [QgsLayerTreeLayer](https://api.qgis.org/api/4.0/classQgsLayerTreeLayer.html) | layer constructor, `layerId`, `clone` |
| Node flags | [QgsLayerTreeNode](https://api.qgis.org/api/3.28/classQgsLayerTreeNode.html) | [QgsLayerTreeNode](https://api.qgis.org/api/4.0/classQgsLayerTreeNode.html) | `children`, `name`, `itemVisibilityChecked`, `isExpanded`, flag setters |
| Vector filters | [QgsVectorLayer](https://api.qgis.org/api/3.28/classQgsVectorLayer.html) | [QgsVectorLayer](https://api.qgis.org/api/4.0/classQgsVectorLayer.html) | `subsetString`, boolean `setSubsetString` |
| Point-cloud filters | [QgsPointCloudLayer](https://api.qgis.org/api/3.28/classQgsPointCloudLayer.html) | [QgsPointCloudLayer members](https://api.qgis.org/api/4.0/classQgsPointCloudLayer-members.html) | `subsetString`, `setSubsetString` |
| Project | [QgsProject](https://api.qgis.org/api/3.28/classQgsProject.html) | [QgsProject](https://api.qgis.org/api/4.0/classQgsProject.html) | `mapLayers`, `layerTreeRoot`, `setDirty` |
| Canvas | [QgsMapCanvas](https://api.qgis.org/api/3.28/classQgsMapCanvas.html) | [QgsMapCanvas](https://api.qgis.org/api/4.0/classQgsMapCanvas.html) | `extent`, `scale`, `setExtent`, `zoomScale`, `freeze`, `isFrozen`, `stopRendering`, `refresh` |
| Extent | [QgsRectangle](https://api.qgis.org/api/3.28/classQgsRectangle.html) | [QgsRectangle](https://api.qgis.org/api/4.0/classQgsRectangle.html) | coordinate getters and four-coordinate constructor |

The registry bridge removes map layers when their last tree reference disappears
([3.28](https://api.qgis.org/api/3.28/classQgsLayerTreeRegistryBridge.html),
[4.0](https://api.qgis.org/api/4.0/classQgsLayerTreeRegistryBridge.html)). The
[4.0 implementation](https://api.qgis.org/api/4.0/qgslayertreeregistrybridge_8cpp_source.html)
queues deletion without consulting its enabled flag on that path. Accordingly,
restore inserts every replacement before removing any original node. No signal
blocking or private registry calls are used.

`QgsMapLayerStyle.isValid` only tests whether its stored XML is nonempty. The
[style implementation](https://api.qgis.org/api/4.0/qgsmaplayerstyle_8cpp_source.html)
does not return an import status from `writeToLayer`. Checkpoint parses the XML
before mutation, but provider-specific style application needs real-QGIS checks.

## Run inside QGIS later

Open the QGIS Python Console and run the following, replacing the repository
path if you moved it. This does not require the unfinished plugin entry point.
It creates a separate in-memory project and canvas, leaving the open project
alone. Do not interpret a passing run on one version as validation of both Qt
builds.

```python
from pathlib import Path
import sys
repo = Path("/Users/mooly612/Documents/Codex/2026-11-01/files-mentioned-by-the-user-checkpoint/outputs/checkpoint")
sys.path.insert(0, str(repo))
script = repo / "tests" / "qgis_smoke.py"
exec(compile(script.read_text(), str(script), "exec"))
```

The script checks plain serialization, style/tree round trip, map-view options,
layer registry survival after queued events, later layers, deleted layers,
malformed XML rejection, and preservation of an already-frozen canvas.

## Visual and provider checks still required

Use a disposable project and repeat on QGIS 3.28/Qt5 and QGIS 4.x/Qt6:

1. Capture a vector layer with labels, opacity, and blend modes, plus a raster.
   Change those settings and restore. Confirm the map and layer properties.
2. On a filter-capable provider, capture a nonempty subset, change or clear it,
   and restore. Also restore an empty subset over a nonempty one. A rejected
   filter should produce a notice rather than silently claiming success.
3. Reorder nested groups and layers. Include collapsed groups, duplicate group
   names, mixed visibility, and empty groups. Restore the original tree.
4. Add a layer inside a shared group and another inside a new nested group.
   Restore. Verify both survive with unchanged styles, filters, and local flags.
5. Restore a view with the scale lock enabled and after resizing the canvas.
   Confirm center and scale; the new aspect ratio can change extent boundaries.
6. Exercise point-cloud filters when a suitable test dataset is available.
7. Test QGIS 4 custom nodes: they should remain in the current tree and should
   not participate in snapshot hashes.

Watcher suppression, pinned pre-restore history, restore-result recording, and
message-bar display remain controller work for milestones 3 and 4. The low-level
restore returns notices, but is not a complete user-facing restore workflow.
