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
