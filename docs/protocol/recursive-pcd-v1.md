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

### Encoding across the curve cycle

The BN254 scalar field used by leaf proofs and final EVM statements is 254
bits, whereas the BLS12-377 scalar field is 253 bits. A BN254 value must not be
copied as one BLS public input because it could be reduced and change meaning.
`aggregator/pcd/state_encoding.go` fixes the transport format as four
little-endian 64-bit limbs per BN254 state value. `NodeBLS` emits 36 public
limbs; `NodeBW` checks those limbs and emits nine canonical BN254 values in its
BW6-761 scalar field. The encoder/decoder reject noncanonical values and
out-of-range limbs.

## State committed by every node

The final proof exposes the nine values specified by
[`final-attestation-v1`](final-attestation-v1.md). Intermediate PCD nodes use
this distinct nine-value state, which retains both the initial and populated
nullifier roots and postpones verdict calculation:

```text
S = (
  protocolVersion, droneIdCommitment, timeBucket, policyCommitment,
  memberRoot, oldNullifierRoot, newNullifierRoot,
  consistentCount, suspiciousCount
)
```

Parents bind this state across proofs; `FinalBN` maps `newNullifierRoot` to the
external `nullifierRoot` and calculates `verdict` under `policyCommitment`.
Observation locations, RSSI, device identifiers, nullifier leaves, membership
paths, leaf proofs, and signatures remain private witnesses.

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
other curve's base field, allowing recursive proof verifiers to have a fixed
representation. The intended tree alternates proof types, but their mutually
fixed verification-key setup and release are not yet established. Do not treat
“set up once” as a completed or solved bootstrap procedure.

`aggregator/pcd/PinnedBLS12ProofCircuit` is the implemented fixed-key
primitive for the `BLS12-377 -> BW6-761` direction.  It uses gnark's
`ValueOfVerifyingKeyFixed`, so the child verification key is compiled as circuit
constants rather than accepted as a prover witness.  Its regression test proves
that a proof produced under a different, otherwise valid key is rejected.
`NodeBW` and `NodeBLS` pin their child key and implement two-child binary state
transitions. Both privately open the fixed 16-slot child nullifier sets, verify
each root with emulated MiMC_BN254, reject overlapping observer indexes,
recompute the union root, and bind child counts to occupied slots. `NodeBLS`
emits the 36-limb representation; `NodeBW` validates and decodes it.
`BridgeBW` pins a BN254 leaf key, verifies the documented 18-signal leaf
layout, rejects missing Remote ID/detection flags, maps drone/time/result into
state, verifies the device membership path, and changes exactly that device's
session-nullifier slot from zero to its domain-separated nullifier.

For the PoC's first fixed batch of exactly three observers, an acyclic topology
is now represented in code:

```text
BridgeBW(leaf 0) ─┐
                  ├─ NodeBLS(0,1) ─┐
BridgeBW(leaf 1) ─┘                ├─ NodeBW ─ FinalBN
BridgeBW(leaf 2) ─ PromoteBLS ────┘
```

`PromoteBLS` verifies the third real BridgeBW proof and preserves its state; it
is not a dummy proof. Setup can proceed topologically: BridgeBW first, then
NodeBLS and PromoteBLS, then a NodeBW with separate pinned child VKs, then
FinalBN. The constructors and off-circuit `PrepareObserverBatch` /
`MergeObserverStates` plumbing are implemented. Tests verify the checked-in
Circom leaf proofs against the pinned leaf VK, check a separately fixed
synthetic observer roster and paths, and derive the three-leaf merged state.
This does not prove that the large recursive circuits can be compiled, set up,
or proved within available resources; no BridgeBW or final proof artifact has
been generated yet. The unbounded alternating NodeBLS/NodeBW family remains a
separate scaling design and still has its own mutually fixed key bootstrap.

`aggregator/cmd/pcd3` is the reproducible driver for this finite topology.
`cd aggregator && go run ./cmd/pcd3 --stage=plan --allow-manifest-root-for-test`
loads the pinned Circom VK,
verifies the three checked-in leaf proofs, resolves their keys against the
separate synthetic roster, and prints the fixed topology and final public
statement. It performs no recursive compile or setup. The driver also has an
explicit `--stage=run` path which compiles and sets up each layer in order,
then proves/verifies the three bridges, `NodeBLS`, `PromoteBLS`, `NodeBW`, and
`FinalBN`. Setup artifacts are write-once, hashed, and tied to source and
parent-artifact hashes so a partial or stale stage is not silently reused.
That run path has **not yet been executed**: it performs large recursive
compiles and random local Groth16 setup, which is neither a trusted ceremony
nor a production key. The exported Solidity verifier and final proof artifact
are research outputs only; this command does not yet deploy or call the v1 EVM
registry/verifier.

The checked-in roster is synthetic. Outside offline tests, pass
`--active-member-root` with a value obtained independently from the
authoritative registry. `pcd3` recomputes the roster root and rejects a
mismatch; the test-only opt-in does not authenticate the manifest.

Once a final artifact exists, setting `PCD3_FINAL_ARTIFACT` when running
`./scripts/run_e2e_demo.sh` invokes
`contracts/scripts/verify_pcd3_final_evm.js`. That optional local-EVM harness
checks the verifier-source hash, compiles the generated Solidity, requires the
exact `verifyProof(bytes,uint256[9])` ABI, verifies the real proof, rejects a
tampered public input, deploys `FinalAttestationRegistryV1` with that generated
verifier, and checks the persisted record. Its compiler/ABI helper has unit
tests now, but the artifact-backed verifier/registry flow has not run because
there is not yet a generated FinalBN proof artifact.

