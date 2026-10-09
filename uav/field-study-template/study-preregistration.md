# RSSI field-study notes (copy into ignored `uav/captures/`)

Complete before opening or scoring held-out evaluation data. Keep the completed
copy private; it may identify people, sites, devices, or flight operations.
The machine-readable `study-preregistration.json` is the sole authority for
evaluator run IDs and numeric policy. Do not duplicate those values here; use
the JSON template and retain an independent record showing it was reviewed
before held-out results were opened.

| Field | Pre-registered value |
|---|---|
| Date range and approved test area | |
| Remote ID transmitter / firmware class (local note) | |
| Independent aircraft truth source and vertical datum | |
| Shared decision-window ID convention across observers | |
| Planned known calibration distances and repetitions | |
| Planned position-consistent / mismatch cases | |
| Exploratory-only rule if the run-count or precision target is not met | |
| Predeclared exclusion/deviation rules, including incomplete/conflicting groups | |
| Observer IDs, receiver/antenna, placement, profile IDs | |
| Weather, obstructions, orientation, and other conditions to record | |
| Observer count per scored window (current recursive V2 requires exactly 3) | |
| Data custody, access, retention, and deletion plan | |

Do not select or change the threshold/tolerance based on held-out results. If a
planned condition changes, record the deviation before analyzing that run and
keep it identifiable in the study notes. Use opaque IDs; never put a plaintext
Remote ID, participant name, or secret key in these tables.

Count independent test sessions/flights by `run_id`, not by observer rows or
decision windows. The three observers in one V2 decision window are evidence
for one aggregate classification, not three independent outcome trials;
repeated windows from the same run also remain one uncertainty cluster. Store
the complete expected run lists and all evaluator policy values in the JSON
template before viewing held-out outcomes. The evaluator requires exact
calibration/evaluation run-set matches and reports whether the run floor and
false-rate interval-width targets were met. Its content hash supports
reproducibility but does not prove the JSON predates the outcomes; use a
separately retained review/timestamp record for that.

Predeclare how acquisition errors and proof-shaped group statuses are reported.
Do not silently drop difficult runs after seeing their RSSI or classification:
incomplete groups (`INSUFFICIENT_EVIDENCE`), conflicting votes, and observer
counts unsupported by the current three-leaf topology do not enter binary
aggregate false-positive/negative rates, but their counts and reasons must be
reported beside those rates.

For evaluation ledgers, assign the same `decision_window_id` to every observer
row representing the same Remote ID target and aligned truth window. Use a
different ID for another target or decision window; keep `sample_id` unique per
observer row. The evaluator joins only this opaque ID and rejects a group whose
run or independent-truth label disagrees. This offline grouping identifier is
not a circuit input and must not be treated as proof of common-session origin.
