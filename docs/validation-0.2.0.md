# Validation of the local 0.2.0 build

Work started 2026-11-02; final verification completed 2026-11-03 (Asia/Shanghai). No remote release, push or QGIS catalog upload was performed.
The starting checkout was clean at `b686c193f5c1f1b32b5776a7ab6395608ca3027f`.

## Baseline and reproduced failures

The original 44 Python tests and six QGIS smoke scripts passed. Separate real
QGIS reproductions nevertheless showed:

| Scenario | Original result | New regression outcome |
| --- | --- | --- |
| Group exclusivity + typed custom property, capture/apply | `False`, property missing | Exclusivity, selection and typed property retained |
| Two stores opened before either append | Only B remained; A's pin lost | Both entries and pins retained |
| View center (10°, 20°), switch to EPSG:3857 | Center (10, 20) meters | About (1113194.9079, 2273030.9270) meters |
| Enable Auto in a populated open project | Zero history entries | Starting point exists before subsequent tracked edits |

## Environment and checks

- Pure Python: Python **3.14.7**, pytest **9.2.0**, macOS **27.0 (26A428)**.
  **60 tests passed**, including independent instances, two spawned writer
  processes, busy timeout, actual SQLite transaction failure, stale deletion,
  preview immutability, JSON migration, history copying and reproducible packaging.
- Native runtime: **QGIS 3.44.8-Solothurn / Qt 5.15.18 / Python 3.12.11** on that
  macOS host, using Qt's offscreen platform and a disposable QGIS profile.
- **Nine QGIS scripts** cover settings, state application, watcher timing, plugin
  lifecycle, Apply/recovery failures, previews, audit regressions and the bundled
  demo project and reopening an unchanged project in independent QGIS processes.
  They are also run against the extracted versioned plugin ZIP,
  checking that imports come from the temporary installation.
- Visual inspection: native dock at 360–390 px width, long checkpoint names,
  empty history, maps disabled, historical comparison, two-layer application and
  undo. Screenshots are of live Qt/QGIS widgets in an isolated interface harness.
  They do not represent an interactive test of the full QGIS Plugin Manager.
- The versioned archive is built twice from identical input and compared byte for
  byte; ZIP integrity, member layout, metadata, demo data and SHA-256 are checked.
  The checksum is the accompanying `.zip.sha256` artifact.

Additional regression work found that the root tree uses a different XML writer
which omits inherited WMS fields, and that style XML attribute order varies between
processes. Root capture now explicitly uses the base-group writer; schema-2 style
hashes normalize XML, including native callout symbol XML embedded in attributes,
while keeping the original style bytes for application. User custom-property
strings are not normalized as embedded symbols.
Legacy schema-1 hash validation is unchanged.

The group tests inspect real `isMutuallyExclusive`, selected child, custom QVariant
values, root/server/WMS properties after modification, duplicate names, renaming
and later layers. Simulated unsupported QGIS/Qt versions are rejected before
mutation; this is guard testing, not execution on those older/newer runtimes. Other native
checks cover legacy records, different/identical/invalid CRS, failed transformation,
canvas resizing, disabled view restoration, rejected filters, special group-layer
preflight, startup-save failure, disabled maps with samples, explicit retry,
project close/unload during pending render and delayed completion signals.

Failure injection verifies that an unavailable safety write leaves styling alone,
a failed result write leaves persisted recovery, and a partial provider exception
leaves recovery and releases watcher suppression. SQLite rollback is also tested
with a real rejecting SQL trigger, not just mocked file writes.

## Scaling measurement

`scripts/benchmark_history.py` uses 100 protected records with 400,000 image bytes
per record (about 40 MB total). Three local runs of a whole-JSON rename took
**160.01, 153.20, 335.48 ms**. The corresponding SQLite/revision-cache operation
measured **7.29, 2.63, 2.37 ms**. This is a small local microbenchmark, not a claim
about every filesystem or project. The first independent process refresh still
reads all records; individual updates write only changed rows. UI rows are reused.

## Compatibility and remaining limits

QGIS 3.28/3.40/3.44 APIs were compared. The server/WMS group methods used by
the supported contract start in 3.44, so metadata and a preflight runtime guard
require QGIS 3.44+ within 3.x and Qt5. Only 3.44.8 was executed.
Windows, Linux, other QGIS releases, Qt6/QGIS4 and slow real remote providers remain
unverified. Metadata excludes Qt6/QGIS4. CI configuration was added for pure Python
and packaging, with an opt-in prepared QGIS runner; no hosted CI run is claimed.

The preview threshold cannot cap a synchronous provider call. Group layers,
embedded/custom tree constructs refuse safely. Arbitrary project-wide Undo,
source data recovery and deleted-layer recreation remain out of scope. Legacy
records keep the current tree and skip a view without CRS. Export is provided;
import and cross-project layer/source mapping remain a separate feature.

No usability participants were recruited and no results are invented. The
[5–8 participant study plan](usability.md) is ready. Publication, catalog upload,
additional-platform testing, cross-project import and the study are separate
follow-up actions.
