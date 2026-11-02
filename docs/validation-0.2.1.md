# Local 0.2.1 follow-up, 2026-11-03

Baseline: a805f73 (0.2.0). Local build only; no push, GitHub Release or QGIS catalog upload.
Existing user-owned `work/` probes were read and run, not modified.

## Behavior and interface

Undo is a single-level operation. A persisted SQLite `undo_head` identifies the
recovery created by the most recent explicit Apply. Undo's protective recovery has
`operation=undo` and `undo_of`, and cannot become the next Undo target. Successful
Undo consumes the original action. Partial/provider/result-write failures retain
the original target for retry. A failed safety write performs no application.
Removing the target, including from another session, disables Undo without falling
back to an older entry. The head survives restart and Save As; completed active
recovery is protected from automatic cleanup. Legacy events have no automatic
Undo, but remain available for manual Apply. No existing pins are removed.

Undo restores supported styling across the saved project scope, including manual
styling edits made after Apply. Those current edits are saved in Undo's protective
recovery before application. This is explained in the button tooltip. Recovery
entries remain visible for manual restoration. It is not an editing/data undo.

The native dock has a persistent vertical splitter, keyboard-accessible full
contents checkbox, and a compact default summary of changed layers. Snapshot
layer count is explicitly distinguished from changed style/filter count; tree and
view changes are reported separately. Pin, Rename, availability and image updates
update existing rows without emitting a false selection change. Actual selection
captures current state immediately; observed styling/view changes debounce the
summary by 150 ms. No project-state cache is used, so choosing an entry again and
Apply perform fresh checks. Changes without signals require a manual capture or
reselection to update the displayed summary. Apply always preflights actual state.
Screenshots in `docs/images` are real isolated Qt/QGIS widgets, not a user study.

## Auto contract

Verified against the installed QGIS 3.44.8 QObject metaobject, whose group signals
are children add/remove, visibility, customPropertyChanged, expandedChanged and
nameChanged. Root custom-property signals propagate from descendants, so no
per-group QObject references or reconnect scans are needed.

| Property | Saved/applied | Auto | Manual capture needed |
| --- | --- | --- | --- |
| Order, group name, visibility | yes | yes | no |
| Group custom properties | yes | yes, propagated signal | no |
| Internal checkpoint/group-id | yes | deliberately ignored | no |
| Expanded/collapsed nodes | yes | deliberately ignored | yes, or next tracked change |
| Mutual exclusion / selected child | yes | only if visibility also emits | yes when visibility does not change |
| WMS/server group fields | yes | no dedicated reliable signal | yes |
| Layer styles and subset filters | yes | style/renderer/subset signals | for mutations bypassing those signals |
| Canvas CRS/extent/scale | yes | updates summary, not Auto history | yes, or next tracked change |

Capture does not serialize XML on each signal. Restore retains suppression through
the next event loop turn. Tests cover rapid custom-property changes producing one
entry, UUID/expansion silence, group deletion, Apply and suppression release.

## Reproducible measurements

Raw distributions, repetitions, nearest-rank p95 (= maximum for these small sample
counts), peak process RSS and database sizes are in `benchmarks/*.jsonl`.
Run `scripts/profile_history.py` with ordinary Python, and `scripts/profile_qgis.py`
with the QGIS Python environment documented in `install.md`. `CHECKPOINT_SOURCE`
selects an extracted baseline checkout. Fixture creation is excluded. Baseline
and modified runs use structurally equivalent synthetic local memory projects;
QGIS-generated UUIDs vary. These are microbenchmarks, not arbitrary real projects.
Open measures a new store with a warm OS filesystem cache, not physical cold disk.
External refresh includes the other store's real rename; two-writer correctness
is separately covered by multiprocessing tests. No slow remote source was used.

