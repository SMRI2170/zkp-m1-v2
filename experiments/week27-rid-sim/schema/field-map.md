# PR1 fields and provenance

All rows have `dataset_source=simulation`. Units are local metres, simulator
seconds and dBm; the RID payload timestamp is milliseconds. No GPS datum is
implied. Raw CSV/Parquet and ledgers stay in ignored owner-only `captures/`.

| Field | Source / limitation |
|---|---|
| `tx_event_id` | TX `Transmission Packet ID`, RX `Packet ID`: OMNeT++ packet tree ID; exact join, not serial/time proximity |
| `rx_event_id` | Receiver index + OMNeT++ event number; derived identifier |
| `tx_time` | Event vector timestamp at management enqueue; actual PHY airtime not recorded here |
| `rx_time` | Handler event vector timestamp |
| `rx_signal_start_time` | `Reception Time` vector, nullable |
| `serial` | RX `Serial Number`; null if not received, never synthesized from TX host index |
| `claimed_timestamp` | RX `Reception Timestamp`; null if missing. Attacker-controlled, not used for physical packet matching |
| `rx_node_id` | Receiver module path; for not-observed opportunities, configured receiver list |
| `rx_xyz` | RX `Reception My * Coordinate`, nullable for not-observed opportunities |
| `true_tx_xyz` | TX `Transmission My * Coordinate`, simulation truth for audit only |
| `claimed_xyz` | TX `Transmission * Coordinate`; verified against exact received claim |
| `rx_claimed_xyz` | RX `Reception * Coordinate`, null for not-observed opportunities |
| `tx_power_dbm_truth_only` | PR1: TX `Transmission Power` (parameter sample). PR2: `Requested PHY Power` (per-packet tag request), with `tx_power_source` distinguishing these. Not detector input |
| `phy_tx_time_truth_only`, `phy_tx_power_dbm_truth_only` | PR2 only: actual createTransmission hook. Null if no PHY hook by horizon. The native implementation keeps the INET parameter immutable; packet tag supplies dynamic power |
| `rssi_dbm` | `Reception Power`, only when that vector exists in the same event. Missing `SignalPowerInd` becomes null, never default zero. INET 4.5.4 ReceiverBase computes the minimum signal-plus-noise power over the listening interval, not isolated desired-signal power |
| `delivered`, `delivery` | Received Beacon handler present, or `NOT_OBSERVED` for TX×configured receiver with no handler by horizon. PR2 distinguishes `PHY_TX_NOT_LOGGED_BY_HORIZON` using the PHY hook |
| `is_spoofed` | TX `Transmission Is Spoofed`, simulation label only |
| `score`, `decision` | null / `UNDETERMINED`: no detector in PR1 |
| `observer_regime` | This smoke is same-packet multiple-site comparison, not #66's asynchronous solution |

`NOT_OBSERVED` does not distinguish PHY rejection, MAC drop or a still-pending
frame. There is no row for a beacon that was never enqueued; a zero-TX run fails
the smoke. Raw `.vec/.sca`, actual commands, exits and logs permit further audit.

Upstream's Parquet converter currently uses vector row indices for associated
RX fields and synthesizes TX serial/time from host/time. Our audit instead uses
ETV event numbers, rejects ambiguity, and takes serial/time only from RX logs.
GCS Python callbacks expose only the first report's packet ID. Matching GCS
counts is useful smoke evidence, not proof of collision-safe GCS grouping.

PR2 adds a monotonically increasing GCS `callback_id`. Multiple callbacks can
occur in one OMNeT++ event. Only when every fixed callback field has the same
count and counters are unique do we split that event by callback occurrence.
Repeated GCS fields without counters, incomplete callback sets, and repeated
management/PHY fields still fail closed. This is a logged callback boundary,
not matching arbitrary packets by nearby timestamps.
# PR4 inference and Issue69 mode E

`detector_projection` is the only boundary into the conditional detectors.
True position, actual TX power, labels, scenario names and seeds are excluded;
an unreceived payload is null. Frame IDs group records and are not numeric
features. KF startup and missing receptions are UND, never zero-score normal.

SingleResidual and DRSS subtract the known **synthetic -100dBm background**
before scoring. This is an extra calibrated-noise assumption; no arbitrary
interference cancellation is implied. KF and upstream MLAT use recorded raw
total RSS. Geometry and empirical thresholds are learned on disjoint normal
splits only. All performance has conditional denominators and all-TX counts.

`visualization_adapter.py` maps the observation-regime names to #69's
`async_single_packet_per_observation` and `same_physical_packet_multirx`.
It reads already-computed scores and never implements another detector.
Its optional mode-E coordinate export is restricted to ignored `captures/`;
the public results contain only aggregate metrics. `BELOW_THRESHOLD` means
below a model threshold, not verified true position or safety.
# PR5 private attack audit

`attack-truth.schema.json` describes the private per-physical-TX ledger.
`requested_delta_db` is the unconstrained n=2 compensation. `applied_delta_db`
is the final actual PHY power minus nominal, after separate attack and PHY
clamps. `compensation_error_db = applied_delta_db - requested_delta_db`.
`target_rx_id=-1` is a mixture/no-reference marker, not a missing receiver
measurement. `evaluation_rx_id` is audit-only, including in blind runs.

The blind native path never reads `observerSchedule`; its mathematical helper
cannot receive a schedule or RX feedback. Private truth fields are excluded by
the existing whitelist projection. Audit/model/power/clipping strata may use
truth only AFTER detector scores have been saved. They do not improve the
detector's runtime information or turn derived model checks into new RF runs.
