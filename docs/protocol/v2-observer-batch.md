# V2 multi-observer batch preflight

Status: the Go preflight verifies V2 Groth16 leaf proofs, builds V2 bridge
assignments, and enforces a common session and profile-set root plus distinct
membership in a roster root. Individual observers may use different profile
IDs only when each leaf proves membership in that same approved root. The
revised BLE/RSSI-only leaf compiles with 6,201 constraints and 8 outputs;
`scripts/test_leaf_v2_binding.sh` confirms a synthetic far-mismatch witness has
output 0 `1` and output 5 `0`. On 2026-10-04 the updated disposable integration
generated proofs for this relation, passed proof-backed host batch integration,
and verified a leaf proof with a generated local EVM verifier (including five
public-signal tamper rejections). Its `pcd3 --stage=plan` reported one
consistent and two suspicious observers, with `VerdictSpoofSuspected`. The
current leaf relation has now passed the optional BridgeBWV2 test-engine solve
using an actual far-mismatch leaf proof; both member-path and profile-path
tampering were rejected. No outer BW6 Groth16 proof has been created. Earlier V2 proof/VK/bridge results
from other leaf relations are stale. No committed release verifier is pinned.
This is **not** a completed recursive aggregation, final ZK attestation, or
release integration.

As of 2026-10-04, the code also has protocol-version-pinned `NodeBLS`,
`NodeBW`, and `PromoteBLS` constructors, a separate 10-public-input
`FinalBNV2`, and a `pcd3 --protocol=v2` path for a fixed three-observer tree.
The current leaf relation has also passed a disposable proof-backed
`pcd3 --stage=plan` run, which produced the expected one-consistent/two-
suspicious verdict. This checks input verification and host-side planning only;
the path has not generated recursive proofs or reached FinalBNV2 EVM. Its local
Groth16 setup must remain research-only, and the V2 leaf VK still needs an
independently reviewed release process before it can be treated as a trust
root.

## Accepted statement

`VerifyV2ObserverBatch` in `aggregator/pcd/v2_observer_batch.go` accepts a
caller-pinned V2 verification key, leaf proof/public-witness pairs, the
registered observer roster and its separately obtained active root, an
explicit calibration-profile allowlist, and a quorum. It verifies each leaf
proof before using its public values, then requires:

- at least two proofs, each with exactly 8 public signals;
- `observation_eligible == 1` and `consistency_ok` boolean;
- the same `drone_id_commitment` (signal 1) and `time_bucket` (signal 4). The
  commitment is a run-key/run-ID/time-bucket-scoped pseudonym for an equal
  claimed broadcast RID, not proof that the physical aircraft or RID is authentic;
- signed observation timestamp (signal 6) equals `target_time_sec` by the leaf
  constraint; the host preflight also checks it is in the same 60-second bucket;
- a uint32 calibration profile (signal 7) whose domain-separated MiMC leaf
  opens the same approved fixed-depth profile-set Merkle root in `BridgeBWV2`;
- each observer public key (signals 2–3) resolves to a different registered
  roster entry, and the roster recomputes to the active root;
- quorum outcome derived from the verified consistency outputs.