| Operation | Baseline median | After median |
| --- | ---: | ---: |
| 1000 records, actual changing Rename | 11.565 ms | 1.349 ms |
| 1000 records, no-op Rename | 10.938 ms | 0.154 ms |
| 1000 records, Pin | 11.554 ms | 1.151 ms |
| 100 records / 40 MB images, changing Rename | 2.874 ms | 2.082 ms |
| 100 records / 40 MB images, new-store open | 160.097 ms | 161.907 ms |
| 100 records / 40 MB, other-writer rename + refresh | 163.884 ms | 166.093 ms |
| 500 simple layers, capture | 240.90 ms | 238.55 ms |
| 500 layers, identical-state summary only | 3034.29 ms | 0.80 ms |
| 10 layers, warm component hashing | 15.40 ms | 0.44 ms |
| Initial symbol preview, 100 categories | 26.25 ms | <0.01 ms (omitted) |
| Initial symbol preview, 10000 categories | 2572.42 ms | <0.01 ms (omitted) |

The summary speedup removes unrelated component hashing and short-circuits exact
XML equality. It does not include capture; differing style XML still needs exact
normalization. The bounded normalization cache holds at most 256 entries and
8 MB estimated string storage (4 bytes/character); individual large styles bypass
it. Project/watcher teardown clears it. It benefits small repeated projects;
100/500-layer sequential scans exceed its byte capacity and still cost about
152/751 ms for component hashing. No incremental capture was introduced.
Append passes already-computed components into historical description generation.

Metadata mutations copy the changed record rather than deepcopy every snapshot;
no-op rename/pin does not publish a database revision. SQLite format and bounded
150 ms busy timeout are preserved, with no WAL change. Full history refresh and
opening still parse/validate all records after an external revision. Large base64
images and full list copies remain a scaling limit. Separating image storage is a
future migration decision, not claimed as fixed here.

Symbol samples inspect at most two changed layers and render at most two legend
items per side; only two comparison rows are displayed. Styles over 128000
characters are omitted before renderer loading. The UI explicitly describes this
incomplete sample set; no exact omitted-change count is invented. Unchanged style
XML does not render symbols for filter-only changes. The category benchmark is an
initial snapshot: subsequent full XML comparison/capture of a 20 MB style can
still block the GUI. Peak RSS for the 10000-category sequence was about 882 MB
before and 761 MB after, including fixture creation and prior benchmark cases.
This is not per-operation allocation. Full capture and text comparison are still
unbounded by layer/category count. Provider calls remain synchronous.

Only one PreviewTask can own map jobs at a time (two sides). While cancelled jobs
finish, new entries retain text/symbol previews and explicitly report that maps
were skipped. Resources are retained until jobs finish, including after unload.
Historical images remain immutable; retry creates a fresh checkpoint.

## Shutdown investigation

The original `work/run_recheck_probe.py` reproduced SIGSEGV after reporting Undo
and Auto results, both before and after behavioral fixes. Faulthandler reported
no Python frame. Adding GC and Qt DeferredDelete processing before `exitQgis()`
made that original probe exit 0. The runner now finalizes these objects while
QGIS registries still exist rather than leaving disposal to interpreter shutdown.

However, isolated empty/canvas/cyclic-window variants all exited 0, and the copied
minimal audit scenario also exited 0 with legacy, GC-only, DeferredDelete-only and
combined teardown. Therefore the exact native crash owner is **still unresolved**;
a native backtrace was not obtained, and teardown ordering remains a supported
hypothesis, not proof of a production plugin crash fix. No signals or exit codes
are ignored and no `os._exit` workaround is used. `scripts/check_shutdown.py`
checks the copied reproduction in a subprocess; `--matrix` reports the variants.
The user-owned original reproduction remains available for further native debugging.

## Validation and limits

Runtime: QGIS 3.44.8-Solothurn, Qt 5.15.18, Python 3.12.11, macOS, offscreen
platform and temporary QGIS profile. Python unit checks use Python 3.14.7.
The pure suite has 63 passing tests. All eleven native scenarios passed from the extracted ZIP with process exit 0, including the original nine and new Undo/Auto/UI and shutdown probes.
It imports from the extracted archive and checks process completion, not just
printed success. Added failure injection exercises Undo safety-write, partial
provider, result-write failure, retries, manual edits and repeated clicks. Store
tests cover restart, concurrent deletion and detached return values. Earlier
Apply failures, rollback, concurrency, close/unload and immutable images remain.

Windows/Linux, Qt6/QGIS4, slow network sources, large complex real projects and
interactive user testing remain unverified. The 100 ms target is not met by full
capture at 500 layers or opening/refreshing the 40 MB history. No wall-clock
performance assertions were added to ordinary tests.
