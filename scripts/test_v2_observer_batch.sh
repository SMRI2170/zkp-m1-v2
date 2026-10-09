#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The opt-in recursive setup can take hours and produce large resumable
# artifacts. Never start it unless the caller explicitly preserves its work
# directory for audit/resume; otherwise the EXIT trap would delete it.
if [[ "${RUN_PCD3_V2:-0}" == "1" && "${UAV_V2_BATCH_KEEP_FIXTURES:-0}" != "1" ]]; then
  printf 'RUN_PCD3_V2=1 requires UAV_V2_BATCH_KEEP_FIXTURES=1 so setup/proof artifacts are preserved for audit or resume\n' >&2
  exit 2
fi

TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/uav-v2-observer-batch.XXXXXX")"
cleanup() {
  if [[ "${UAV_V2_BATCH_KEEP_FIXTURES:-0}" == "1" ]]; then
    printf 'keeping disposable V2 fixtures at %s\n' "$TEST_DIR" >&2
  else
    rm -rf "$TEST_DIR"
  fi
}
trap cleanup EXIT

CIRCUIT_OUT="$TEST_DIR/circuit"
BASE_INPUTS="$TEST_DIR/base-inputs"
PROFILE_INPUTS="$TEST_DIR/profile2-inputs"
OTHER_RUN_INPUTS="$TEST_DIR/other-run-same-bucket-inputs"
SESSION_INPUTS="$TEST_DIR/other-session-inputs"
FAR_MISMATCH_INPUTS="$TEST_DIR/far-mismatch-inputs"
mkdir -p "$CIRCUIT_OUT" "$BASE_INPUTS" "$PROFILE_INPUTS" "$OTHER_RUN_INPUTS" "$SESSION_INPUTS" "$FAR_MISMATCH_INPUTS" \
  "$TEST_DIR/base" "$TEST_DIR/profile2" "$TEST_DIR/other-run-same-bucket" "$TEST_DIR/other-session" "$TEST_DIR/far-mismatch"
cd "$ROOT_DIR"

# Go test/run binaries must be executable from the build temp directory. When
# fixture storage is redirected to an external volume (which may be noexec or
# lack native executable metadata), keep Go's transient build products local.
export GOTMPDIR="${GOTMPDIR:-/tmp}"

# The circuit compiler and proving CLI are external to package-lock.json. Fail
# closed on version drift so a different compiler/prover cannot silently
# produce a different relation or fixture under the same test command.
assert_cli_version() {
  local tool="$1"
  local expected="$2"
  local output actual
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf 'required tool is missing: %s\n' "$tool" >&2
    exit 1
  fi
  # snarkjs 0.7.6 prints its version banner but exits 99 for this flag.
  output="$("$tool" --version 2>&1)" || true
  actual="${output%%$'\n'*}"
  if [[ "$actual" != "$expected" ]]; then
    printf 'unsupported %s version: expected "%s", got "%s"\n' \
      "$tool" "$expected" "$actual" >&2
    exit 1
  fi
}

assert_cli_version circom 'circom compiler 2.2.3'
assert_cli_version snarkjs 'snarkjs@0.7.6'
node - "$ROOT_DIR" <<'NODE'
const fs = require("node:fs");
const path = require("node:path");
const root = process.argv[2];
const expected = { circomlib: "2.0.5", circomlibjs: "0.1.7" };
for (const [name, version] of Object.entries(expected)) {
  const packagePath = path.join(root, "node_modules", name, "package.json");
  let actual;
  try {
    actual = JSON.parse(fs.readFileSync(packagePath, "utf8")).version;
  } catch {
    process.stderr.write(`required locked npm package is unavailable: ${name}\n`);
    process.exit(1);
  }
  if (actual !== version) {
    process.stderr.write(`unsupported ${name} version: expected ${version}, got ${actual}\n`);
    process.exit(1);
  }
}
NODE
if [[ ! -x "$ROOT_DIR/contracts/node_modules/.bin/hardhat" ]]; then
  printf 'contract dependencies are missing; run npm ci in contracts/ first\n' >&2
  exit 1
