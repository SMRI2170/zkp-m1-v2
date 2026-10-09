# Leaf attestation interface for final-attestation-v1

## Purpose

An aggregate count is meaningful only when each accepted item is a genuine
device observation proof.  This document fixes which public signals from
`circuits/uav_witness_attestation.circom` a recursive or batch aggregator must
verify and carry into the final statement.

The leaf proof is Groth16/BN254.  Its verification key is a release artifact;
an aggregator MUST pin that key and must not accept a relayer-supplied key.

## Public-signal layout

The Circom declaration order is the canonical layout below.  The current
gnark aggregate code uses the same zero-based indexes.

| Index | Signal | Aggregator rule |
| ---: | --- | --- |
| 0–5 | distance/time/detection sub-results | Private to the aggregation policy; not copied to final output. |
| 6 | `within30_and_detected` | Must equal `1`. |
| 7–9 | observation commitments | Not copied to final output. |
| 10 | `drone_id_commitment` | Must be identical across all leaves; becomes final `droneIdCommitment`. |
| 11–12 | `device_pubkey_x`, `device_pubkey_y` | Must have valid membership under `memberRoot`; used for the session nullifier transition. |
| 13 | `time_bucket` | Must be identical across all leaves; becomes final `timeBucket`. |
| 14 | `consistency_ok` | Must be Boolean; contributes to exactly one of the two counts. |
| 15 | `drone_auth_ok` | Must equal `1` for this legacy leaf. It only means an EdDSA-Poseidon signature verified under a public key supplied by the prover; it does **not** prove that the key is authorized for this Remote ID. |
| 16 | `drone_operator_commitment` | Poseidon commitment to the supplied key only. It is not bound to `drone_id_commitment` by a trusted registry proof. |
| 17 | `freshness_pub` | Signed by the device inside the leaf proof.  Replay is rejected through `timeBucket` and the session nullifier transition. |

## Required acceptance rules

For every leaf, the aggregator must:

1. verify the proof using the pinned leaf verification key;
2. require `within30_and_detected == 1`;
3. require `drone_auth_ok == 1` as a legacy fixture filter only; do not interpret it as authenticated Remote ID ownership until the signer key is cryptographically bound to the asserted ID by a configured trust root;
4. require equality of `drone_id_commitment` and `time_bucket` with the first
   accepted leaf;
5. prove membership of the device public key under `memberRoot`;
6. apply the one-time session nullifier transition defined in
   [`nullifier-v1.md`](nullifier-v1.md);
7. compute, rather than accept from the caller, the two consistency counts.

`freshness_pub` is part of the device signature.  The final protocol uses a
time-bucketed session and one-time nullifier, so a proof from a prior session
cannot be counted again.  A deployment that needs a stricter real-time window
MUST add a versioned public freshness/epoch commitment rather than relying on a
relayer-provided timestamp.

## Security limitation: observer signature does not bind the RSSI outcome

This V1 leaf is a legacy regression format and MUST NOT be treated as a
cryptographically observer-attested RSSI report. Its device signature is over
`Poseidon(drone_id_commitment, target_commitment, frame_binding,
within30_and_detected, freshness)`. It omits both `measured_range_cm` and the
circuit-derived `consistency_ok`. A holder of an otherwise accepted V1
observation signature can therefore reuse that signature with another private
range; the circuit recomputes a potentially different `consistency_ok` for the
changed witness. The proof establishes that the chosen range and outcome are
internally consistent with the circuit, not that the registered observer
signed or measured that range.

This was reproduced on 2026-10-04 with the synthetic observer-2 fixture:
changing `measured_range_cm` from 5000 cm to 341 cm preserved the observer
signature, changed public signal 14 (`consistency_ok`) from `0` to `1`, and the
changed witness produced a Groth16 proof accepted by the checked-in V1
verification key. The reproducible helper is
[`audit_leaf_signature_v1_rebinding.js`](../../scripts/audit_leaf_signature_v1_rebinding.js).
It is an attack regression/audit for the legacy format, not evidence that an
RSSI sensor reported either value truthfully.

To repeat the proof-level check from the repository root:

```sh
mkdir -p /tmp/leaf-v1-rssi-binding-audit
circom circuits/uav_witness_attestation.circom --O2 --wasm -l node_modules -o /tmp/leaf-v1-rssi-binding-audit
node scripts/audit_leaf_signature_v1_rebinding.js zk-distance/samples/witness/input_dev2.json /tmp/leaf-v1-rssi-binding-audit/input_dev2_rebound.json
node /tmp/leaf-v1-rssi-binding-audit/uav_witness_attestation_js/generate_witness.js /tmp/leaf-v1-rssi-binding-audit/uav_witness_attestation_js/uav_witness_attestation.wasm /tmp/leaf-v1-rssi-binding-audit/input_dev2_rebound.json /tmp/leaf-v1-rssi-binding-audit/input_dev2_rebound.wtns
snarkjs groth16 prove rapidsnark_app/assets/circuits/uav_witness/distance30_witness_attestation_groth16.zkey /tmp/leaf-v1-rssi-binding-audit/input_dev2_rebound.wtns /tmp/leaf-v1-rssi-binding-audit/rebound-proof.json /tmp/leaf-v1-rssi-binding-audit/rebound-public.json
snarkjs groth16 verify rapidsnark_app/assets/circuits/uav_witness/distance30_witness_attestation_verification_key.json /tmp/leaf-v1-rssi-binding-audit/rebound-public.json /tmp/leaf-v1-rssi-binding-audit/rebound-proof.json
```

