# Final Attestation Protocol v1

## Purpose

`final-attestation-v1` is the public statement proved by the final recursive
prover and verified by an EVM contract.  It deliberately describes **what was
proved**, not the recursion implementation used to produce the proof.  A
gnark, Halo2, or zkVM implementation may be substituted only if it produces a
Groth16/BN254 proof for this exact statement.

The statement means:

> During one observation session, only authorised devices contributed at most
> once each; their valid leaf observations were evaluated under one policy; and
> the published counts and verdict are the result of that evaluation.

Individual device identifiers, positions, RSSI readings, Merkle paths, leaf
proofs, and device secrets are private witnesses.  They must never be public
inputs or stored on-chain.

## Version and field rules

- Protocol version: `1`.
- Proof system at the EVM boundary: Groth16 over BN254 / alt_bn128.
- Every public input is a canonical BN254 scalar field element, i.e. an
  unsigned integer strictly less than
  `21888242871839275222246405745257275088548364400416034343698204186575808495617`.
- `timeBucket` is a Unix-time bucket encoded as an unsigned `uint64` and then
  represented by the same integer in the scalar field.
- `consistentCount` and `suspiciousCount` are unsigned `uint32` values.
- `policyCommitment` is a Poseidon commitment in the BN254 scalar field.
- `memberRoot` and `nullifierRoot` use the domain-separated `MiMC_BN254`
  Merkle construction defined by the aggregation circuit.  The existing
  `aggregator/membership` implementation is the reference until a versioned
  migration is explicitly specified.  A byte hash must not be reduced modulo
  the field.

## Canonical public-input ABI

The verifier takes exactly nine `uint256` values in this order.  Their index is
part of the protocol and may not be reordered.

| Index | Name | Type / range | Meaning |
| ---: | --- | --- | --- |
| 0 | `protocolVersion` | constant `1` | Selects this statement and ABI. |
| 1 | `droneIdCommitment` | field element | Privacy-preserving commitment to the claimed Remote ID. |
| 2 | `timeBucket` | `uint64` | Observation time window. |
| 3 | `policyCommitment` | field element | Poseidon commitment to the signed RSSI/freshness/policy parameters. |
| 4 | `memberRoot` | field element | Root of the authorised witness-device Merkle tree. |
| 5 | `nullifierRoot` | field element | Root committing to the devices already counted for this session. |
| 6 | `consistentCount` | `uint32` | Number of valid observations consistent with the claim. |
| 7 | `suspiciousCount` | `uint32` | Number of valid observations inconsistent with the claim. |
| 8 | `verdict` | `0`, `1`, or `2` | `Undetermined`, `Trusted`, or `SpoofSuspected`. |

The final circuit MUST constrain the following:

1. all accumulated leaves use the same values at indexes 0–4;
2. every counted leaf has valid membership under `memberRoot`;
3. no device nullifier is counted twice, and the resulting state is
   `nullifierRoot`;
4. `consistentCount + suspiciousCount` is the number of accepted leaves;
5. `verdict` is calculated from these counts and the threshold encoded by
   `policyCommitment`, rather than chosen by the prover.

## EVM session identifier

`sessionId` is an EVM storage and event identifier, **not** a Groth16 public
input.  A `bytes32` Keccak hash is not automatically a BN254 field element, so
including it as a field input would introduce ambiguous reduction rules.

It is derived canonically after proof verification:

```solidity
keccak256(
    abi.encode(
        uint8(1),
        uint256(droneIdCommitment),
        uint64(timeBucket),
        uint256(policyCommitment)
    )
)
```

Solidity MUST use `abi.encode`, not `abi.encodePacked`, for this definition.
The result separates sessions whose policy changes even if their drone and time
bucket match.

## Encoding and compatibility

- JSON test vectors represent all field elements and counts as decimal strings.
- Solidity ABI values are `uint256`; values outside the ranges above MUST be
  rejected before the verifier call.
- The Groth16 proof encoding is verifier-specific.  The deployed verifier
  address, its bytecode hash, the verification-key hash, and the circuit source
  hash are release artifacts, not protocol-version substitutes.
- Any change to an index, range, hash domain separator, verdict rule, or
  session-ID preimage requires a new `protocolVersion`.

## Current migration status

The current aggregate PoC and `FinalAttestationRegistry` use the earlier
five-input order `(droneIdCommitment, timeBucket, consistentCount,
suspiciousCount, memberRoot)`.  They are useful prototypes but are **not
`final-attestation-v1`**.  Issue #5 will generate the nine-input verifier and
Issue #6 will migrate the registry only after the recursive and nullifier
requirements are implemented.

## Test vectors

Canonical values and the expected EVM `sessionId` are in
[`test-vectors/final-attestation-v1.json`](test-vectors/final-attestation-v1.json).
The Hardhat test validates that the Solidity ABI derivation matches these
vectors.  Circom and recursive-prover implementations must consume the same
vector before claiming v1 compatibility.
