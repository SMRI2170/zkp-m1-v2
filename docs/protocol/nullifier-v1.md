# Nullifier transition for final-attestation-v1

## Goal

This transition prevents a registered device from contributing more than once
to one observation session without revealing the device identity in the final
proof or on-chain record.

It applies to an append transition.  A binary PCD merge needs a disjoint-set
union proof and is deliberately not enabled until that proof is implemented.

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
what makes an attempted second use of device A fail.  It provides a safe
two-device building block for a recursive node without exposing either
nullifier.

This is deliberately an ordered append, **not** a general binary union of two
already-populated child nullifier roots.  A recursive merge of arbitrary child
subtrees still needs a proof that their sets are disjoint and that their
canonical union has the advertised root.  It is not yet connected to a leaf
proof or to the fixed recursive PCD family.  Those integrations belong to
Issues #4 and #2 respectively.

The final v1 proof exposes only `memberRoot` and the resulting
`nullifierRoot`; it does not expose `deviceLeaf`, the path, or `nullifier`.
