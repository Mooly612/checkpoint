# Checkpoint

Local styling history for QGIS users who experiment with the appearance of several
layers at once. Keep a starting point, change symbols, labels or filters, inspect
what an earlier checkpoint would apply, then apply it and undo that application.
Checkpoint saves style XML, filters, the layer tree and the map view. It does not
back up geometry, attributes, data sources or project files.

QGIS already offers per-layer styling history and editing Undo/Redo. Map Themes
provide named presentation variants and reference named styles; changing a
referenced style also changes that theme. Checkpoint stores the style XML at each
checkpoint and applies a snapshot across existing layers.
[QGIS styling history](https://docs.qgis.org/3.44/en/docs/user_manual/introduction/general_tools.html#layer-styling-panel),
[Map Themes](https://docs.qgis.org/3.44/en/docs/user_manual/introduction/general_tools.html#map-themes).

## Install and try it

This is **0.2.2, an experimental build prepared for QGIS repository submission**.
The prepared artifact is `dist/checkpoint-0.2.2.zip`, with a `.zip.sha256` sidecar.
To build it from this checkout, run `python3 scripts/package.py`.

1. In QGIS, open **Plugins → Manage and Install Plugins → Install from ZIP** and
   choose `checkpoint-0.2.2.zip`. Enable Checkpoint. Restart QGIS after updating.
2. Open a project. Checkpoint creates a starting point after loading completes.
   Check the panel status before editing. An empty project waits for its layers.
3. Change the appearance of two layers. **Auto** saves after a 2-second pause in
   styling changes, respecting the minimum gap between saves (60 seconds by
   default). In **Manual**, click **Save checkpoint**.
4. Select the starting point. Read **Changes relative to the current project**:
   it describes all affected layers, filters, visibility, groups and the view.
5. Click **Apply saved map styling**. Click **Undo last application** to return
   to the state immediately before it. Undo is available once per Apply and also
   replaces later manual styling edits; those edits receive their own recovery.
   Drag the details splitter or enable **Show full snapshot contents** as needed.

![Two-layer styling change and the selected checkpoint's application scope](docs/images/history.png)

This image comes from real QGIS 3.44.8 / Qt5 widgets in an isolated test window.
It is not a mockup or a screenshot of the user's desktop. The small
[demo project](demo/checkpoint-demo.qgz) contains synthetic roads, buildings and
labels. [Demo instructions and data provenance](demo/README.md).

## What selection, Apply and Preview mean

Selecting a row changes neither the map nor opens a window. The inline details
compare the selected snapshot with the current project. The row's description
records what changed historically; it does not limit the scope of Apply.

**Preview** opens saved historical before/after images. They use data available
when captured and may show a representative neighborhood. They are not an
up-to-date simulation of applying the checkpoint to today's data.

**Save map previews** controls expensive map rendering. Symbol samples and text
remain available with it off. If a render times out, **Retry maps** creates a fresh
checkpoint with current data. Existing saved images are never replaced. Two
seconds is a soft rendering/preparation budget; synchronous provider calls can
exceed it.

## Recovery and retention

Apply first stores a recovery state. If that write fails, the map is untouched.
A provider can fail during application, leaving partial changes; the recovery
state and Undo remain available within the same styling contract.

User **Pin / Unpin** controls ordinary retention. Automatic records are labeled
**Recovery** and linked to an application, without becoming user pins. Under
**History… → Clean up completed recoveries…**, keep the latest 10 recoveries,
all unresolved or partial ones, and every pin. Cleanup is explicit. Old
`before restore` pins remain pinned. Recovery and pins can therefore grow without
bound until you review them. The ordinary history limit defaults to 20.

## Where history lives

Saved history is local to your QGIS profile in
`checkpoint/<hash-of-project-path>/history.sqlite3`. Unsaved projects keep history
only in memory and lose it when closed. Normal project saving persists that
memory history. Save As offers **Continue with a copy** or **Start new history**;
an existing destination history is never silently merged or overwritten.

Moving the file outside QGIS does not move its history. Sending a `.qgz` to someone
else does not send the history. **History… → Export history…** saves a JSON archive
for inspection/archival. Import and automatic remapping across projects are not
supported in 0.2.1; names alone cannot safely identify layers. Use Save As inside
QGIS to continue a history at a new path.

## Limits and compatibility

Deleted layer IDs are skipped. Later layers remain; saved parent visibility may
still hide them. Group names, nesting, mutually exclusive selection and native
serialized group properties are retained. Group layers and custom/embedded tree
constructs are rejected before application. Legacy snapshots without group
identities keep the current tree. Views without a known saved CRS are skipped
with a notice; styles can still be applied. A CRS change transforms the saved
center and keeps the saved scale, without changing the project CRS.

Layouts, Map Themes, custom drawing order, source data and project settings are
outside the restoration contract. Continue saving and backing up the project.
There is no telemetry, account or cloud service. QGIS providers may contact their
sources while rendering.

Verified locally: **QGIS 3.44.8 / Qt 5.15.18 / Python 3.12.11 on macOS**.
The metadata targets QGIS 3.44–3.x with Qt5. Earlier versions are refused before
application because the supported group-property APIs require 3.44. Other QGIS versions, Windows, Linux,
Qt6 and QGIS4 have not been runtime-verified here; Qt6/QGIS4 are not advertised as
supported. English is the only shipped UI language.

[Installation](docs/install.md) · [Reference](docs/reference.md) ·
[Validation and limitations](docs/validation-0.2.1.md) ·
[Usability study plan](docs/usability.md) · [Changelog](CHANGELOG.md)

By Alen Alimzhanov. [GPL-2.0-or-later](LICENSE).
