# Raspberry Pi Remote ID Observer Capture

`observer_capture.py` is a local data-capture utility for the October–November
multi-observer PoC. It listens for BLE Service Data UUID `0xFFFA` and records
the local receive time, receiver-reported RSSI, and supported Basic ID / Location
message fields as JSON Lines. It accepts a single 25-byte ASTM message or an
OpenDroneID Message Pack containing 1–9 such messages. Authentication page
metadata and page data are retained, but pages are not reassembled and DRIP is
not cryptographically verified. It is separate from `remote_id.py`, which
broadcasts the Pi's own test messages.

## Run

On a Raspberry Pi with Bluetooth enabled and Python 3.10 or newer:

```sh
python3 -m pip install bleak
python3 uav/observer_capture.py --duration 120 \
  --run-id field-run-2026-10-04-01 \
  --observer-id observer-pi-01 --calibration-profile-id 2 \
  --output captures/observer-01.jsonl
```

By default, each process uses a random in-memory key, so its `uas_id_tag` is
not linkable to another observer's tag. To opt in to matching the same
broadcast Basic ID across nodes **within one run**, make a fresh 32-byte key
for that run and provision it to participating nodes through a secure channel
(never Git, chat, or the capture output):

```sh
umask 077
openssl rand -out captures/session-key.bin 32
chmod 600 captures/session-key.bin
```

Pass `--session-key-file captures/session-key.bin` on every participating
node. The file must be a regular, current-user-owned file with no group/other
permissions, contain exactly 32 raw bytes, and not be a symlink. Use a new key
for each run; do not put the key in the repository or logs. After the run,
restrict access to or remove the key according to the test data-retention plan.
The `uas_id_tag_scope` field identifies whether tags used the default
process-local key or an explicitly shared session key; the file path and key
are never logged.

The experimental V2 leaf uses that same shared key and `run_id` to derive its
private RID salt as
`HMAC-SHA256(key, "signal.observer-circuit-salt.v2\0" || run_id)[:31]`,
interpreted as a big-endian field integer. It commits with
`Poseidon("SIGNAL_RID_V2", remote_id, session_salt, time_bucket)`. A prover
must use the exact key and run ID used by the captures; the salt stays a private
witness while `drone_id_commitment` and the 60-second bucket are public. The
capture utility itself does not produce proofs. The sample witness generator
accepts `UAV_V2_SESSION_KEY_FILE` and `UAV_V2_RUN_ID`; its default key is a
public test fixture and must never be used for real data. Witness input JSON
contains the private salt and other private inputs; the generator creates each
file with mode `0600` and refuses to overwrite an existing input.

Use the same opaque `--run-id` on every node participating in one physical
session. Reuse a node's stable, non-identifying `--observer-id` and immutable
`--calibration-profile-id` across its calibration and evaluation runs. All
three fields are copied into the start, observation, and end JSONL records so
they can be joined consistently with held-out truth. Do not put a person's name,
email, drone serial number, or exact address into these identifiers.

Optional asserted observer coordinates can be added with both
`--observer-lat` and `--observer-lon`; `--observer-alt-m` adds altitude in
metres. These coordinates are local claims, not GPS-attested measurements. The
log file is created with mode `0600`; an existing file is never overwritten.
The raw BLE address and plaintext UAS ID are not stored by default. BLE address
tags always use a process-local key. `uas_id_tag` uses the process-local key by
default; with `--session-key-file`, it uses the shared key and `run_id` as
context, so the same typed Basic ID and run produce the same tag on participating
nodes while another run produces a different tag. Basic ID type and UA type are
included to avoid cross-type aliases.

This opt-in tag only groups equal broadcast identifiers. It does not prove the
broadcast is authentic, that two observations came from the same physical
aircraft, or that observers are independent: an attacker can copy/spoof a Basic
ID, and every holder of the shared key can test candidate IDs against that
run's tags/commitments. `run_id` is an application grouping value, not
authenticated session evidence. The circuit cannot prove the salt was random;
privacy depends on fresh high-entropy keys, secure distribution, and no reuse.
Keep a separately access-controlled truth ledger for controlled multi-aircraft
evaluation. The HMAC capture tag is metadata only; the leaf proof separately
binds the same private key-derived session scope through its Poseidon commitment.