fi
printf 'V2 integration toolchain: circom 2.2.3, snarkjs 0.7.6, circomlib 2.0.5, circomlibjs 0.1.7\n'
go version

# The checked-in synthetic captures are intentionally old fixtures. Shift all
# their event times together to the start of the current minute so the optional
# FinalAttestationRegistryV2 EVM run exercises its real freshness window. The
# fixture Remote ID value remains unauthenticated; V2 does not verify a RID
# trust chain.
BASE_TARGET_TIME_SEC="$(node -e 'const x=require(process.argv[1]); process.stdout.write(String(x.target_time_sec))' \
  "$ROOT_DIR/zk-distance/samples/witness/input_dev0.json")"
NOW_SEC="$(date +%s)"
CAPTURE_BUCKET_START_SEC=$((NOW_SEC / 60 * 60))
FRESHNESS_OFFSET_SEC=$((CAPTURE_BUCKET_START_SEC - BASE_TARGET_TIME_SEC))
PCD3_V2_EVM_INITIAL_DATE="$(node -e 'process.stdout.write(new Date(Number(process.argv[1]) * 1000 + 30_000).toISOString())' \
  "$CAPTURE_BUCKET_START_SEC")"

CIRCOM_OUTPUT="$(circom circuits/uav_witness_attestation_v2.circom \
  --O2 --r1cs --wasm -l node_modules -o "$CIRCUIT_OUT" 2>&1)"
printf '%s\n' "$CIRCOM_OUTPUT"
DISPOSABLE_PTAU_POWER=13
node - "$CIRCOM_OUTPUT" "$DISPOSABLE_PTAU_POWER" <<'NODE'
const output = process.argv[2];
const power = Number(process.argv[3]);
const nonlinear = output.match(/^non-linear constraints: ([0-9]+)\s*$/m);
const linear = output.match(/^linear constraints: ([0-9]+)\s*$/m);
if (!nonlinear || !linear) {
  process.stderr.write("could not read linear/non-linear constraint counts from Circom output; refusing disposable ceremony\n");
  process.exit(2);
}
const constraints = Number(nonlinear[1]) + Number(linear[1]);
const capacity = 2 ** power;
if (!Number.isSafeInteger(constraints) || constraints <= 0 || constraints > capacity) {
  process.stderr.write(`current V2 R1CS has ${constraints} constraints; power ${power} supports ${capacity}; review required before starting disposable ceremony\n`);
  process.exit(2);
}
process.stdout.write(`Powers-of-Tau capacity preflight: ${constraints} constraints fit within 2^${power} = ${capacity}\n`);
NODE
UAV_V2_RUN_ID=field-run-01 UAV_V2_TIME_OFFSET_SEC="$FRESHNESS_OFFSET_SEC" \
  node scripts/gen_witness_sample_v2.js "$BASE_INPUTS"
UAV_V2_RUN_ID=field-run-01 UAV_V2_DEVICE_INDEX=2 UAV_V2_PROFILE_ID=2 \
  UAV_V2_TIME_OFFSET_SEC="$FRESHNESS_OFFSET_SEC" \
  node scripts/gen_witness_sample_v2.js "$PROFILE_INPUTS"
UAV_V2_RUN_ID=field-run-02 UAV_V2_DEVICE_INDEX=2 UAV_V2_TIME_OFFSET_SEC="$FRESHNESS_OFFSET_SEC" \
  node scripts/gen_witness_sample_v2.js "$OTHER_RUN_INPUTS"
UAV_V2_RUN_ID=field-run-02 UAV_V2_DEVICE_INDEX=2 \
  UAV_V2_TIME_OFFSET_SEC=$((FRESHNESS_OFFSET_SEC + 60)) \
  node scripts/gen_witness_sample_v2.js "$SESSION_INPUTS"
UAV_V2_RUN_ID=field-run-01 UAV_V2_SCENARIO=far-mismatch UAV_V2_DEVICE_INDEX=1 \
  UAV_V2_TIME_OFFSET_SEC="$FRESHNESS_OFFSET_SEC" \
  node scripts/gen_witness_sample_v2.js "$FAR_MISMATCH_INPUTS"
