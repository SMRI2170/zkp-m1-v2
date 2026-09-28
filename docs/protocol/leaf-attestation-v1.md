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
| 15 | `drone_auth_ok` | Must equal `1`; this means the circuit verified the signed Remote ID. |
| 16 | `drone_operator_commitment` | Reserved for policy-level allowlisting in a future version. |
| 17 | `freshness_pub` | Signed by the device inside the leaf proof.  Replay is rejected through `timeBucket` and the session nullifier transition. |

## Required acceptance rules

For every leaf, the aggregator must:

1. verify the proof using the pinned leaf verification key;
2. require `within30_and_detected == 1`;
3. require `drone_auth_ok == 1`;
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

## Current implementation status

`aggregator/cmd/aggregate` now enforces items 1–5 and count calculation.  The
nullifier transition has a tested reference circuit in `aggregator/nullifier`;
binding it into the fixed recursive node family is the remaining integration
work.  The existing generated aggregate verifier predates the new
`drone_auth_ok` constraint and must be regenerated before deployment.
