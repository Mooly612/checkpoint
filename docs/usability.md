# Alternatives and usability assessment

Checkpoint has a plausible niche, not a unique claim to undo in QGIS.

- [QGIS Layer Styling dock](https://changelog.qgis.org/id/entry/494) already offers
  live styling with undo/redo. Prefer it for ordinary single-layer style editing.
- [Map themes](https://documentation.qgis.org/3.10/en/docs/user_manual/introduction/general_tools.html)
  provide named combinations of visible layers and active styles. Prefer explicit
  themes for presentation variants rather than accumulating automatic history.
- [Apply Layer Styles](https://plugins.qgis.org/plugins/apply_layer_styles/) copies
  styles across layers; it addresses reuse rather than project-wide checkpoints.

Checkpoint's useful distinction is a single chronological history combining style
XML, filters and tree changes across multiple layers, with reversible restoration
in the current session. The search was not an exhaustive audit of every plugin;
we should not advertise it as the only solution.

## Critique of the current build

The functionality is useful for cartographic experimentation, but convenience is
not yet proven. The user's confusion about Restore is evidence that the wording
needs work: a row describes a change, while Restore applies a full saved styling
state. A clearer future label is "Apply saved map styling", with an affected-layer
summary before application.

The click-open dialog interrupts browsing the list. A persistent preview area or
explicit Preview button would reduce accidental popups. The two-second fuse has
already failed on a real project; isolated tests cannot certify performance for
remote/large providers. Symbol samples should eventually remain usable even when
map rendering is disabled. Automatic pinned safety records clutter the history;
a dedicated recovery section or grouped restore events would help. Sparse-feature
focus can miss other changed layers. The minimum-gap control is also easy to
mistake for a periodic autosave interval.

Recommended next validation: ask several QGIS users to save a baseline, change two
layers, restore, undo that restore, and recover from a missing preview without
coaching. Record wrong actions, recovery success, and time to understand the state.
Until then this is an experimental helper, not a demonstrated polished replacement
for native styling undo or map themes.
