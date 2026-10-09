#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
VALIDATE_ONLY=0
if [[ $# -eq 2 && "$2" == "--validate-only" ]]; then
  VALIDATE_ONLY=1
elif [[ $# -ne 1 ]]; then
  printf 'usage: %s /absolute/path/uav-v2-observer-batch.XXXXXX [--validate-only]\n' "$0" >&2
  exit 2
fi
if [[ ! -d "$1" ]]; then
  printf 'fixture directory does not exist: %s\n' "$1" >&2
  exit 2
fi
TEST_DIR="$(cd "$1" && pwd -P)"
case "$TEST_DIR" in
  */uav-v2-observer-batch.*) ;;
  *)
    printf 'refusing a non-test fixture path: %s\n' "$TEST_DIR" >&2
    exit 2
    ;;
esac

required_files=(
  verification_key.json
  test-only.zkey
  pot-final.ptau
  base/dev0_public.json
  pcd3-inputs/input_dev0_proof.json
  pcd3-inputs/input_dev0_public.json
  pcd3-inputs/input_dev1_proof.json
  pcd3-inputs/input_dev1_public.json
  pcd3-inputs/input_dev2_proof.json
  pcd3-inputs/input_dev2_public.json
)
for relative_path in "${required_files[@]}"; do
  if [[ ! -f "$TEST_DIR/$relative_path" ]]; then
    printf 'fixture is incomplete; missing %s\n' "$TEST_DIR/$relative_path" >&2
    exit 2
  fi
done

# A proof can verify under an old VK even after the Circom relation changes.
# Before `pcd3 --stage=run`, compile the current source and require the saved
# disposable zkey to verify against that exact R1CS and Powers of Tau artifact.
CIRCUIT_CHECK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/pcd3-current-v2-circuit.XXXXXX")"
cleanup_circuit_check() {
  rm -rf "$CIRCUIT_CHECK_DIR"
}
trap cleanup_circuit_check EXIT
circom "$ROOT_DIR/circuits/uav_witness_attestation_v2.circom" \
  --O2 --r1cs -l "$ROOT_DIR/node_modules" -o "$CIRCUIT_CHECK_DIR"
CURRENT_R1CS="$CIRCUIT_CHECK_DIR/uav_witness_attestation_v2.r1cs"
snarkjs zkey verify "$CURRENT_R1CS" "$TEST_DIR/pot-final.ptau" "$TEST_DIR/test-only.zkey"
snarkjs zkey export verificationkey "$TEST_DIR/test-only.zkey" "$CIRCUIT_CHECK_DIR/verification_key.json"
node -e '
const assert = require("node:assert/strict");
const fs = require("node:fs");
const saved = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
const current = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
assert.deepStrictEqual(saved, current, "saved V2 leaf VK differs from the VK exported from the current-source zkey");
' "$TEST_DIR/verification_key.json" "$CIRCUIT_CHECK_DIR/verification_key.json"
if [[ "$VALIDATE_ONLY" == "1" ]]; then
  printf 'Fixture leaf VK matches the current V2 circuit and saved test-only zkey. No recursive setup/proof was started.\n'
  exit 0
fi
trap - EXIT
cleanup_circuit_check

cd "$ROOT_DIR/aggregator"
PCD3_INPUTS="$TEST_DIR/pcd3-inputs"
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

PCD3_V2_EVM_INITIAL_DATE="$(node -e '
const fs = require("node:fs");
const publicSignals = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
if (!Array.isArray(publicSignals) || publicSignals.length !== 8 || !/^(0|[1-9][0-9]*)$/.test(publicSignals[4])) {
  throw new Error("saved V2 leaf public signals are malformed");
}
const bucketStartMs = (BigInt(publicSignals[4]) * 60n + 30n) * 1000n;
if (bucketStartMs > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error("time bucket exceeds JavaScript date range");
process.stdout.write(new Date(Number(bucketStartMs)).toISOString());
' "$TEST_DIR/base/dev0_public.json")"

printf 'Resuming the V2 recursive pipeline using matching setup manifests and verified proof caches under %s\n' "$TEST_DIR/pcd3-artifacts"
GOMAXPROCS="${PCD3_GOMAXPROCS:-1}" go run ./cmd/pcd3 --stage=run "${PCD3_ARGS[@]}"

shopt -s nullglob
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

printf 'Fixtures and proof artifacts remain available at %s\n' "$TEST_DIR"