The node regression fixtures are synthetic child circuits, not yet actual
`BridgeBW -> NodeBLS -> NodeBW` proof artifacts. The mutually fixed node-key
setup and a complete proof-generation path remain unresolved release gates.
Passing node tests establishes the merge relation for these fixtures; it does
not establish a releasable recursive PCD family.

`BridgeBW` and `FinalBN` are intentionally separate from the repeating pair.
They isolate interoperability with existing BN254 Groth16 leaf proofs and with
the EVM boundary.  They must not be repeated at every merge.

`aggregator/pcd/FinalBN` is now implemented as a BN254 circuit. It pins and
verifies one BW6-761 root key, rejects noncanonical BW6 state values at the
BN254 boundary, requires the old nullifier root to be the empty session root,
maps the verified union state to the fixed nine public inputs, and derives
the quorum verdict using the v1 Circomlib Poseidon commitment. Regression
tests use a small BW6 proof to verify both successful wrapping and altered
statement rejection. `RUN_FINAL_BN_COMPILE=1 go test ./pcd
-run '^TestFinalBNCompilesToNinePublicInputs$'` compiles the outer circuit and
checks that it exposes exactly nine public inputs.

This is a circuit implementation, not yet a releasable end-to-end proof
artifact. The released root key must be the production `NodeBW` key. The
recursive-key bootstrap, actual leaf-to-root proof generation, and generated
Solidity verifier remain release work; test-only setup keys must never be
deployed.

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
L.oldNullifierRoot   == R.oldNullifierRoot   == O.oldNullifierRoot

root(L.nullifierLeaves) = L.newNullifierRoot
root(R.nullifierLeaves) = R.newNullifierRoot
L.nullifierLeaves[i] * R.nullifierLeaves[i] = 0 for every registered index i
O.newNullifierRoot = root(L.nullifierLeaves + R.nullifierLeaves)
L.count = occupiedSlots(L.nullifierLeaves)
R.count = occupiedSlots(R.nullifierLeaves)

O.consistentCount = L.consistentCount + R.consistentCount
O.suspiciousCount = L.suspiciousCount + R.suspiciousCount
```

Here `count` means the child's `consistentCount + suspiciousCount`. The
`NodeBLS`/`NodeBW` relation enforces these checks with a fixed-depth emulated
BN254 MiMC tree. The finalizer requires the shared initial root to be the empty
session tree. The membership registry must also provide a canonical set with
unique observer keys; duplicate enrollment at multiple Merkle positions would
otherwise defeat index-based uniqueness.

The implementation checks can be rerun with `cd aggregator && go test ./...`.
The more expensive BLS12-377 recursive direction is exercised separately with
`cd aggregator && RUN_RECURSIVE_PCD_HEAVY=1 go test ./pcd -run
'^TestNodeBLSBinaryUnionOfDisjointChildren$' -count=1`. Both use synthetic
child circuits and must not be presented as actual leaf-to-EVM integration.

The low-resource preflight in `./scripts/run_e2e_demo.sh` additionally runs
`go test ./cmd/pcd3` and `go run ./cmd/pcd3 --stage=plan`. The plan verifies the
actual checked-in leaf proofs and synthetic roster but deliberately performs
no recursive compile, key setup, proof generation, or EVM call.
The v1 test step also exercises Solidity compilation and ABI-width rejection
for the generated-verifier harness; this does not substitute for executing an
actual generated FinalBN proof on EVM.

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
from the policy quorum and counts, and constrains the nine-input BN254 Groth16
statement. The prover/key-release command that produces a deployable proof
artifact remains to be connected after the recursive node family is
production-safe. The EVM contract derives `sessionId` using the canonical ABI
defined in `final-attestation-v1.md`; it does not rely on a relayer-supplied
session key.

## Security invariants and negative tests

The implementation must reject each of these before a final proof can exist:

1. a child proof with an invalid verification key or altered public witness;
2. left and right children from different drone, time bucket, policy, member
   root, or protocol version;
3. an overflow or a count that is not the sum of the child counts;
4. a leaf whose result bit is inconsistent with its private RSSI calculation;
5. duplicate device participation at the same registered index (covered by
   the binary-union gadget and recursive node fixtures).

## Delivery sequence

1. Keep `chainpoc` as the small direct-recursion security regression test.
2. The fixed-depth nullifier set union and canonical cross-curve state encoding
   are integrated into both node relations and pass synthetic child-proof tests.
3. Generate and verify the finite three-observer topology above from the
   checked-in real leaf fixtures, then produce reproducible binary-node proofs.
   Measure compile/setup/prove resources before attempting a larger alternating
   tree. The general mutually fixed NodeBLS/NodeBW key bootstrap remains an
   unresolved scaling dependency.
4. Deliver an actual nine-input v1 proof through `FinalBN` and an EVM verifier.
   A direct three-proof BN254 batch was measured at 6,820,657 constraints; setup
   did not complete within 7m44s and was stopped when the shared host approached
   17GB swap. A BW6 direct batch compiled to 8,284,443 constraints but has not
   been set up or proved. Therefore “fixed-size direct batch” is not yet a
   demonstrated fallback. Continue with resource-gated finite-depth circuit
   families whose VKs can be set up topologically, or evaluate another proof
   architecture without weakening child-proof verification.
5. Bind real BLE/RSSI measurements and the versioned Remote ID authentication
   root to the leaf proof; publish the experiment and remaining threat model.

This order avoids claiming that a fast folding accumulator, an application
wrapper, or an unchecked resume state is equivalent to PCD.
