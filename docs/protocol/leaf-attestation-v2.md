# Observer leaf V2: signed RSSI result

Status (2026-10-04): the revised BLE/RSSI-only relation compiles with 6,201
constraints and 8 public outputs. `bash scripts/test_leaf_v2_binding.sh` passes
the signed-range/profile/freshness witness checks and confirms a synthetic
far-mismatch witness has `observation_eligible=1`, `consistency_ok=0`. The
updated `scripts/test_v2_observer_batch.sh` generated current-relation Groth16
leaf proofs, passed the host batch integration, verified a leaf proof in a
fresh local EVM verifier, and rejected five changed public signals. Its
`pcd3 --stage=plan` produced one consistent/two suspicious and
`VerdictSpoofSuspected`. The current run did not execute the BridgeBWV2 test
engine, an outer recursive proof, or FinalBNV2 EVM. All earlier V2 proofs/VKs
are stale for this source. No release-quality V2 ceremony or pinned VK is
published; V2 MUST NOT be accepted using the V1 VK or stale V2 fixture proofs.

## Change from V1

V1 verifies an observer signature over the Remote ID commitment, target, frame,
detection result, and freshness, but omits the RSSI range and the resulting
`consistency_ok`. A V1 proof can therefore reuse the same observer signature
with a different private range and obtain a different circuit output. This was
reproduced with the checked-in V1 VK; details and the attack command are in
[`leaf-attestation-v1.md`](leaf-attestation-v1.md).

V2 lives at [`circuits/uav_witness_attestation_v2.circom`](../../circuits/uav_witness_attestation_v2.circom).
V1 source, zkey, verification key, fixtures, and protocol numbering remain
unchanged.

## Canonical observer message

V2 computes one EdDSA-Poseidon message:

```text
M = Poseidon(
  0x4f42535f4c4541465f5632,   // domain: ASCII "OBS_LEAF_V2"
  drone_id_commitment,
  target_commitment,
  observation_eligible,
  freshness,
  measured_range_cm,
  calibration_profile_id,
  consistency_ok
)
```

Before signing, the circuit derives the public grouping value as:

```text
session_salt = big_endian(HMAC-SHA256(run_key,
  "signal.observer-circuit-salt.v2\0" || run_id)[:31])
drone_id_commitment = Poseidon(
  0x5349474e414c5f5249445f5632,   // domain: ASCII "SIGNAL_RID_V2"
  remote_id,
  session_salt,                 // private witness
  time_bucket
)
```

Observers in one run must use the same fresh, high-entropy 32-byte key and
opaque `run_id`; the same claimed RID and 60-second bucket then produce the
same public commitment. A different run key/ID or bucket produces a different
commitment, reducing straightforward cross-run linkage from the old
`Poseidon(remote_id)` construction. This is a trust assumption, not a circuit
proof of randomness: the session coordinator must generate and distribute the
key securely, never reuse it, and keep it private. Any key holder can test
candidate broadcast IDs. The commitment proves neither RID authenticity nor
that equal broadcast IDs came from the same physical aircraft. The run ID is
not itself authenticated; session membership still depends on the observer
signature and aggregation policy.

The range is constrained to 32 bits and must be positive. The calibration
profile id is constrained to 32 bits. `consistency_ok` is computed from the
range by the same circuit before it is included in the signed message; it is
not a prover-controlled input. `observation_eligible` is computed from a
five-second time-difference check and the positive-range check. It does not
prove packet reception or sensor honesty. A large position mismatch does not
make an observation ineligible: it produces `consistency_ok == 0`, which the
aggregator can count toward the suspicious quorum. The circuit constrains
`freshness` to equal `target_time_sec` and derives the 60-second `time_bucket`
from that value. The batch preflight checks that the public timestamp lies
inside the bucket; the V2 final registry checks submission recency using the
bucket only. This is coarse filtering, not proof that the observer clock or
receive event was truthful. The public-signal order is:

| Index | Signal | Purpose |
| ---: | --- | --- |
| 0 | `observation_eligible` | Timestamp within five seconds and measured range is positive; independent of position consistency |
| 1 | `drone_id_commitment` | Group equal claimed broadcast RIDs within a run and time bucket |
| 2 | `device_pubkey_x` | Observer registry lookup |
| 3 | `device_pubkey_y` | Observer registry lookup |
| 4 | `time_bucket` | Coarse observation time window |
| 5 | `consistency_ok` | RSSI/position consistency result |
| 6 | `freshness_pub` | Observer-signed Unix timestamp in seconds; constrained equal to `target_time_sec` |
| 7 | `calibration_profile_id_pub` | Allowlisted calibration profile |

