# Change-focused history previews

Accepted UI direction on 2026-11-01, following the first desktop test.
This updates the original whole-canvas thumbnail requirement. Milestone 5 now
implements this direction; see [implementation details and limits](milestone-5.md).
The standard Options integration remains milestone 6.

## Compact history rows

Each row contains a time, affected layer name(s), change type, and a small
before/after visual sample. Put the date in a day separator instead of repeating
it in every row. Use subtle separators and native selection styling; do not
assign arbitrary colors to checkpoints. Keep full descriptions in details and
tooltips. Render samples with QGIS symbology, not approximate CSS or drawings.

For simple point, line, and polygon style changes, show the old and new symbol
at the same sample size. Sample size must not depend on the geographic extent
or the feature count. This makes a sparse point layer's change legible.

For categorized or rule-based renderers, show a small representative subset
of changed legend items and a count of additional changes. Do not imply that a
single representative symbol describes the entire renderer. Labeling, opacity,
and blend-mode changes may require the map comparison to explain their result.

For changes without a useful symbol comparison, show the specific operation:
visibility on/off, filter changed, or layer/group order changed. A filter change
does not necessarily change symbology, and must not be represented by misleading
identical swatches. The initial checkpoint has no before-state sample.

## Map on click

Clicking a row opens its larger before/after preview without restoring it.
Keep Restore a separate explicit action. Compare both states at the same extent
and scale. Focus the preview on affected layers and include enough surrounding
map context to understand the change. Label this as a preview of changed layers,
not an exact detection of changed geographic features.

The stored style/filter/tree comparison identifies affected layers, not changed
feature geometries. An automatic zoom must not simply use the whole-project
extent, nor assume that a layer extent always yields a useful view. Sparse or
widely dispersed points may need a representative feature neighborhood; the
symbol sample remains the reliable small visual in those cases. A change to
layer order or blending requires surrounding layers in the comparison.

Persist preview artifacts at checkpoint creation so later edits to source data
do not silently replace a historical preview with a new rendering. If no preview
was saved, report that it is unavailable. Do not fabricate previews for old
checkpoints. Preview images are not a backup of source data.

## Controls and resource limits

Provide a discoverable preview enable/disable control in the panel, connected
to the standard QGIS Options setting. Disabling it prevents preview rendering
and new image storage. Keep the original main-thread QGIS parallel-render job,
two-second cancellation, and per-project heavy-render safety fuse. Turning off
previews must leave the textual history usable.

## Delivery order

The selected before/after sample plus click-to-open map design is accepted.
Restore safety remains milestone 4. Preview rendering and this compact row UI
belong to milestone 5; the standard Options page remains milestone 6. The
before-state information needed by previews must be retained when recording a
checkpoint, including when the preceding unpinned record is later evicted.

Acceptance checks include a sparse point layer in a large project, multiple
changed layers, categorized symbols, label-only changes, filter-only changes,
visibility, layer order, old checkpoints without previews, disabled rendering,
and the heavy-project timeout.
