# Synthetic neighborhood demonstration

Open `checkpoint-demo.qgz` in QGIS with Checkpoint enabled. Keep `roads.geojson`
and `buildings.geojson` alongside it; the project uses relative file references.
The initial file has blue roads, neutral building footprints and street labels.

The GeoJSON features were generated from simple coordinates by
`scripts/create_demo.py` specifically for this project. They are synthetic, not
surveyed locations or downloaded OSM features. No external dataset or attribution
is required. The demo assets use the repository's GPL-2.0-or-later license.

1. Verify the starting checkpoint in the panel.
2. Change Roads to a wider rust-colored line. Change Buildings' fill and set its
   filter to `"floors" >= 3`. Save a checkpoint.
3. Select the starting point and inspect both layers' application scope.
4. Apply saved styling, then undo the application.
5. Use Preview to compare saved images, and disable maps to try the text/symbol
   workflow. Retry maps creates a new entry using current data.

`docs/images/history.png`, `applied.png`, `undo.png` and `comparison.png` were
captured from actual running Qt/QGIS widgets at QGIS 3.44.8 / Qt 5.15.18, using an
isolated interface harness and this project's GeoJSON. They are not mockups and do
not claim to show the full QGIS desktop or an active user project.

Regenerate from a QGIS Python environment:

```sh
python3 scripts/run_qgis_checks.py --demo --only demo
```

This updates the demo files and screenshot assets in the checkout. Screenshots
show the default native theme of the test runtime; Checkpoint sets no UI theme.
