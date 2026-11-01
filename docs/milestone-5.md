# Milestone 5: change-focused previews

The history dock now has a persistent **Previews** checkbox. New checkpoints get
up to two QGIS-rendered before/after symbol samples, with a count of additional
changed legend items. Rows show time and description, with the date once per day.
Click or activate a row to open saved before/after maps. Restore remains a separate
button. An open preview updates when its asynchronous map rendering finishes.

Simple point, line, and polygon symbols use native QGIS legend previews at a fixed
sample size. Categorized/rule-based legend entries are paired by label and occurrence;
only changed sample images are displayed. Opacity is applied to samples. Label-only,
filter-only, visibility, and order changes do not display identical symbol pairs.
Their textual change descriptions remain visible. Visibility details are also
included in the comparison note.

## Rendering and focus

A preview uses detached layer clones with the recorded styles and filters, plus
the saved tree order and effective visibility. It never changes live layer styles,
filters, the project tree, or canvas view. Both sides use identical map settings
and extent. All visible context layers remain present, including for order and
blending changes.

For affected vector layers, a request limited to one feature finds a representative
neighborhood. This makes a sparse point legible in a very large project. The first
usable affected layer supplies the focus; the note names that layer. Multiple
widely separated changed layers are not all guaranteed to fit this one view.
Without a usable feature, the preview uses the saved canvas extent. This is a
styling comparison, not detection of exactly which geographic features changed.
Both styles render against source data available when the checkpoint is created;
no historical feature data is reconstructed. Missing sources and rejected filters
are noted instead of silently claiming a complete comparison.

Two `QgsMapRendererParallelJob` instances are started on the GUI thread. No custom
QThread is used. Their pair shares a two-second budget, including preparation,
and a precise single-shot timer cancels unfinished jobs with
`cancelWithoutBlocking()`. Cancelled jobs retain their detached layers until
`finished`, even after project close or plugin unload. New checkpoints interrupt
an unfinished older preview rather than building an unbounded render queue.
Available samples and the interruption reason are retained for that older entry.

Preparation (provider cloning, first-feature access, symbol sampling) is synchronous
because it uses QGIS layer objects. Elapsed-time checks stop further preparation
once over budget, but a blocking provider call cannot be interrupted by a Qt timer
while it occupies the GUI thread. Remote provider performance remains a practical
limitation. WMS/XYZ maps may be partial or blank; render errors are noted.

## Persistence and controls

Each record's optional `preview` dictionary contains PNG symbol samples, JPEG maps,
focus extent, changed-layer names, and explanatory text. Images are base64-encoded
inside the same atomic history JSON, so migration, pin retention, and eviction need
no separate orphan-file cleanup. They do not participate in styling hashes. Maps
are 400 by 260 pixels at JPEG quality 70 to support the larger click-open comparison;
only small symbol samples appear in history rows.

Images are saved once at checkpoint creation. Opening an entry never rerenders
against changed source data. Before images survive eviction of the predecessor.
Old entries without artifacts explicitly say that no saved preview is available.
Unsaved-project previews remain in memory until the first successful project save.
Image-write failure leaves the styling checkpoint intact and reports a preview
storage problem separately.

Turning Previews off hides samples and closes the comparison, cancels pending work,
and performs no new image rendering or image storage. Existing images remain with
their records. `checkpoint/previews` in `QgsSettings` is the shared setting for the
future standard Options control in milestone 6.

On timeout, `checkpoint/heavy/<project-key>` disables further previews for that
project, with one persistent panel notice instead of repeated message-bar alerts.
It survives reopening and migrates with an unsaved project's first save. Toggle
Previews off/on to retry. The standard Options page and its navigation link remain
milestone 6; no separate settings dialog was introduced here.

## API references and validation

Reviewed the versioned APIs for:

- Renderer lifecycle, `finished`, `renderedImage`, `errors`, nonblocking cancellation:
  [3.28](https://api.qgis.org/api/3.28/classQgsMapRendererParallelJob.html),
  [4.0](https://api.qgis.org/api/4.0/classQgsMapRendererParallelJob.html).
- Map settings, output size, extent, layers, background, style overrides:
  [3.28](https://api.qgis.org/api/3.28/classQgsMapSettings.html),
  [4.0](https://api.qgis.org/api/4.0/classQgsMapSettings.html).
- Native symbol samples:
  [3.28](https://api.qgis.org/api/3.28/classQgsSymbolLayerUtils.html),
  [4.0](https://api.qgis.org/api/4.0/classQgsSymbolLayerUtils.html).
- Legend items:
  [3.28](https://api.qgis.org/api/3.28/classQgsFeatureRenderer.html),
  [4.0](https://api.qgis.org/api/4.0/classQgsFeatureRenderer.html).
- Detached vector cloning:
  [3.28](https://api.qgis.org/api/3.28/classQgsVectorLayer.html),
  [4.0](https://api.qgis.org/api/4.0/classQgsVectorLayer.html).
- Limited feature requests:
  [3.28](https://api.qgis.org/api/3.28/classQgsFeatureRequest.html),
  [4.0](https://api.qgis.org/api/4.0/classQgsFeatureRequest.html).

43 pure-core tests pass. All five QGIS smoke scripts pass on QGIS 3.44.8 /
Qt 5.15.18 / Python 3.12.11, in an isolated offscreen profile. Preview checks cover
sparse points, line/polygon samples, multiple layers, categories, label-only,
filter-only, visibility, order, live-state isolation, persistence after predecessor
eviction and migration, old entries, disabled previews including Restore, timeout,
per-project fuse, retry, and asynchronous cancellation during unload/project close.
The timeout test uses deliberately stalled jobs with a real Qt timer; ordinary
map tests use actual QGIS render jobs. Qt panel/dialog screenshots were inspected.
QGIS 3.28 and QGIS 4/Qt6 runtime testing remains outstanding.

## Performance correction after desktop testing

Style/filter/visibility comparisons clone only affected layers, omitting unrelated
providers and labeling that omission in the preview. Order/group, blending, and
layer-opacity changes retain the full stack because context affects their result.
The two-second fuse remains; a slow affected provider can still exceed it.