This is an intentional privacy boundary: exact coordinates and the target
commitment are not exported. The circuit includes the target commitment and
signed RSSI result in its observer-message check. The new circuit/VK and
protocol version are incompatible with V1. All keys and proofs created before the
run-scoped salt relation—including earlier 8-output experimental V2 artifacts
and the older 19-output layout—must not be reused even though the public signal
count remains eight.

The exact Unix observation timestamp is a public leaf signal and is therefore
visible to whoever receives the leaf proof (normally the off-chain aggregator).
It is not in the 10-input final statement or V2 registry record, which exposes
only the coarse bucket. Do not publish raw leaf proofs if exact timing is
sensitive. If the aggregator must not learn exact observation times, change
the leaf schema to keep the timestamp private and expose only the bucket; that
is a breaking circuit/VK change and needs new end-to-end tests.

The aggregator MUST allowlist the public `calibration_profile_id` for the
policy and effective date in use. The synthetic generator uses profile `1`;
this is a fixture identifier, not a calibrated or approved real-device profile.

## What the signature does not prove

The signature proves that the holder of an accepted observer key endorsed the
range, profile, session context, and circuit-derived result. It does not prove
that RSSI was sampled honestly, that the hardware/software is uncompromised, or
that a range estimate is physically accurate. A malicious registered observer
can still sign false data. Device attestation, protected acquisition, real
calibration, and multi-node field evaluation remain separate requirements.

V2 does not verify a drone self-signature or bind the claimed Remote ID to a
DRIP registration trust root. `drone_id_commitment` only groups equal claimed
RID inputs within the run and bucket. A final result MUST NOT claim authenticated
aircraft identity until endorsement-chain, current signed-evidence/content,
and trust-root checks are implemented and bound to policy.

## Capture-to-proof gap

The V2 admission semantics now fit the BLE/RSSI-only objective: no camera fields
are required, and a far advertised-position/RSSI mismatch can remain an eligible
leaf with `consistency_ok == 0`. `scripts/gen_witness_sample_v2.js` adds a
synthetic far-mismatch scenario for regression testing; this does not represent
real sensor data or field accuracy.

The Pi capture utility still only emits JSONL. An experimental offline adapter,
[`scripts/capture_to_witness_v2.js`](../../scripts/capture_to_witness_v2.js),
now accepts an anchor `--include-raw` event and a same-bucket decision window,
plus a matching calibration report, run key, and separately provisioned
observer BabyJubJub key; it checks the shared run-scoped Basic-ID tag, takes
one RSSI sample per event and median-reduces the window, then builds the
canonical signed V2 witness. Regression tests use synthetic capture records,
validate the median-window witness with the current Circom relation, and an
opt-in disposable single-contributor Groth16 test has generated and verified a
proof. No real BLE capture has gone through
this adapter, the observer key is not yet enrolled in an operational registry,
and there is no release V2 zkey/VK. This does not prove RSSI was sampled by a
genuine receiver or that the offline model was honestly applied. The fixed keys
in `scripts/gen_witness_sample_v2.js` remain test fixtures and must not be used
for field data. Real capture-to-proof, device enrollment/attestation, and real
RSSI false-positive/false-negative evaluation remain open. Any future schema
change must regenerate V2 leaf keys/proofs and re-run Bridge, recursive, and
EVM validation.

## Current validation and pending release work

Before the BLE/RSSI-only relation change, on 2026-10-04 Circom 2.2.3 compiled
the prior session-salted wrapper with 12,087 nonlinear constraints, 8 public
outputs, and 12,077 wires. Its disposable Groth16/Bridge/EVM checks passed for
that prior relation, but they are not evidence for the current source. The
current relation also compiles with 6,201 constraints. On 2026-10-04,
`scripts/test_v2_observer_batch.sh` generated fresh leaf proofs for this
relation; the proof-backed host batch test passed, a Solidity verifier
generated from the same disposable setup accepted a leaf proof and rejected
five changed public signals, and `pcd3 --stage=plan` derived one consistent
plus two suspicious reports and `VerdictSpoofSuspected`. The script did not
run the BridgeBWV2 test engine, an outer recursive proof, or FinalBNV2 EVM.
On 2026-10-04, `TMPDIR=/Volumes/SSD bash scripts/test_leaf_v2_binding.sh` was
rerun:
Circom compiled and the signature-binding audit rejected changed range,
profile, and freshness values while accepting the eligible far-mismatch with
`consistency_ok=0`. All previous V2 proofs, VKs, and verifier artifacts are
stale. No test-only setup is a trusted setup or release artifact, and neither
witness nor leaf-verifier checks prove physical RSSI accuracy or
recursive/final aggregation. The current V2 multi-observer preflight and its
limits are documented in
[`v2-observer-batch.md`](v2-observer-batch.md). It checks real leaf proofs and
roster/session/profile consistency on the host, but does not yet prove those
aggregate rules in a recursive circuit.

