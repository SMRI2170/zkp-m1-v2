# Nullifier transition for final-attestation-v1

## Goal

This transition prevents a registered device from contributing more than once
to one observation session without revealing the device identity in the final
proof or on-chain record.

The one-device transition is an append from a zero slot. Independently created
child reports are combined with a binary disjoint-set union proof; neither
operation may trust a relayer-supplied root transition.

## Trees and indexing

There are two depth-`D` `MiMC_BN254` Merkle trees with the same private path
bits for each device.

| Tree | Leaf at device index | Root |
| --- | --- | --- |
| Authorisation tree | `MiMC(devicePubKeyX, devicePubKeyY)` | `memberRoot` |
| Per-session nullifier tree before use | `0` | `oldNullifierRoot` |
| Per-session nullifier tree after use | session-specific nullifier | `newNullifierRoot` |

The registration authority MUST reject duplicate public keys when constructing
`memberRoot`.  Otherwise a malicious registrant could occupy multiple indexes.

## Domain-separated commitments

All values are BN254 scalar-field elements and use the existing sequential
`MiMC_BN254` encoding (32-byte big-endian field elements).

```text
sessionCommitment = MiMC(42020, protocolVersion, droneIdCommitment,
                         timeBucket, policyCommitment)

deviceLeaf        = MiMC(devicePubKeyX, devicePubKeyY)
nullifier         = MiMC(42021, deviceLeaf, sessionCommitment)
```

`protocolVersion == 1` is constrained in the transition circuit.  The session
commitment is recomputed in-circuit, so a caller cannot reuse a nullifier tree
under another drone, bucket, or policy by supplying a chosen commitment.

## Required circuit constraints

1. `deviceLeaf` has a valid Merkle path to `memberRoot`.
2. The same path bits prove that a zero leaf belongs to `oldNullifierRoot`.
3. Replacing only that zero leaf with `nullifier` produces `newNullifierRoot`.
4. `nullifier != 0`.

After a successful transition, attempting to use the same device again while
claiming a zero old leaf cannot reconstruct `newNullifierRoot`; proof creation
therefore fails.

## Implementation and scope

The reference implementation is
[`aggregator/nullifier`](../../aggregator/nullifier): it includes circuit and
off-circuit MiMC functions plus negative tests.  `PairCircuit` also performs
two ordered append transitions in one proof:

```text
oldRoot -- authorised device A --> intermediateRoot
        -- authorised device B --> newRoot
```

The second path is checked against `intermediateRoot`, not `oldRoot`; this is
what makes an attempted second use of device A fail. `PairCircuit` is a
sequential append primitive. The recursive PCD instead uses the independent
set-union relation below, because observers produce their child proofs in
parallel rather than sharing an ordered root handoff.

`aggregator/nullifier/MergeCircuit` provides the native BN254 fixed-depth
(16-slot) union primitive. The same relation is now implemented with an
emulated BN254 MiMC gadget in `aggregator/pcd/NodeBLS` and `NodeBW`: each parent
privately opens both child leaf vectors, binds them to the child roots, rejects
overlapping occupied indexes, and recomputes the union root. Each child's
`consistentCount + suspiciousCount` is also bound to its occupied nullifier
slots. Tests accept disjoint roots and reject duplicate-slot and forged-root
assignments. `BridgeBW` initializes a singleton session tree from a verified
leaf proof.

This is binary set union, not an ordered `left.newRoot == right.oldRoot`
handoff. Both child states retain the same initial session root while their
populated roots are unioned. The finalizer requires the shared initial root to
be the canonical empty tree, so independently created reports can be merged
without an artificial arrival order.

The index-based uniqueness invariant assumes the authorized membership tree
contains each observer key at most once. The current owner-operated root
workflow does not itself prove enrollment uniqueness; production registration
must reject duplicate keys or use a canonical unique-set tree.

The final v1 proof exposes only `memberRoot` and the resulting
`nullifierRoot`; it does not expose `deviceLeaf`, the path, or `nullifier`.
