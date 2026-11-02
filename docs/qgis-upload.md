# QGIS repository submission: Checkpoint 0.2.3

Upload **`dist/checkpoint-0.2.3.zip`** at
https://plugins.qgis.org/plugins/add/ after logging in. Upload the generated plugin
archive, not GitHub's source-code ZIP, a Markdown document or the checksum file.
The `.sha256` sidecar is for local verification only.

Reviewed against https://plugins.qgis.org/docs/publish and
https://plugins.qgis.org/docs/approval on 2026-11-03, and the supplied screenshot
of the six-item Pre-upload Checklist. The upload form itself requires login.

| Checklist item | Evidence / author action |
| --- | --- |
| Correct plugin ZIP structure | One `checkpoint/` root containing metadata.txt, __init__.py, implementation, icon and documentation. Packaging tests check this and reproducibility. |
| Public source matches uploaded code | Repository is public. Before checking this box, push the 0.2.3 source changes and verify the remote revision matches the ZIP. The local archive alone does not satisfy this item. |
| Meaningful English description | English description/about explain features, dependencies, supported QGIS/Qt and tested platforms. |
| Valid public metadata links | Homepage and repository point to the public GitHub repository/README; tracker points to its Issues page (HTTP 200 without authentication). |
| Version tested in QGIS | Test the built ZIP with scripts/run_qgis_checks.py in its disposable profile. The PNG icon is decoded and drawn at toolbar size by QGIS/Qt. |
| Contact email and maintenance agreement | Metadata uses mooly612@gmail.com. The author must personally agree to receive management correspondence and keep this address current. This agreement is not implied by technical validation. |

GPL-2.0-or-later licensing is declared consistently with the existing README;
the full GPLv2 license is bundled. The supplied icon is included as icon.png and
distributed under the project's license. There are no bundled native libraries,
external Python dependencies, accounts, telemetry or remote services. Synthetic
demo project/data and installation/usage documentation are included. The package
is below the 25 MB limit; development caches and Git metadata are excluded.

The build remains **experimental**. Compatibility is QGIS 3.44 through 3.x with
Qt5. Runtime validation is on QGIS 3.44.8 / Qt 5.15.18 / Python 3.12.11 / macOS;
Windows and Linux remain unverified and are disclosed in metadata. QGIS4/Qt6
support is not claimed. Existing shutdown-investigation limitations are recorded
in validation-0.2.1.md rather than silently declared solved.

On submission QGIS runs its own security checks and approval process. Passing our
local checks does not guarantee repository approval. The author submits the form
and confirms the contact agreement; this preparation does not submit anything.
