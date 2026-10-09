#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_DIR="$(mktemp -d)"
CIRCUIT_OUT="$TEST_DIR/circuit"
SAMPLE_OUT="$TEST_DIR/samples"
FAR_SAMPLE_OUT="$TEST_DIR/far-mismatch-samples"

mkdir -p "$CIRCUIT_OUT" "$SAMPLE_OUT" "$FAR_SAMPLE_OUT"
cd "$ROOT_DIR"

circom circuits/uav_witness_attestation_v2.circom \
  --O2 --r1cs --wasm -l node_modules -o "$CIRCUIT_OUT"
node scripts/gen_witness_sample_v2.js "$SAMPLE_OUT"
UAV_V2_SCENARIO=far-mismatch UAV_V2_DEVICE_INDEX=2 UAV_V2_PROFILE_ID=2 \
  node scripts/gen_witness_sample_v2.js "$FAR_SAMPLE_OUT"
node scripts/audit_leaf_signature_v2_binding.js \
  "$CIRCUIT_OUT/uav_witness_attestation_v2_js/uav_witness_attestation_v2.wasm" \
  "$SAMPLE_OUT/input_dev2.json" \
  "$FAR_SAMPLE_OUT/input_dev2.json"

echo "V2 constraint artifacts and samples remain in $TEST_DIR"