UAV_V2_RUN_ID=field-run-01 UAV_V2_SCENARIO=far-mismatch UAV_V2_DEVICE_INDEX=2 UAV_V2_PROFILE_ID=2 \
  UAV_V2_TIME_OFFSET_SEC="$FRESHNESS_OFFSET_SEC" \
  node scripts/gen_witness_sample_v2.js "$FAR_MISMATCH_INPUTS"

# This one-contributor setup is explicitly throwaway test material. It must
# never be used as a release ceremony or for a deployed/published VK.
# Constraint capacity was checked against Circom's compiled counts before setup.
snarkjs powersoftau new bn128 "$DISPOSABLE_PTAU_POWER" "$TEST_DIR/pot0.ptau"
snarkjs powersoftau contribute "$TEST_DIR/pot0.ptau" "$TEST_DIR/pot1.ptau" \
  --name="disposable V2 batch test only" -e="$(openssl rand -hex 64)"
snarkjs powersoftau prepare phase2 "$TEST_DIR/pot1.ptau" "$TEST_DIR/pot-final.ptau"
snarkjs groth16 setup "$CIRCUIT_OUT/uav_witness_attestation_v2.r1cs" \
  "$TEST_DIR/pot-final.ptau" "$TEST_DIR/test-only.zkey"
snarkjs zkey export verificationkey "$TEST_DIR/test-only.zkey" "$TEST_DIR/verification_key.json"
snarkjs zkey export solidityverifier "$TEST_DIR/test-only.zkey" "$TEST_DIR/GeneratedV2LeafVerifier.sol"

WASM_DIR="$CIRCUIT_OUT/uav_witness_attestation_v2_js"
prove_sample() {
  local label="$1"
  local index="$2"
  local input_path="$3"
  local output_dir="$TEST_DIR/$label"
  node "$WASM_DIR/generate_witness.js" \
    "$WASM_DIR/uav_witness_attestation_v2.wasm" "$input_path" \
    "$output_dir/dev${index}.wtns"
  snarkjs groth16 prove "$TEST_DIR/test-only.zkey" \
    "$output_dir/dev${index}.wtns" "$output_dir/dev${index}_proof.json" \
    "$output_dir/dev${index}_public.json"
}

for index in 0 1 2; do
  prove_sample base "$index" "$BASE_INPUTS/input_dev${index}.json"
done
prove_sample profile2 2 "$PROFILE_INPUTS/input_dev2.json"
prove_sample other-run-same-bucket 2 "$OTHER_RUN_INPUTS/input_dev2.json"
prove_sample other-session 2 "$SESSION_INPUTS/input_dev2.json"
prove_sample far-mismatch 1 "$FAR_MISMATCH_INPUTS/input_dev1.json"
prove_sample far-mismatch 2 "$FAR_MISMATCH_INPUTS/input_dev2.json"

cd "$ROOT_DIR/contracts"
LEAF_V2_VERIFIER_SOURCE="$TEST_DIR/GeneratedV2LeafVerifier.sol" \
LEAF_V2_PROOF="$TEST_DIR/base/dev0_proof.json" \
LEAF_V2_PUBLIC="$TEST_DIR/base/dev0_public.json" \
  ./node_modules/.bin/hardhat run --no-compile scripts/verify_v2_leaf_evm.js

cd "$ROOT_DIR/aggregator"
UAV_V2_BATCH_FIXTURE_DIR="$TEST_DIR" \
  go test -timeout "${UAV_V2_BATCH_GO_TEST_TIMEOUT:-10m}" \
    ./pcd -run '^TestV2ObserverBatchProofIntegration$' -count=1 -v