The final command reports `OK!`; `rebound-public.json[14]` is `1` while the
checked-in observer-2 public fixture has `0`.

Until a versioned leaf fixes this binding, aggregators and user-facing output
MUST label V1 `consistency_ok` as a prover-selected measurement evaluated by
the circuit, not as an observer-authenticated physical measurement. Do not
silently change V1: any changed constraint system requires a new protocol
identifier, R1CS/VK/verifier pin, release manifest, and regenerated proofs.

### Required V2 observer-signed payload

The versioned implementation and current validation status are maintained in
[`leaf-attestation-v2.md`](leaf-attestation-v2.md). The minimum payload
requirements remain:

V2 MUST domain-separate its signature message with a protocol/version tag and
bind at least the canonical Remote ID message commitment, observer credential,
session/epoch, target or location commitment, measured-range value (or a
measurement commitment that is opened and checked in-circuit), calibration
profile identifier, and the circuit-derived `consistency_ok`. The range and
calibration profile must be range-checked and constrained by the same V2
circuit; the signed outcome must be the exact output derived from those inputs.
All signers, witness generators, public-signal layouts, aggregator-pinned
keys, and EVM verifiers must agree on one field encoding and protocol version.

Even that signature proves only that the registered key endorsed those
values. It does not prove that RSSI was measured honestly or that the sensor,
clock, location, calibration, or device software was uncompromised. Those
require separate hardware, calibration, and field-evaluation controls. A V2
constraint change cannot reuse the V1 verification key or V1 proof fixtures.

## Current implementation status

`aggregator/cmd/aggregate` now enforces items 1–5 and count calculation.
`aggregator/pcd/BridgeBW` binds items 1–6 for one BN254 leaf: it verifies the
release-pinned leaf proof, reconstructs the same BN254 MiMC membership and
session-nullifier roots in BW6-761, and rejects a reused slot.  Binding the
resulting nullifier state into a general binary recursive merge remains the
remaining proof-generation integration work. `PrepareObserverBatch` now
verifies the three checked-in Circom fixtures against the pinned leaf VK,
resolves their keys against a separate registered-observer roster, and derives
the BridgeBW paths, nullifier states, and final-v1 statement. Its fixture roster
is explicitly synthetic and is not a production identity registry. The actual
BridgeBW proofs, recursive merge proofs, FinalBN proof, and EVM v1 verification
are still not connected end to end. The existing generated aggregate verifier
predates the new `drone_auth_ok` constraint and must be regenerated before
deployment.

### Authentication claim boundary

The current Circom circuit's `drone_auth_ok` is **not** a trusted Remote ID
authentication result. It verifies an experimental EdDSA-Poseidon message
using `drone_pubkey_ax/ay` supplied by the prover. It does not prove that this
key belongs to the asserted Remote ID, is registered, or is unrevoked. The
corresponding `drone_operator_commitment` hashes the key alone. Consequently,
the legacy leaf may be used for regression fixtures, but it must not be
presented as proving a registered aircraft's identity.

The PoC authentication target is DRIP Broadcast RID authentication per
[RFC 9575](https://www.rfc-editor.org/rfc/rfc9575.html): validate the applicable
UA-Signed Evidence and freshness/context, then validate the Broadcast
Endorsement chain binding the UA DET to its Host Identity. The trust anchor is
the configured DRIP registration hierarchy (root/RAA/DIME keys and policy),
not a key supplied with an individual proof. Observers must have the allowed
trust anchors and validity/revocation policy provisioned locally so broadcast
verification does not require live connectivity. [RFC 9153](https://www.rfc-editor.org/rfc/rfc9153.html)
describes the ownership, message-binding, and registration properties; it
also explains that F3411 Authentication Message framing alone does not define
the authentication method.

This target is **not yet implemented or proven inside the leaf/PCD circuits**.
Before a final proof may claim authenticated aircraft identity, a new protocol
version must bind the asserted DET/ID, signed evidence, endorsement chain,
trust-root version, and validity/revocation decision to a verifier the
aggregator cannot replace. Until then, report only “signature checked under a
prover-supplied key” or “authentication not established”; never label it
“registered/verified Remote ID”.
