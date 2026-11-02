# Usability validation plan

No user research has been conducted for 0.2.0. Automated checks and the author's
visual inspection are engineering evidence, not observed usability results.

Recruit 5–8 QGIS users: several who use layer styling daily and several who rely
on Map Themes or built-in Undo. Use the supplied synthetic neighborhood project.
Give each participant a fresh temporary profile/history and the same brief:

1. Establish a safe starting point and explain whether it is currently saved.
2. Change roads and buildings, including the building filter. Save that variant.
3. Select the first checkpoint. Before applying, say which layers and properties
   will change and whether geometry, attributes or the project file will change.
4. Apply it. Return to the state immediately before that application.
5. Open the saved preview and explain its relation to today's data and Apply.
6. Encounter unavailable map previews. Find the details/samples and retry maps.
7. Switch to Manual, inspect a memory-only project, then use Save As and explain
   where the old and new histories will live.
8. Pin a checkpoint, review recovery cleanup, and predict what will remain.

Do not teach the intended action before the participant tries. Record task
completion, time, first wrong action, requests for help, unexpected popups,
confusion between historical description and application scope, uncertainty about
recovery retention, and whether status is interpreted as data backup protection.
Ask for confidence before and after Apply. Compare behavior, not preferences alone.

Engineering acceptance already covered: selection does not change styling/open a
popup; long names have tooltips; details scroll at ordinary dock width; keyboard
focus can reach list, details and actions; missing maps leave text accessible;
safety-write failure leaves the map unchanged; partial failure leaves recovery.

Remaining research questions include whether a full-snapshot Apply is predictable,
whether Undo is found without prompting, and whether explicit recovery cleanup is
understood. Publish participant counts, actual observations and limitations only
after running the study. Never fill this document with invented results.

For one layer, QGIS's own styling history can be enough. Its documented Map Themes
reference named styles and are useful for presentation variants. Checkpoint adds
persistent snapshots across existing layers, with the narrow contract described
in [the reference](reference.md).