# Exercise the public pcd3 entrypoint against the exact current-relation leaf
# proofs generated above, not stale checked-in proofs or a host-only mock.
PCD3_INPUTS="$TEST_DIR/pcd3-inputs"
mkdir -p "$PCD3_INPUTS"
cp "$TEST_DIR/base/dev0_proof.json" "$PCD3_INPUTS/input_dev0_proof.json"
cp "$TEST_DIR/base/dev0_public.json" "$PCD3_INPUTS/input_dev0_public.json"
cp "$TEST_DIR/far-mismatch/dev1_proof.json" "$PCD3_INPUTS/input_dev1_proof.json"
cp "$TEST_DIR/far-mismatch/dev1_public.json" "$PCD3_INPUTS/input_dev1_public.json"
cp "$TEST_DIR/far-mismatch/dev2_proof.json" "$PCD3_INPUTS/input_dev2_proof.json"
cp "$TEST_DIR/far-mismatch/dev2_public.json" "$PCD3_INPUTS/input_dev2_public.json"
PCD3_MINIMUM_QUORUM=2
PCD3_ARGS=(
  --protocol=v2
  --leaf-vk "$TEST_DIR/verification_key.json"
  --proof-dir "$PCD3_INPUTS"
  --roster pcd/testdata/observer-roster-v1.json
  --allow-manifest-root-for-test
  --calibration-profile-ids 1,2
  --quorum "$PCD3_MINIMUM_QUORUM"
  --artifacts "$TEST_DIR/pcd3-artifacts"
)
pcd3_plan_output="$(go run ./cmd/pcd3 --stage=plan "${PCD3_ARGS[@]}")"
printf '%s\n' "$pcd3_plan_output"
pcd3_test_member_root="$(node -e 'const fs=require("node:fs");process.stdout.write(JSON.parse(fs.readFileSync(process.argv[1],"utf8")).memberRoot)' \
  "$ROOT_DIR/aggregator/pcd/testdata/observer-roster-v1.json")"
pcd3_test_policy_commitment="$(printf '%s\n' "$pcd3_plan_output" | awk -F 'policy commitment: ' '/^Approved calibration profile-set root:/ {print $2; exit}')"
if [[ -z "$pcd3_test_member_root" || -z "$pcd3_test_policy_commitment" ]]; then
  printf 'failed to derive the explicit synthetic registry root or approved policy commitment\n' >&2
  exit 1
fi

if [[ "${RUN_PCD3_V2:-0}" == "1" ]]; then
  GOMAXPROCS="${PCD3_GOMAXPROCS:-2}" go run ./cmd/pcd3 --stage=run "${PCD3_ARGS[@]}"
  final_artifacts=("$TEST_DIR"/pcd3-artifacts/proofs-v2/session-*/final-proof-v2.json)
  if [[ ${#final_artifacts[@]} -ne 1 || ! -f "${final_artifacts[0]}" ]]; then
    printf 'expected exactly one FinalBNV2 proof artifact, found %d\n' "${#final_artifacts[@]}" >&2
    exit 1
  fi
  final_verifier_source="$TEST_DIR/pcd3-artifacts/setup/final-bn-v2/FinalAttestationGroth16VerifierV2.sol"
  if [[ ! -f "$final_verifier_source" ]]; then
    printf 'expected the verifier exported and checked against the FinalBNV2 VK at %s\n' "$final_verifier_source" >&2
    exit 1
  fi
  final_verifier_sha256="$(node -e 'const c=require("node:crypto");const f=require("node:fs");process.stdout.write(c.createHash("sha256").update(f.readFileSync(process.argv[1])).digest("hex"))' "$final_verifier_source")"
  cd "$ROOT_DIR/contracts"
  PCD3_V2_FINAL_ARTIFACT="${final_artifacts[0]}" \
    PCD3_V2_ACTIVE_MEMBER_ROOT="$pcd3_test_member_root" \
    PCD3_V2_APPROVED_POLICY_COMMITMENT="$pcd3_test_policy_commitment" \
    PCD3_V2_APPROVED_MINIMUM_QUORUM="$PCD3_MINIMUM_QUORUM" \
    PCD3_V2_EXPECTED_VERIFIER_SHA256="$final_verifier_sha256" \
    PCD3_V2_EVM_INITIAL_DATE="$PCD3_V2_EVM_INITIAL_DATE" \
    ./node_modules/.bin/hardhat run scripts/verify_pcd3_final_v2_evm.js --network hardhat
fi