Signal 0, `observation_eligible`, is 1 only when the advertised and observer
timestamps are within five seconds and measured range is positive. Position
inconsistency is deliberately not an admission gate: a far mismatch must be
accepted with `consistency_ok == 0` so multiple suspicious reports can reach the
quorum policy. This avoids dropping the exact reports the PoC is meant to
aggregate. It still does not prove that a physical BLE packet was received or
that a sensor honestly measured RSSI. The leaf-to-real-capture signer path is
open; see [the capture-to-proof gap](leaf-attestation-v2.md#capture-to-proof-gap).

The return value calls this a `ProvisionalVerdict` on purpose. It also returns a
host-computed `PolicyCommitment`:

The V2 verdict keeps the existing numeric public-input ABI (`0/1/2`) but uses
deliberately narrow meanings: `0 = INSUFFICIENT_EVIDENCE`,
`1 = NO_INCONSISTENCY_OBSERVED`, and
`2 = POSITION_INCONSISTENCY_SUSPECTED`. In particular, value `1` is not
`Trusted`: agreement among these reports does not prove aircraft identity,
Remote ID authenticity, observer location, or sensor honesty. V1 retains its
legacy `Trusted` label and ABI; this clarification applies to V2 only.

`pcd3 --protocol=v2 --stage=plan` renders this symbolic label next to the
unchanged numeric verdict. `FinalAttestationRegistryV2` uses the same symbolic
enum names while preserving their numeric order, so existing V2 statement
encoding and verifier inputs remain unchanged.

```text
profileLeaf = MiMC(FinalPolicyV2ProfileDomainTag, profileID)
profileSetRoot = MiMC-Merkle(profileLeaf[sorted allowlisted uint32 IDs])
parameters = Poseidon("UAV_V2_PROFILE_POLICY", minimumQuorum, profileSetRoot)
policy     = Poseidon("UAV_FINAL_POLICY_V2", 2, parameters)
```

The fixed tree depth is four (at most 16 profile IDs); IDs are sorted before
tree construction, and unused leaves are zero-padded by the shared membership
tree implementation. Reordering an allowlist therefore cannot change its
root. The Go and gnark final-verdict gadget implementations have an independent
circomlibjs Poseidon vector test, and the gadget rejects another set root,
quorum, or version. The same hash was also checked with an emulated BN254 field
inside a BW6-761-native test circuit. `BridgeBWV2` binds the policy commitment
and verifies each profile path; `FinalBNV2` exposes the profile-set root at
public input 4 and `policyCommitment` at input 3. The V2 EVM registry stores
that canonical BN254 root and requires the exact policy commitment to be
approved. Prior experimental V2 final proofs/VKs and registry fixtures using a
single profile ID at input 4 are schema-incompatible and must be regenerated.
Each `BridgeBWV2` proves a single observer transition from the empty
session-nullifier root: `deviceLeaf = MiMC(observerPubKeyX, observerPubKeyY)`,
`session = MiMC(SessionDomain, protocolVersion, droneIdCommitment, timeBucket,
policyCommitment)`, and `nullifier = MiMC(NullifierDomain, deviceLeaf, session)`.
It inserts that nullifier at the same private roster index. `NodeBLSV2` and `NodeBWV2` bind
each private fixed-capacity leaf vector to its child root, reject overlap at
any roster index, and prove the union root; `FinalBNV2` exposes only that root.
Host preflight and merge-gadget tests cover this relation, but the recursive
proof pipeline has not yet proven it end to end on this host. The nullifier is
session-scoped rather than a persistent cross-session spend record. The final
registry accepts only one finalization for a `(droneIdCommitment,timeBucket)`
and one use of proof bytes, preventing alternate accepted results for that
session. These cryptographic checks do not prove that registered credentials
belong to distinct people, physical devices, or sites; enrollment governance
must address Sybil identities. The nullifier is derived from the public-key
leaf, not a separate observer secret: if a watcher also knows the ordered
candidate roster, it can enumerate the at-most-16 slots and identify the
participants from the final root. Do not claim roster-independent on-chain
anonymity; use a secret-derived credential commitment in a new protocol if
that threat is in scope. Profile IDs
must identify immutable records; different calibration coefficients, hardware
scope, effective dates, or approval state require new IDs. The ID alone does
not make that governance true. At the leaf, signed freshness is constrained to
`target_time_sec`, from which the time bucket is derived. The preflight checks
bucket membership. The final registry checks age/future bounds on the bucket
start, not on the hidden exact timestamp: with a 60-second bucket, default
settings permit up to roughly 180 seconds of age and roughly 64 seconds of
future timestamp at the extremes. This is a coarse bound and cannot prove the
observer clock or radio receive time; it must not be described as trusted
time. This function must not be used as a final-attestation verifier.

Profile membership proves only that the signed profile ID is in the approved
set. The leaf receives `measured_range_cm` after its RSSI-to-range conversion
outside the circuit; it binds that value, the profile ID, and the derived
consistency result to the observer signature, but it does not prove that raw
RSSI came from an unmodified receiver or that the stated profile coefficients
were applied correctly. Hardware calibration, collection provenance, and
held-out field evaluation remain separate trust/evidence requirements.

The revised V2 circuit has no drone self-signature placeholder. It commits the
claimed Remote ID value for session grouping but does not authenticate it or
bind it to a DRIP registration trust root. An authenticated RID result remains
unavailable until a real trust-chain/content verifier is integrated and
policy-bound.

## Reproducible adversarial test

From the repository root:

```sh
bash scripts/test_v2_observer_batch.sh
```

The updated script was run on 2026-10-04 against the BLE/RSSI-only relation.
It passed proof-backed multi-observer integration for two synthetic
far-mismatch reports and the suspicious quorum. Each run creates and deletes a
new single-contributor test setup, so the generated VK must never be published
or treated as a release trust root.

The script compiles the V2 circuit, creates a **single-contributor disposable
test setup**, proves three baseline synthetic observers, variants with a
different profile and a different 60-second time bucket, plus two large
position/RSSI mismatch observers under distinct keys. It runs
`TestV2ObserverBatchProofIntegration` against those actual proofs and covers:

- three valid registered observers with a 2 consistent / 1 suspicious summary;
- a consistent report plus two far-mismatch reports remaining eligible and
  deriving the suspicious quorum verdict;
- duplicate observer rejection;
- mixed-profile acceptance when every profile is allowlisted, plus
  non-allowlisted profile rejection using a valid alternate-profile proof;
- different time-bucket rejection using a valid alternate-session proof;
- a mutated public profile signal rejected against its original proof;
- a mutated signed timestamp rejected against its original proof;
- V1 VK rejection for V2 leaves;
- creation of 8-signal `BridgeBWV2` assignments, profile/member/nullifier path
  openings, V2 policy/count state, and V1/V2 merge separation.

The script also verifies a base leaf in a freshly generated Solidity verifier on
local EVM, rejects five changed public signals, and runs `pcd3 --protocol=v2
--stage=plan` with one consistent and two far-mismatch current-relation proofs,
the `{1,2}` profile set, and the synthetic observer roster. Thus the planned
final statement targets the suspicious-quorum result from real leaf proofs,
but `--stage=plan` does not create recursive proofs.

The checked-in synthetic captures have 2024 timestamps. The integration script
shifts only its disposable generated copies to the start of the current minute
so a future final-registry test can exercise the deployed freshness rule rather
than failing on stale test data. For that final test only, the local Hardhat
chain clock is pinned to 30 seconds after the synthetic bucket start via
`PCD3_V2_EVM_INITIAL_DATE`; the registry freshness limits are not relaxed.
When `TMPDIR` points at an external/noexec volume, Go build temporaries remain
in `/tmp` via `GOTMPDIR` so the test binary can execute.

The alternate-session fixture remains a synthetic claimed-RID input; there is
no drone signature check in the current BLE/RSSI-only leaf. All fixtures,
temporary proving keys and ceremony material are
created under one `mktemp` directory and deleted when the script exits by
default. Set `UAV_V2_BATCH_KEEP_FIXTURES=1` only when reusing the disposable
fixtures for another gated test; it prints the retained directory. This
single-operator setup is strictly test-only and is not suitable for publishing
a VK or claiming a trusted ceremony. The integration script is intentionally
slow and separate from ordinary `go test ./...`; without its environment,
the integration test skips.

To additionally attempt the complete recursive setup/prove pipeline and
FinalBNV2 verifier + registry EVM check, opt in explicitly:

```sh
RUN_BRIDGE_BW6_SOLVE=1 RUN_PCD3_V2=1 PCD3_GOMAXPROCS=2 \
UAV_V2_BATCH_KEEP_FIXTURES=1 bash scripts/test_v2_observer_batch.sh
```

`RUN_PCD3_V2=1` without `UAV_V2_BATCH_KEEP_FIXTURES=1` is rejected before
creating temporary files. This prevents an interrupted expensive attempt from
silently deleting artifacts needed to inspect or resume it.

This gate is resource-intensive and remains incomplete on this machine. On
2026-10-04 the current BridgeBWV2 compiled at 2,285,785 constraints. While its
local Groth16 setup was running, host swap usage was observed at 7,841.69 MiB
of 8 GiB (334.31 MiB free); the run was interrupted to protect the host. No
recursive proof or FinalBNV2 EVM result was produced. It uses test-only local Groth16 setups,
caps Go parallelism at two by default, and must never create a release trust
root. Keeping fixtures preserves failed or completed stage artifacts for
inspection. A completed stage with a matching `stage.json` hash manifest is
reused; an incomplete or mismatched stage fails closed and is not guaranteed to
resume automatically. Retained directories contain large proving keys and
must be handled and removed deliberately after review.

If the full recursive gate is interrupted, preserve its fixture directory and
resume against that exact directory rather than regenerating leaf keys/proofs:

```sh
PCD3_GOMAXPROCS=1 bash scripts/resume_v2_observer_batch.sh \
  /Volumes/SSD/uav-v2-observer-batch.XXXXXX
```

The resume script requires a named disposable fixture directory and the saved
leaf VK/proofs. Before `pcd3 --stage=run`, it recompiles the current leaf
Circom source, verifies the saved zkey against that exact R1CS and Powers of
Tau file, and compares the exported VK with the saved leaf VK. Old proofs can
verify under an old VK while no longer representing the current circuit; a
stale or mismatched zkey therefore fails before any recursive setup starts.
To perform just this inexpensive compatibility gate without starting the
recursive pipeline, append `--validate-only` to the fixture path.
It then reruns the read-only `pcd3 --stage=plan`, derives the
synthetic member root/policy separately, then invokes `pcd3 --stage=run` with
the same artifact directory. Matching setup stages and the BridgeBWV2 x3,
NodeBLSV2, PromoteBLSV2, NodeBWV2, and FinalBNV2 proofs are reused only after
source/constraint/VK/assignment hashes match and each proof verifies against
its cached public witness. Cache files contain the proof and public witness,
not the full/private assignment, and are written owner-only under
`proof-cache-v1/`; these generated directories are gitignored. The final JSON
and SHA-256 file are assembled in a private sibling directory and published
together by rename. Its directory name is an opaque hash over the statement,
verifier, and proof rather than a raw RID/time value. Re-running accepts an
existing output only when its exact file set and bytes match; partial or
altered output is preserved and rejected.
An interruption before a setup/proof cache is atomically published requires
that work to be recomputed; incomplete/mismatched cache directories remain
fail-closed and are neither deleted nor overwritten by the resume script. The
pipeline is still research-only.

The current V2 public schema is:

| Index | Signal |
| ---: | --- |
| 0 | `observation_eligible` |
| 1 | `drone_id_commitment` |
| 2–3 | observer public key X/Y |
| 4 | `time_bucket` |
| 5 | `consistency_ok` |
| 6 | `freshness_pub` |
| 7 | `calibration_profile_id_pub` |

Previously generated V2 keys and proofs are incompatible unless they were
generated from the exact current BLE/RSSI-only relation and its signed-message
semantics. This includes artifacts from the earlier run-scoped 8-output and
19-output experiments; no V2 release key is pinned.

The slower opt-in solve gate uses an actual generated Circom proof and its VK in
the BW6 circuit, checks a valid `BridgeBWV2Assignment`, and rejects a flipped
Merkle path bit:

```sh
RUN_BRIDGE_BW6_SOLVE=1 bash scripts/test_v2_observer_batch.sh
```

This gate passed on 2026-10-04 for the current BLE/RSSI-only relation using
freshly generated leaf proofs. `TestV2ObserverBatchProofIntegration` solved an
actual eligible far-mismatch/profile-2 leaf assignment in BridgeBWV2 and
rejected changed member and profile Merkle paths. The gate evaluates the
circuit relation with gnark's test engine; it does not run outer BW6
Groth16 setup/proving or replace independent verifier verification.

The outer Groth16 proof gate compiles the actual-key BW6 circuit, runs
`groth16.Setup`, proves the same actual leaf/path assignment, then verifies the
resulting 9-public-input proof:

```sh
RUN_BRIDGE_BW6_PROVE=1 \
UAV_V2_BATCH_GO_TEST_TIMEOUT=30m \
GOMAXPROCS=8 \
bash scripts/test_v2_observer_batch.sh
```

On 2026-10-04, earlier attempts on the 19-signal bridge reached BW6
`groth16.Setup` but did not produce an outer proof. One timed out during
`BatchScalarMultiplicationG1`; another was manually interrupted after about 22
minutes when system swap approached 12 GB. After reducing that circuit to
3,079,825 constraints, a third attempt was interrupted after about 12 minutes
with swap at 7.7/8.2 GB. The current 8-signal circuit is smaller at 2,092,014
constraints, but its outer setup/proving has not yet been attempted. No outer
proof has been produced. Actual-key compilation and inner test-engine solve are
verified, but outer Groth16 setup/proving feasibility remains unresolved on
this machine. The disposable single-contributor setup remains test-only.

After the host assignment/path tests pass, an opt-in compile checks the full
BW6 bridge constraint system with a dummy leaf key that has the same 8-public-
signal shape. The actual Circom V2 VK/proof shape is separately exercised by
the integration test. This compile does not perform an outer setup or proof:

```sh
RUN_BRIDGE_BW6_COMPILE=1 bash scripts/test_v2_observer_batch.sh
```

This compile is resource-intensive. On 2026-10-04, the 8-signal bridge
compiled with 2,092,014 constraints and 9 public inputs. The earlier 19-signal
version had 3,079,825 constraints, so narrowing public outputs removed 987,811
constraints (about 32.1%). Current-schema actual-proof solving and Merkle-path
tamper rejection also passed. Outer Groth16 setup/proving remains a separate
gate.

## Remaining proof integration

`BridgeBW` and `FinalBN` remain V1-only. V2 uses separate bridge/finalizer
circuits, while recursive merge constructors pin either version at compile
time. Keep each version's proving and verification keys separate. The next
gates are to compile/setup/prove each recursive stage, verify cross-version and
tamper rejection with actual proofs, then run the 10-input final proof through
a V2 EVM registry that approves immutable policy commitments and rejects both
duplicate sessions and reused proofs. None of those end-to-end gates has passed
yet. The V2 CLI currently supports a three-observer topology and a deterministic
allowlist of up to 16 calibration profile IDs.

The current commands are:

```sh
cd aggregator
go run ./cmd/pcd3 --protocol=v2 --stage=plan \
  --leaf-vk /path/to/release-pinned-v2-verification-key.json \
  --proof-dir /path/to/three-v2-proof-files \
  --roster pcd/testdata/observer-roster-v1.json \
  --active-member-root /decimal-root-read-from-registry \
  --calibration-profile-ids 1,2 --quorum 2
```

Add `--active-member-root` with a decimal value obtained independently from
the authoritative observer registry. The checked-in manifest is synthetic;
offline fixture runs may instead opt into `--allow-manifest-root-for-test`.
That option is not evidence of registry authentication. `pcd3` recomputes the
root from the roster and rejects duplicate keys or any root mismatch.

The `--stage=run` variant additionally performs all recursive Groth16 setups
and proofs for the supplied observations, writes a V2 verifier and
`final-proof-v2.json`, and is intentionally not run in ordinary tests because
the outer setup is resource intensive. The disposable script supplies the
one-consistent/two-suspicious set to target a `VerdictSpoofSuspected` result.
Once
an actual artifact exists, the local EVM command is:

```sh
# Resolve these independently: read registry values and approved verifier hash
# from the appropriate registry/release manifest before invoking the runner.
cd contracts
PCD3_V2_FINAL_ARTIFACT=/absolute/path/final-proof-v2.json \
PCD3_V2_ACTIVE_MEMBER_ROOT="$ACTIVE_MEMBER_ROOT" \
PCD3_V2_APPROVED_POLICY_COMMITMENT="$APPROVED_POLICY_COMMITMENT" \
PCD3_V2_APPROVED_MINIMUM_QUORUM=2 \
PCD3_V2_EXPECTED_VERIFIER_SHA256="$EXPECTED_VERIFIER_SHA256" \
  npx hardhat run scripts/verify_pcd3_final_v2_evm.js --network hardhat
```

The EVM harness requires expected root, policy, minimum quorum, and verifier
source hash independently of the proof artifact. It checks the public root and
policy, requires the artifact quorum and embedded source hash to match the
independent values, and hashes the source bytes before compiling/deploying the
verifier. Obtain the verifier hash from the reviewed release/VK manifest, not
from the proof artifact itself. The disposable synthetic test derives these
expectations from its fixture roster, selected plan, and FinalBNV2 stage source
that `pcd3` exported and checked against its VK; it tests binding but does not
authenticate a production registry, ceremony, or governance process.

The V2 registry uses the public order below and keys session finalization by
protocol version + drone commitment + time bucket, independent of policy
revision. This prevents an already-finalized drone/time session from being
submitted again under a newly approved calibration policy. It separately
rejects reuse of identical proof bytes. The current Hardhat tests exercise
those registry gates with a mock verifier; they do not replace execution of
the generated FinalBNV2 verifier against a real recursive proof.

| Index | FinalBNV2 public input |
| ---: | --- |
| 0 | protocol version (`2`) |
| 1–3 | drone commitment, time bucket, policy commitment |
| 4 | approved calibration profile-set root (canonical BN254 scalar) |
| 5–6 | active member root, merged nullifier root |
| 7–9 | consistent count, suspicious count, verdict |

The October-November goal checkpoints are:

| Due | Evidence required |
| --- | --- |
| Oct 11 | Review RID trust-root choice, observer enrollment, session/replay model, privacy boundary, and V2 public ABI. |
| Oct 25 | Actual recursive V2 proofs across Bridge → NodeBLS/Promote → NodeBW → FinalBNV2; adversarial version/session/duplicate rejection. |
| Nov 8 | Independent-device capture sessions with a held-out RSSI evaluation and false-positive/false-negative report. |
| Nov 22 | Generated V2 verifier and registry tests on a local EVM, including policy approval and replay rejection. |
| Nov 30 | Reproducible commands, pinned test materials, results, and explicit limitations reviewed and documented. |

Real field measurements, an external RID trust-root binding, and a reviewed
release ceremony remain outstanding. A synthetic proof or a test-only setup
does not satisfy those requirements.

## 2026-10-05 current-relation rerun and pinned integration toolchain

The proof-backed command was rerun after the gnark update with:

```sh
TMPDIR=/tmp GOTMPDIR=/tmp GOMAXPROCS=1 \
UAV_V2_BATCH_GO_TEST_TIMEOUT=10m bash scripts/test_v2_observer_batch.sh
```

It passed with Circom 2.2.3, snarkjs 0.7.6, circomlib 2.0.5,
circomlibjs 0.1.7, and Go 1.26.5 (module minimum: Go 1.25.7). The script
now checks the external compiler/prover and installed Circom libraries before
building; version drift fails closed with a message instead of silently
changing the tested relation. npm dependencies still come from the checked-in
lockfiles (`npm ci` in the repository root and `contracts/`).

Current result: the 6,201-constraint / 8-output leaf circuit compiled; a fresh
disposable setup produced multiple proofs; the generated local EVM leaf
verifier accepted a valid proof and rejected edits to RID commitment, time
bucket, consistency, freshness, and profile. The proof-backed Go batch test
passed for three distinct synthetic registered observers, and `pcd3
--protocol=v2 --stage=plan` independently revalidated the proofs and derived
one consistent + two suspicious observations with
`POSITION_INCONSISTENCY_SUSPECTED`.

This rerun did not enable `RUN_PCD3_V2` or `RUN_BRIDGE_BW6_SOLVE`: there is no
current Bridge outer proof, recursive FinalBNV2 proof, or artifact-backed
FinalBNV2 EVM result from it. Setup keys and fixtures were disposable and
removed by the script. The test remains synthetic and is not field RSSI or
Remote ID/DRIP authentication evidence.

## 2026-10-05 resumed recursive setup resource stop

The retained current-relation fixture passed the documented
`scripts/resume_v2_observer_batch.sh <fixture> --validate-only` gate:
`snarkjs zkey verify` reported `ZKey Ok!`, and the saved verification key
exactly matched the key exported from the current 6,201-constraint Circom
relation. The resumed `--stage=plan` reverified all three synthetic leaf
proofs and derived one consistent plus two suspicious observers
(`POSITION_INCONSISTENCY_SUSPECTED`).

The full resume was then started with `PCD3_GOMAXPROCS=1`. `BridgeBWV2`
compiled to 2,520,507 constraints and entered local Groth16 setup. After about
8 minutes, the setup was interrupted with SIGINT to protect the host: swap
grew from about 2.31 GiB used to 3.94 GiB used (the system expanded its swap
file to 5 GiB), while internal-volume free space fell from 3.9 GiB to 1.6 GiB. No
stage manifest/key or proof was published; the `pcd3-artifacts` directory is
empty, and the retained leaf fixture is intact. No Bridge proof, recursive
Node/FinalBNV2 proof, or generated-verifier EVM result was produced. This is a
resource-limited setup attempt, not a circuit correctness failure. Do not
retry on the same host until adequate memory and internal swap headroom are
available; use the preserved synthetic leaf fixture with the resume gate.

## 2026-10-05 capture-event identity check and cross-runtime rerun

The offline capture adapter previously selected an event when any record had
the target run-scoped UAS tag, then included every Location record with that
`capture_event_seq`. It did not reject a second, different non-null UAS tag in
the same callback. `parseCaptureBytes` now requires every present UAS tag to be
a 24-character lowercase hexadecimal pseudonym and rejects an event containing
more than one distinct tag. A regression test mutates only the Location row's
tag and confirms witness creation fails closed.

Verification: `node --test scripts/capture_to_witness_v2.test.js` passed 14/14;
`TMPDIR=/tmp node --test --test-concurrency=1
scripts/test_cross_platform_capture_interop.test.js` passed 1/1. The latter
generated and verified three disposable current-V2 leaf proofs from synthetic
Flutter + two Pi-format captures, checked the three-observer preflight, and
ran its duplicate/tamper/mixed-session rejections. It is not physical BLE/GPS
evidence or operational enrollment.

The disposable leaf ceremony now uses Powers-of-Tau power 13 instead of 14:
the current R1CS has 6,201 constraints, which fits within 2^13 = 8,192. Both
the cross-runtime integration test and batch script parse Circom's linear and
non-linear constraint counts before starting the ceremony and fail closed if
the counts cannot be read or exceed capacity. The cross-runtime gate has
unit coverage for 6,201/8,193 constraints and malformed compiler output. This
avoids needless phase2 work while protecting future circuit changes. This
optimization does not affect recursive BW6 setup resource requirements.
