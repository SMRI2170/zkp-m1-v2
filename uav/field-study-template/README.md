# RSSI field-study starter files

These are empty **templates**, not measurements. Copy them into an ignored
private working directory (for example `uav/captures/` or root `captures/`)
before filling them. Keep completed truth
ledgers, raw BLE captures, session keys, normalized CSVs, and reports out of
Git: they contain exact locations, broadcast identifiers or operationally
sensitive experiment details. `uav/captures/` is already ignored by the root
`.gitignore`.

Before collecting data:

1. Complete the owner-private `study-preregistration.json` from the example
   before collecting data or opening held-out results. It is the only source
   for evaluator thresholds, quorum, run IDs, and adequacy targets. Use
   `study-preregistration.md` only for other field-method notes; do not keep a
   second conflicting copy of evaluator settings.
2. Use one opaque `run_id` per independent session/flight, shared across nodes
   observing that session. Give calibration and evaluation different run IDs.
3. Survey observer positions and collect aircraft truth independently from the
   Remote ID Location message. Record vertical datum and conservative clock
   alignment uncertainty. Do not fill truth from the broadcast being tested.
   The evaluator reads the preregistered maximum uncertainty directly from the
   JSON; windows exceeding it are rejected rather than scored.
4. Use several known distances and at least two independent calibration runs
   per receiver/profile. Aim for at least three windows per distance and profile.
5. For evaluation, preserve separate runs and include both position-consistent
   and position-mismatch cases. More independent runs are better; many windows
   from one run do not count as many independent samples.
6. Give the same opaque `decision_window_id` to all observer rows for the same
   target and aligned truth window; keep each per-observer `sample_id` unique.
   This lets the offline evaluator reproduce quorum outcomes without putting
   the grouping label into the proof. The normalizer checks that each such group
   uses one per-run UAS tag, has one row per observer, and has overlapping time
   windows; it cannot authenticate the group ID or the truth ledger.
7. The current recursive V2 proof runner accepts exactly three observers.
   Plan three distinct observers for every scored decision window; incomplete
   groups are insufficient and groups larger than three are unsupported until
   the proof topology is extended.
8. Before looking at held-out outcomes, declare the expected calibration and
   evaluation `run_id` lists, minimum independent evaluation clusters per
   truth class, and maximum 95% false-rate interval width in the JSON. The
   evaluator rejects any CSV whose run-ID set differs from those exact lists.
   Repeated windows from one run and the three observers in one decision
   window are not independent outcome trials. Its report hashes the JSON and
   data CSVs, and compares both adequacy targets with finalized aggregate run
   coverage and interval widths. A hash does not prove when the JSON was
   authored: preserve an independent pre-analysis review record. If either
   target is missed, label the result exploratory and report class/run
   coverage, interval status, and all incomplete/conflicting/unsupported
   groups; do not tune thresholds or omit runs after seeing classifications.

Copy the appropriate truth-window header to a new private CSV; keep the
calibration and evaluation ledgers separate. The columns and processing
commands are documented in
[`OBSERVER_CAPTURE.md`](../OBSERVER_CAPTURE.md#rssi-evaluation-against-independent-ground-truth).
`prepare_rssi_dataset.py` validates the ledger/capture join and produces the
normalized calibration or evaluation CSV. Copy
`study-preregistration.json.example` to the ignored captures directory and
replace every example run ID and policy value with the reviewed study plan;
the numeric values in the example are illustrative, not recommended defaults.
The evaluator reports metrics and run-cluster uncertainty; it does not
authenticate the sensors or truth source.
