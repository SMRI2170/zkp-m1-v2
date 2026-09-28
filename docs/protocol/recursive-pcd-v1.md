# Recursive PCD architecture for final-attestation-v1

## Decision

The protocol uses **direct recursive proof-carrying data (PCD)**, not a raw
folding accumulator.  A new node is valid only when its circuit verifies the
proof(s) for the node(s) it consumes.  Therefore a participant never has to
trust a relay, an aggregator, or the participant who created the previous
node.

The canonical aggregation topology is a binary merge tree.  A linear append is
permitted only when chronology is itself meaningful.  For independent witness
observations, a tree has lower end-to-end latency and does not make one delayed
device block every later device.

```text
leaf A ──┐
         ├── node AB ──┐
leaf B ──┘             │
                       ├── final node ABCD ──> final-attestation-v1 proof
leaf C ──┐             │
         ├── node CD ──┘
leaf D ──┘
```

Every arrow means “verify the child proof in the parent circuit”; it does not
mean an application-level `verify()` call that an adversary can skip.

## State committed by every node

All recursive nodes expose the following public state in the order specified by
[`final-attestation-v1`](final-attestation-v1.md):

```text
S = (
  protocolVersion, droneIdCommitment, timeBucket, policyCommitment,
  memberRoot, nullifierRoot, consistentCount, suspiciousCount, verdict
)
```

An intermediate node may keep `verdict` as `Undetermined`; the final circuit
calculates it under `policyCommitment`.  The values are public because a parent
circuit must bind them to its own statement.  Observation locations, RSSI,
device identifiers, nullifiers, membership paths, leaf proofs, and signatures
remain private witnesses.

## Fixed circuit family

The current `aggregator/cmd/chainpoc` is an educational three-level bootstrap:
its verifier witness shape is rebuilt for Genesis, Chain-A, then Chain-B.  It
proves the desired security property, but it cannot be extended indefinitely.

The production construction uses a fixed, mutually recursive pair of circuits
over an elliptic-curve cycle:

| Circuit | Native curve | It verifies | Role |
| --- | --- | --- | --- |
| `NodeBLS` | BLS12-377 | two `NodeBW` proofs | merge one tree level |
| `NodeBW` | BW6-761 | two `NodeBLS` proofs | merge the next tree level |
| `BridgeBW` | BW6-761 | a BN254 leaf proof | convert an approved leaf to the node state |
| `FinalBN` | BN254 | one `NodeBLS` or `NodeBW` proof | emit the EVM Groth16 proof |

The BLS12-377/BW6-761 pair is used because each curve's scalar field is the
other curve's base field, allowing the previous proof verifier to have a fixed
native representation.  `NodeBLS` and `NodeBW` are compiled and set up once;
tree depth changes only which of the two proof types is used next.

`aggregator/pcd/PinnedBLS12ProofCircuit` is the implemented fixed-key
primitive for the `BLS12-377 -> BW6-761` direction.  It uses gnark's
`ValueOfVerifyingKeyFixed`, so the child verification key is compiled as circuit
constants rather than accepted as a prover witness.  Its regression test proves
that a proof produced under a different, otherwise valid key is rejected.
`NodeBLS`/`NodeBW` still need their two-child state transition and mutually
released key artifacts before this primitive becomes the complete fixed PCD
family.

`BridgeBW` and `FinalBN` are intentionally separate from the repeating pair.
They isolate interoperability with existing BN254 Groth16 leaf proofs and with
the EVM boundary.  They must not be repeated at every merge.

## Node transition rules

For a merge node with left state `L`, right state `R`, and output `O`, the
circuit enforces:

```text
verify(leftProof, L)  = true
verify(rightProof, R) = true

L.protocolVersion == R.protocolVersion == O.protocolVersion == 1
L.droneIdCommitment == R.droneIdCommitment == O.droneIdCommitment
L.timeBucket         == R.timeBucket         == O.timeBucket
L.policyCommitment   == R.policyCommitment   == O.policyCommitment
L.memberRoot         == R.memberRoot         == O.memberRoot

O.consistentCount = L.consistentCount + R.consistentCount
O.suspiciousCount = L.suspiciousCount + R.suspiciousCount
O.verdict = Undetermined              // until FinalBN evaluates the policy
```

`nullifierRoot` is deliberately not specified as a simple equality or hash of
two roots.  The merge must prove that the two child nullifier sets are disjoint
and calculate one canonical next root.  Its Merkle hash is the domain-separated
`MiMC_BN254` construction used by `aggregator/membership`; `policyCommitment`
remains a Poseidon field commitment.  This is the security-critical Step C work
in Issue #3.  No production merge circuit may be enabled before that transition
is implemented.

An optional chronological append is just a merge with a singleton bridge node.
It uses the same rules and cannot introduce a second, weaker state machine.

## Safe handling of incomplete trees

The protocol does not use a dummy “empty proof” as a public shortcut.  An odd
leaf may remain an independently verifiable node until another leaf arrives,
or a finalizer may use a dedicated one-child final circuit that preserves all
state unchanged.  Both alternatives avoid treating an unchecked placeholder as
a witness observation.

## Finalization

`FinalBN` verifies the root node, validates all v1 ranges, derives `verdict`
from the policy threshold and counts, and creates the nine-input BN254 Groth16
proof.  The EVM contract derives `sessionId` using the canonical ABI defined in
`final-attestation-v1.md`; it does not rely on a relayer-supplied session key.

## Security invariants and negative tests

The implementation must reject each of these before a final proof can exist:

1. a child proof with an invalid verification key or altered public witness;
2. left and right children from different drone, time bucket, policy, member
   root, or protocol version;
3. an overflow or a count that is not the sum of the child counts;
4. a leaf whose result bit is inconsistent with its private RSSI calculation;
5. duplicate device participation once Issue #3 introduces nullifier roots.

## Delivery sequence

1. Keep `chainpoc` as the small direct-recursion security regression test.
2. Implement `BridgeBW`, `NodeBLS`, and `NodeBW` with placeholder nullifier
   transition gated off from production use.
3. Implement the authenticated nullifier-set transition in Issue #3.  The
   repository now has a tested two-device ordered transition; arbitrary
   child-root union/disjointness remains required before enabling binary
   recursive merges.
4. Connect real leaf attestations in Issue #4.
5. Implement `FinalBN` and its EVM verifier in Issue #5.

This order avoids claiming that a fast folding accumulator, an application
wrapper, or an unchecked resume state is equivalent to PCD.