Authentication frames are saved as page fragments: page 0 contains the last
page index, declared data length, timestamp, and up to 17 bytes; later pages contain
up to 23 bytes. The parser retains their bytes in `auth_data_hex`, but does not
assemble them, validate FEC, interpret a DRIP SAM format, or verify a signature,
endorsement chain, or session content. Accordingly, every capture record stays
`authentication_status: not_evaluated`; no authentication attempt is made, so
this is not the DRIP `Unverified` failure state. These page bytes can carry a DET and
signatures; protect the 0600 capture file as authentication material. The
layout follows the [OpenDroneID C reference](https://github.com/opendroneid/opendroneid-core-c/blob/master/libopendroneid/opendroneid.h);
the trust requirements are specified in [RFC 9575](https://www.rfc-editor.org/rfc/rfc9575.html).

For a Message Pack, each embedded 25-byte message becomes one JSONL observation
with its message index/count. All records from the same received service payload
share `capture_event_seq`, receive timestamp, and RSSI. `capture_end.captured`
counts decoded message records; `capture_event_count` counts accepted radio
payload events. The RSSI normalizer counts one RSSI sample per capture event, so
a larger pack does not artificially outweigh a single-message advertisement.

`--include-raw` stores each raw 25-byte ASTM message and, for a Message Pack,
the enclosing pack bytes. This exposes the broadcast UAS ID and exact signed
message bytes needed for independent signature rechecking. Use it only for
controlled test captures and protect/delete the resulting file appropriately.
Structured Authentication page data is recorded even without this option.

## Flutter phone BLE capture

The app's **BLE Raw Scan** page can now record the same `signal.observer-capture.v1`
JSONL consumed by `capture_to_witness_v2.js`. Tap the record icon, enter the
shared opaque run ID, this phone's stable observer ID, the calibration profile,
and the run's 32-byte shared key as 64 hex characters. Use a fresh random key
for each run and provision it to all participating nodes through a secure
channel; never put it in Git, chat, or the capture log. The app holds it in
memory for the capture and does not persist it.

Tap **現在地を取得** to read latitude, longitude, altitude, and reported GPS
accuracy. These are stored as `phone_gps_asserted_unverified`; neither GPS nor
RSSI is hardware-attested. This GPS fix is a single observer-location snapshot
for the entire capture; keep the node stationary or begin a new run after
moving. The V2 projection currently accepts observer latitude only from 34° to
36°. Start capture, then explicitly stop it to write
the closing record. If the app is killed before stop, the missing
`capture_end` makes the file invalid for witness conversion rather than silently
treating a partial run as complete.

BLE adapter loss, scan-start failures, scan-result stream errors, and unexpected
stream closure are written as `capture_error` records. The converter rejects any
capture with such a record, even if it also has a closing record; platform
exception text is not copied into the private log. This prevents a known failed
acquisition from being mistaken for a complete observation window. It cannot
detect packets the radio silently misses, so callback coverage still has to be
reported as a study limitation.

The adapter preserves the phone's reported horizontal GPS accuracy in private
provenance metadata. The current V2 leaf relation does **not** account for that
uncertainty when classifying location/RSSI consistency; this remains a required
field-method and circuit-policy limitation, not a precision guarantee.

The file is stored under the app's private documents directory. On a USB-connected
debug build, the app displays an `adb exec-out run-as ... cat ...` command with
`umask 077` so the host copy retains the owner-private mode required by the Node
adapter. Treat that copy as sensitive because it contains raw broadcast Remote ID
bytes, RSSI, exact observer coordinates, and accuracy. It does not
contain the shared session key or raw Bluetooth address. The phone currently
captures BLE Service Data only, not Wi-Fi manufacturer/NAN observations, and it
does not create the leaf proof on-device. Match `observer_id` and profile ID to
the calibration report, then use the same host conversion/proving flow below.
The adapter records the phone coordinate source in provenance as
`phone_gps_asserted_unverified`.

Run the cross-language synthetic integration gate from the repository root:

```sh
node --test scripts/test_flutter_capture_interop.test.js
```

It asks the actual Dart recorder to emit a synthetic Message Pack capture, then
checks host-file permission enforcement, Node witness/provenance generation,
and Circom WASM witness calculation. It uses fixed test IDs/keys and is not a
field capture, Groth16 proof, device enrollment, or hardware test.

## What this does not prove

- A parsed Remote ID message or Authentication page is not cryptographically
  authenticated by this tool; `authentication_status` remains `not_evaluated`.
- An RSSI value is not a reliable distance measurement by itself; antenna,
  orientation, obstructions, multipath, and hardware affect it.
- Observer coordinates are optional and self-asserted. This tool produces no
  observer credential, ZK proof, aggregation result, or blockchain transaction.
- Capture duration and callback frequency do not guarantee that every BLE packet
  is received. On Raspberry Pi, the BlueZ duplicate-data filter is requested to
  forward repeated advertisements, but adapter/controller filtering can remain.
- BLE addresses can rotate. Per-address correlation can split one transmitter
  into multiple tags; the per-run UAS ID tag can bridge this only after a Basic
  ID is received during that same run.

## Experimental capture event → V2 leaf witness

`scripts/capture_to_witness_v2.js` converts an owner-private capture decision
window into the input JSON for the current BLE/RSSI-only Circom leaf. This is a
prover-side adapter, not a sensor-attestation or Remote ID authenticator. The
anchor `capture_event_seq` must contain exactly one raw Basic ID; within an
explicit decision window (at most 60 seconds and entirely inside one leaf time
bucket), the adapter collects tagged BLE events and Location messages. It uses
one RSSI sample per capture event and takes the median, so a larger Message
Pack does not receive extra weight. Capture with `--include-raw`; the JSONL then
contains the broadcast ID and must remain private. The adapter verifies the
Basic ID's shared `uas_id_tag` against the supplied session key and run ID, and
refuses stale or ambiguous modulo-hour Location timestamps.

The calibration input is the owner-private JSON report produced by
`evaluate_rssi.py`. It must contain the same observer/profile, at least two
independent calibration runs, and the current circuit tolerance (`0.9`). The
adapter computes `range_cm = round(100 * 10^((rssi_at_1m_dbm - median_rssi_dbm) /
(10 * path_loss_exponent)))`. It packs the claimed Basic ID as the big-endian
integer `[id_type byte][ua_type byte][20 Basic ID bytes]`, and uses the captured
receiver time as `target_time_sec`. Latitude/longitude are shifted by +90°/+180°
before E7 encoding; both altitude values are shifted by +1000m before
centimetre encoding so the circuit's unsigned range constraints can represent
below-sea-level values. These transforms preserve coordinate differences but
are part of this experimental witness format.

```sh
umask 077
node scripts/capture_to_witness_v2.js \
  --capture captures/observer-01.jsonl \
  --event-seq 17 \
  --window-start-unix-ms 1791120000000 \
  --window-end-unix-ms 1791120060000 \
  --session-key-file captures/session-key.bin \
  --observer-key-file captures/observer-01.babyjub.key \
  --calibration-report captures/evaluation-report.json \
  --output captures/proofs/observer-01-input.json \
  --provenance-output captures/proofs/observer-01-provenance.json
```

Both key files must be exactly 32 raw bytes, owned by the current user, regular
non-symlink files, and mode `0600` or stricter. The observer BabyJubJub public
key appears in the provenance output; it must be enrolled in the accepted
observer roster before an aggregator will count it. The witness contains the
private RID encoding, observer coordinates, run salt, and signature; the
provenance sidecar intentionally omits plaintext ID and coordinates. Both
outputs are created exclusively with mode `0600` and are never overwritten.
Select no more than one decision window for each observer/RID/time bucket
because batch verification rejects duplicate observers in a bucket.

Compile the exact V2 source and calculate the witness in a private directory:

```sh
umask 077
mkdir -m 700 captures/proofs/circuit
circom circuits/uav_witness_attestation_v2.circom \
  --O2 --r1cs --wasm -l node_modules -o captures/proofs/circuit
node captures/proofs/circuit/uav_witness_attestation_v2_js/generate_witness.js \
  captures/proofs/circuit/uav_witness_attestation_v2_js/uav_witness_attestation_v2.wasm \
  captures/proofs/observer-01-input.json captures/proofs/observer-01.wtns
```

Run the adapter regression (it includes Circom witness generation):

```sh
node --test scripts/capture_to_witness_v2.test.js
```

An optional disposable one-contributor Groth16 proof setup takes several
minutes and is test-only:

```sh
RUN_CAPTURE_WITNESS_GROTH16=1 node --test scripts/capture_to_witness_v2.test.js
```

Never publish or deploy that test setup's proving key, verification key, or
proof as a release artifact. No independently reviewed V2 release key is
pinned yet. The adapter and regression use synthetic capture records; a real
BLE capture, enrolled observer key, and real calibration report have not yet
been used end to end. Its provenance explicitly keeps Remote ID authentication
`not_evaluated`, observer coordinates `cli_asserted_unverified`, and RSSI
receiver-reported but not hardware-attested. Unwrapping the seconds-within-hour
timestamp to the nearest local hour cannot distinguish a replay delayed by an
exact whole hour.

### Flutter / Raspberry Pi capture interoperability

On a development machine with Flutter/Dart, Node dependencies, Go, `circom`,
and `snarkjs` installed, run:

```sh
node --test scripts/test_cross_platform_capture_interop.test.js
```

This uses the real Dart recorder and two Pi capture callbacks driven by fake BLE
scanners, then sends the three private JSONL files through the same witness
adapter. Fixtures share a run key, claimed Basic ID, and time bucket, but use
different observer keys, asserted locations, and calibration profiles. The
test checks the common session-scoped RID commitment, checks that all three
witnesses satisfy the current V2 R1CS, generates and verifies three Groth16
leaf proofs using one disposable contributor, and gives those exact proofs to
`pcd3 --protocol=v2 --stage=plan`. The preflight must accept the distinct
synthetic test-roster observers and derive one consistent / two suspicious
reports. Using the same test VK, it also rejects a changed public signal, a
reused observer proof, and an individually valid proof from a different
run/session. This ceremony is strictly test-only; its zkey and VK must never be
published or deployed. The Python unittest suite also exercises the Pi
callback/JSONL boundary, so CI can cover that part without Flutter, Circom,
radio hardware, or additional dependencies.

These are synthetic inputs: the test does not run the recursive PCD stages or
FinalBNV2 EVM verifier, authenticate any observer key against a real enrollment
registry, or show that a radio emitted the recorded bytes. The generated keys
and identifiers must never be used for field collection.

## RSSI evaluation against independent ground truth

`evaluate_rssi.py` fits a log-distance RSSI model from a calibration CSV and
evaluates a separate, held-out CSV. It reports per-observer and multi-observer
quorum confusion matrices, false-positive/negative rates, and RSSI-derived
range error. It is an offline
measurement tool; it neither changes the ZK circuit nor proves that the sensor
reported an honest RSSI value.

The evaluator opens both exact-position CSV inputs with symlink rejection and
requires regular files owned by the current user with owner-read permission and
no group/other access (`0600` or stricter). The report is also created owner-only
and never overwrites an existing file.

`prepare_rssi_dataset.py` turns completed capture JSONL files plus a separately
maintained truth-window CSV into the evaluator's calibration or evaluation CSV.
The truth-window file is sensitive: it contains exact surveyed positions and
the per-run `uas_id_tag` join value. Keep it outside Git and create it with
owner-only permissions. Each row is one observer × target × decision window;
time bounds are Unix milliseconds with an inclusive start and exclusive end.
The truth position and observer position must come from sources independent of
the Remote ID Location message. For calibration, use surveyed target distances
at multiple ranges over at least two independent `run_id` values. For
evaluation, use entirely held-out `run_id` values and independently recorded
aircraft truth at the decision window (representative of the window centre, or
interpolated from the truth track). Synchronize capture-node and truth-source
clocks to UTC and record the conservative maximum relative time-alignment error
in `time_uncertainty_ms`; this should include capture-clock offset and truth
sampling/interpolation uncertainty. The script rejects uncertainty as large as
the window, but a smaller value is not itself proof of accurate synchronization.
Use a consistent documented vertical datum for observer, truth, and advertised
altitude.

In truth-window ledgers, `sample_id` is unique for each observer row. Rows from
different observers that refer to the same target and aligned independent-truth
window must share one opaque `decision_window_id`; use a new ID for another
target or decision window. `run_id` remains the independent session/flight
cluster. The normalizer requires each group to use the same per-run UAS tag,
have one row per observer, and have a non-empty overlap across all assigned
time windows. This catches common ledger join errors but does not authenticate
the group ID or truth source. The normalizer carries this ID into the evaluation
CSV but never into a leaf witness. Missing observer rows are missing evidence,
not implicit votes.

To avoid hand-typing the truth-window schema, copy the blank ledgers and
preregistration form from
[`uav/field-study-template/`](field-study-template/README.md) into an ignored
private working directory before data collection. The header-only examples are
checked against `WINDOW_FIELDS` by the Python unit suite; they contain no sample
measurements.

```csv
sample_id,decision_window_id,run_id,observer_id,calibration_profile_id,uas_id_tag,window_start_unix_ms,window_end_unix_ms,time_uncertainty_ms,observer_lat_deg,observer_lon_deg,observer_alt_m,truth_lat_deg,truth_lon_deg,truth_alt_m
```

Prepare the two datasets from completed capture files (one file per
run/observer). For multiple observers in the same run, provision the same
run-only session key securely if a common `uas_id_tag` is needed; never save
that key in the truth CSV or repository.

```sh
python3 uav/prepare_rssi_dataset.py \
  --captures captures/cal-observer-01.jsonl captures/cal-observer-02.jsonl \
  --truth-windows captures/cal-truth-windows.csv \
  --mode calibration --output captures/calibration.csv

python3 uav/prepare_rssi_dataset.py \
  --captures captures/eval-observer-01.jsonl captures/eval-observer-02.jsonl \
  --truth-windows captures/eval-truth-windows.csv \
  --mode evaluation --output captures/evaluation.csv
```

The normalizer requires complete `capture_start`/`capture_end` records, rejects
any `capture_error`, checks the logged observation count and stable capture
identity, rejects overlapping windows for the same run/observer/tag, and fails
closed if a window has no matching RSSI or Location packet (including missing
advertised altitude). Input
files must be regular files owned by the current user, have no broader than
`0600` permissions, and not be symlinks. It uses the median RSSI of all tagged
observations and medians of the Location coordinates in each window. Output
CSVs retain the stated time uncertainty but contain no UAS tag; they do contain
exact positions. They also carry `capture_set_sha256` (a domain-separated hash
of the sorted input capture-file hashes) and `truth_windows_sha256`, without
copying local file paths or individual source filenames. They are created mode
`0600` and are never overwritten. The evaluator report then hashes the exact
normalized CSVs, linking the report to these source digests.
Capture and truth files are not
cryptographically authenticated, so this transformation does not establish
data provenance or sensor honesty. Review the emitted packet counts and window
duration before treating a row as a measurement.

Prepare `calibration.csv` with one row per independent measurement window.
Keep all windows from one test session under the same opaque `run_id`, and
collect at least two independent calibration runs per observer/profile:

```csv
sample_id,decision_window_id,run_id,observer_id,calibration_profile_id,true_range_m,rssi_dbm_median
```

`true_range_m` must come from an independent known-distance measurement. Use
several distances and at least three windows for each observer/profile pair,
spread over at least two independent `run_id` values. The evaluator reports
the number of calibration runs and rejects a profile fitted from only one run.
Calibrate each receiver, antenna, placement, and materially different
environment separately; do not pool node readings under one ID unless the
profile explicitly covers that hardware scope.

Prepare `evaluation.csv` from entirely held-out `run_id` values, one row per
observer × aircraft × decision window, after reducing repeated BLE packets to
a median RSSI. Copy `run_id`, `observer_id`, and `calibration_profile_id`
directly from the capture records; do not create a different pseudonym in the
evaluation CSV. The evaluator rejects any calibration/evaluation run or sample
ID overlap. Do not
count individual repeated packets as independent examples. Give all rows from
the same independent flight/test session the same opaque `run_id`; use the
same `run_id` across observer nodes measuring that session. Join each window to
independent aircraft truth (for example, separately recorded GNSS/RTK data),
not to the Remote ID location being tested. `sample_id` must be a local
pseudonym, not a plaintext UAS ID.

```csv
sample_id,decision_window_id,run_id,observer_id,calibration_profile_id,observer_lat_deg,observer_lon_deg,observer_alt_m,advertised_lat_deg,advertised_lon_deg,advertised_alt_m,truth_lat_deg,truth_lon_deg,truth_alt_m,rssi_dbm_median,time_uncertainty_ms,window_duration_ms,capture_observation_count,location_packet_count
```

`observer_*` is the receiver's independently surveyed position;
`advertised_*` comes from the Remote ID Location message; `truth_*` is the
independent aircraft position at that observation window. Set the
position-error threshold before looking at evaluation results. A ground-truth
mismatch is an advertised-vs-truth 3-D error at or above that threshold. The
RSSI classifier predicts suspicious when the advertised observer-to-aircraft
range falls outside the calibrated RSSI range ± tolerance. The default
tolerance (`0.9`) matches the current V2 circuit setting; do not tune it on the
held-out evaluation set.

Run:

```sh
# Copy and complete the owner-private JSON template before held-out analysis.
chmod 600 captures/study-preregistration.json
python3 uav/evaluate_rssi.py \
  --preregistration captures/study-preregistration.json \
  --calibration captures/calibration.csv \
  --evaluation captures/evaluation.csv \
  --output captures/evaluation-report.json
```

The JSON is the evaluator's sole source for thresholds, quorum, run-count and
interval-precision policy. Its calibration and evaluation `run_id` sets must
exactly match the CSVs; missing and extra runs are both rejected. The report
stores the JSON's SHA-256 and byte length alongside input CSV hashes, making
the exact analyzed policy reproducible and preventing accidental value/run
set mismatch. A hash does not prove that the file existed before held-out
outcomes were opened, nor authenticate the data or its source; preserve a
pre-analysis review record separately.

Observer rows are grouped by `(run_id, decision_window_id)`. Each observer may
vote only once per group, and rows in a group must have the same independent
truth mismatch label. The current `pcd3` recursive V2 proof runner has a fixed
three-observer topology. Therefore, only groups with exactly three distinct
observer rows are eligible for a proof-shaped offline classification: fewer
than three are `INSUFFICIENT_EVIDENCE` even if the votes meet quorum, and more
than three are reported as unsupported by this topology. For exactly three,
suspicious or consistent votes reaching quorum produce that final status; if
both reach quorum, the group is conflicting and cannot be finalized; if neither
reaches quorum, it is insufficient. Aggregate false-positive/negative rates
include only finalizable binary decisions. Conflicting, insufficient, and
unsupported groups are reported separately and excluded from those rates, so
their counts must be reviewed alongside coverage. Changing the observer count
requires a matching recursive proof topology, not just a data-tool change.
Confidence intervals resample whole `run_id` clusters, not individual observer
rows or decision windows.

The preregistered maximum time uncertainty is enforced for every window. The
evaluator requires per-window timing uncertainty,
window duration, RSSI event count, and Location packet count; it rejects missing
quality metadata and any evaluation window above that preregistered limit. A
declared bound is still not independently authenticated, and the limit must be
chosen conservatively for the test speed and truth-source interpolation method.

The report records byte lengths and SHA-256 digests of the exact normalized
calibration and evaluation CSVs (without copying local file paths), so an
archived report can be matched to its inputs. These hashes detect content
changes but do not authenticate who collected or labeled the data. When saved
with `--output`, the JSON report is created mode `0600` and an existing report
is never overwritten.

`ground_truth_label_coverage` reports sample counts and independent-run counts
for the per-observer input rows. In `multi_observer`, the same-named field
counts all decision windows, while `finalized_truth_class_coverage` counts
only exact-three-observer binary decisions that enter aggregate error rates.
`preregistered_run_count_adequacy` compares that finalized coverage with the
JSON's `minimum_independent_runs_per_class` value and reports
`meets_minimum` or `below_preregistered_minimum`. A large number of windows
from one run is still one independent run for uncertainty assessment.
`preregistered_interval_precision_adequacy` reports both aggregate FPR/FNR
intervals and their widths relative to the JSON's
`maximum_95_false_rate_ci_width`; a missing interval does not meet the target.
Normalized evaluation rows also supply `capture_quality`, which summarizes
time uncertainty, window width, received RSSI-event count, and Remote ID
Location packet count (min/median/max), plus the applied maximum
time-uncertainty policy. Hand-built evaluation CSVs must include the same
quality fields as normalized CSVs.

`observer_id` is a stable local pseudonym for the receiver; the report gives
pooled and per-observer metrics plus false-rate intervals bootstrapped by
whole `run_id` clusters. At least two independent runs are required for
intervals; few runs still make them unstable. The JSON includes valid and
undefined bootstrap replicate counts separately for FPR and FNR. If fewer than
95% of requested replicates contain the truth class needed for a rate, its
95% interval is omitted instead of reporting a conditionally filtered interval.
Before opening held-out outcomes, record a minimum count of independent
`run_id` clusters for each truth class and a desired interval-precision target
in the owner-private machine-readable preregistration. Repeated windows within
one run and the three observers in one decision window are not independent
outcome trials. The evaluator reads the run-count floor and maximum false-rate
interval width from that JSON, reports whether each truth class meets the run
floor using only finalized binary aggregate decisions, then compares both
aggregate 95% false-rate interval widths with the target; an unavailable
interval is a precision-target miss. Meeting the run floor alone does not
prove useful precision. If either target is missed, label the result
exploratory. Always report incomplete, conflicting, and unsupported
observer-count groups next to binary aggregate rates because those groups are
excluded from the false-rate denominators.
The maximum interval width is `high - low` on the fractional 0..1 rate scale
(for example, 0.10 means ten percentage points).
Each `calibration_profile_id` must match
the corresponding observer's calibration rows and identify an immutable
record of the receiver/antenna, placement, calibration method, fitted
parameters, and effective date; changing
any of these requires a new ID. The current V2 circuit uses a fixed local
longitude scale for approximately 35° N. Results far from that latitude are
not comparable until the circuit's geographic conversion is updated and the
profile is versioned.

The V2 proof batch can accept different profile IDs when they are all in the
same policy-committed allowlist root and every leaf proves membership in it.
That membership proves only that the profile ID is allowed; it does not prove
that the receiver used the corresponding coefficients to convert RSSI into
`measured_range_cm`, or that the sensor reading is genuine. A multi-profile
evaluation report is offline measurement evidence, not proof of that circuit
property or of the final recursive/EVM path.

No real field dataset has been evaluated yet. Unit tests use synthetic values
only to test calculations; they are not evidence of detection accuracy. The
evaluation also cannot rule out multipath, relays, spoofed sensors, or a
malicious observer.

## Parser tests

From the repository root:

```sh
python3 -m unittest discover -s uav -p 'test_*.py'
```

The tests use synthetic packets. A successful test run does not replace a
Raspberry Pi scan or field measurement.