Run the repeatable compile and witness audit from repository root:

```sh
bash scripts/test_leaf_v2_binding.sh
```

To exercise multi-observer proof verification with actual, temporary V2
Groth16 proofs (including valid alternate-profile, alternate-run, and
alternate-time-bucket variants), run:

```sh
bash scripts/test_v2_observer_batch.sh
```

The current-relation run passed proof-backed host integration for normal and
far-mismatch leaves, including duplicate, profile, alternate-run/session, and
public-output tampering cases. Two distinct far-mismatch observers remained
eligible and contributed to the suspicious quorum. The script's plan stage
reported three distinct registered keys, profile set `{1,2}`, counts `1/2`,
and verdict `2`. It uses a disposable single-contributor setup and removes its
temporary VK/proofs/ceremony files on exit. The optional
`RUN_BRIDGE_BW6_SOLVE=1` gate has not been rerun for this relation. No release
ceremony, outer recursive/final proof, or final aggregate/registry EVM
verification is complete.

The proof/EVM check can be repeated with a disposable one-contributor setup.
It takes several minutes, is intentionally not part of the fast test script,
and MUST NOT be used as a release ceremony or to publish a VK:

```sh
TEST_DIR="$(mktemp -d)"
mkdir -p "$TEST_DIR/circuit" "$TEST_DIR/samples"
circom circuits/uav_witness_attestation_v2.circom --O2 --r1cs --wasm -l node_modules -o "$TEST_DIR/circuit"
node scripts/gen_witness_sample_v2.js "$TEST_DIR/samples"
snarkjs powersoftau new bn128 14 "$TEST_DIR/pot0.ptau"
snarkjs powersoftau contribute "$TEST_DIR/pot0.ptau" "$TEST_DIR/pot1.ptau" --name="throwaway V2 test only" -e="$(openssl rand -hex 64)"
snarkjs powersoftau prepare phase2 "$TEST_DIR/pot1.ptau" "$TEST_DIR/pot-final.ptau"
snarkjs powersoftau verify "$TEST_DIR/pot-final.ptau"
snarkjs groth16 setup "$TEST_DIR/circuit/uav_witness_attestation_v2.r1cs" "$TEST_DIR/pot-final.ptau" "$TEST_DIR/test.zkey"
snarkjs zkey verify "$TEST_DIR/circuit/uav_witness_attestation_v2.r1cs" "$TEST_DIR/pot-final.ptau" "$TEST_DIR/test.zkey"
node "$TEST_DIR/circuit/uav_witness_attestation_v2_js/generate_witness.js" "$TEST_DIR/circuit/uav_witness_attestation_v2_js/uav_witness_attestation_v2.wasm" "$TEST_DIR/samples/input_dev2.json" "$TEST_DIR/input_dev2.wtns"
snarkjs groth16 prove "$TEST_DIR/test.zkey" "$TEST_DIR/input_dev2.wtns" "$TEST_DIR/proof.json" "$TEST_DIR/public.json"
snarkjs zkey export verificationkey "$TEST_DIR/test.zkey" "$TEST_DIR/test-vkey.json"
snarkjs groth16 verify "$TEST_DIR/test-vkey.json" "$TEST_DIR/public.json" "$TEST_DIR/proof.json"
snarkjs zkey export solidityverifier "$TEST_DIR/test.zkey" "$TEST_DIR/Verifier.sol"
cd contracts
LEAF_V2_VERIFIER_SOURCE="$TEST_DIR/Verifier.sol" LEAF_V2_PROOF="$TEST_DIR/proof.json" LEAF_V2_PUBLIC="$TEST_DIR/public.json" npx hardhat run --no-compile scripts/verify_v2_leaf_evm.js
```

Before V2 can be treated as a release path, the project still needs an
independently auditable ceremony and pinned release VKs for this exact R1CS and
recursive circuits, plus a release manifest. The V2 bridge/final statement and
registry gates exist, and registry tests cover approved policy, active member
root, recency, and final-session/proof replay with a mock verifier. Still
missing are current-revision leaf proof regeneration, a complete recursive
proof through the generated EVM verifier, observer-session nullifier union,
and production trust/governance for observer credentials and immutable policy
records. This host-side preflight and mock-verifier tests are not substitutes
for those integrations. None may reuse the V1 key.
