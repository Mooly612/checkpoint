# Preview design, version 0.2

The previous click-to-open design was superseded after the audit. Row selection
now updates prospective application details in the dock. Only **Preview** opens
saved historical before/after images. Only **Apply saved map styling** changes the
map; **Undo last application** uses an explicitly linked recovery record.

Text and lightweight renderer-XML symbol samples are always available. Expensive
map previews have an independent toggle. Map errors/timeouts preserve samples,
show a status, and expose **Retry maps**, which creates a new checkpoint using
current data. It never rewrites a historical saved image.

The 2-second threshold is a soft budget, not a UI latency guarantee. Synchronous
provider work can exceed it. Preparation and rendering are measured separately;
QGIS rendering jobs and detached layers are retained through asynchronous cancel.

See [reference](reference.md), [validation](validation-0.2.0.md) and the
[unexecuted user study](usability.md) for the contract and remaining questions.
