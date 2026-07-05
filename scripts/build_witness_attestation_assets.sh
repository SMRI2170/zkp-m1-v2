#!/usr/bin/env bash
set -euo pipefail

# uav_witness_attestation.circom（マルチ端末 UAV 接近証明の端末回路）をビルドする。
# - Groth16 セットアップ（回路は約 1.2 万制約のため Powers of Tau は 2^14）
# - snarkjs で Solidity Groth16 検証器 contracts/contracts/Groth16Verifier.sol を生成
# - zk-distance/samples/witness/input_dev*.json 各端末の proof / public を生成・検証
# - rapidsnark_app 用の zkey / vkey を配置
#
# 事前に `node scripts/gen_witness_sample.js` で署名付き入力を生成しておくこと。

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CIRCUIT_STEM="uav_witness_attestation"
ASSET_PREFIX="distance30_witness_attestation"
POWER="${POWER:-14}"

CIRCUIT_PATH="$ROOT_DIR/circuits/${CIRCUIT_STEM}.circom"
BUILD_DIR="$ROOT_DIR/zk-distance/build/${CIRCUIT_STEM}"
APP_ASSET_DIR="$ROOT_DIR/rapidsnark_app/assets/circuits/uav_witness"
CONTRACTS_DIR="$ROOT_DIR/contracts/contracts"
PROOF_DIR="$BUILD_DIR/proofs"
INPUT_DIR="$ROOT_DIR/zk-distance/samples/witness"

mkdir -p "$BUILD_DIR" "$APP_ASSET_DIR" "$PROOF_DIR" "$CONTRACTS_DIR"

if ! ls "$INPUT_DIR"/input_dev*.json >/dev/null 2>&1; then
  echo "missing sample inputs. run: node scripts/gen_witness_sample.js" >&2
  exit 1
fi

echo "[1/9] Compiling ${CIRCUIT_STEM}"
circom "$CIRCUIT_PATH" --O2 --r1cs --wasm --sym -l "$ROOT_DIR/node_modules" -o "$BUILD_DIR"

echo "[2/9] Powers of Tau (2^${POWER})"
snarkjs powersoftau new bn128 "$POWER" "$BUILD_DIR/pot_0000.ptau" -v
snarkjs powersoftau contribute "$BUILD_DIR/pot_0000.ptau" "$BUILD_DIR/pot_0001.ptau" \
  --name="${ASSET_PREFIX} contribution" -e="${ASSET_PREFIX} deterministic contribution"
snarkjs powersoftau prepare phase2 "$BUILD_DIR/pot_0001.ptau" "$BUILD_DIR/pot_final.ptau"

echo "[3/9] Groth16 setup"
snarkjs groth16 setup \
  "$BUILD_DIR/${CIRCUIT_STEM}.r1cs" "$BUILD_DIR/pot_final.ptau" \
  "$BUILD_DIR/${ASSET_PREFIX}_0000.zkey"
snarkjs zkey contribute \
  "$BUILD_DIR/${ASSET_PREFIX}_0000.zkey" "$BUILD_DIR/${ASSET_PREFIX}.zkey" \
  --name="${ASSET_PREFIX} zkey contribution" -e="${ASSET_PREFIX} deterministic zkey contribution"

echo "[4/9] Export verification key"
snarkjs zkey export verificationkey \
  "$BUILD_DIR/${ASSET_PREFIX}.zkey" "$BUILD_DIR/${ASSET_PREFIX}_vkey.json"

echo "[5/9] Export Solidity Groth16 verifier -> contracts"
snarkjs zkey export solidityverifier \
  "$BUILD_DIR/${ASSET_PREFIX}.zkey" "$CONTRACTS_DIR/Groth16Verifier.sol"

echo "[6/9] Generate proof for each device input"
for f in "$INPUT_DIR"/input_dev*.json; do
  name="$(basename "$f" .json)"
  node "$BUILD_DIR/${CIRCUIT_STEM}_js/generate_witness.js" \
    "$BUILD_DIR/${CIRCUIT_STEM}_js/${CIRCUIT_STEM}.wasm" "$f" "$BUILD_DIR/${name}.wtns"
  snarkjs groth16 prove \
    "$BUILD_DIR/${ASSET_PREFIX}.zkey" "$BUILD_DIR/${name}.wtns" \
    "$PROOF_DIR/${name}_proof.json" "$PROOF_DIR/${name}_public.json"
done

echo "[7/9] Verify each proof"
for f in "$INPUT_DIR"/input_dev*.json; do
  name="$(basename "$f" .json)"
  snarkjs groth16 verify \
    "$BUILD_DIR/${ASSET_PREFIX}_vkey.json" \
    "$PROOF_DIR/${name}_public.json" "$PROOF_DIR/${name}_proof.json"
done

echo "[8/9] Copy artifacts for rapidsnark_app"
cp "$BUILD_DIR/${ASSET_PREFIX}.zkey" "$APP_ASSET_DIR/${ASSET_PREFIX}_groth16.zkey"
cp "$BUILD_DIR/${ASSET_PREFIX}_vkey.json" "$APP_ASSET_DIR/${ASSET_PREFIX}_verification_key.json"

echo "[9/9] Optional .wcd for on-device witness calc"
BUILD_CIRCUIT_BIN="${BUILD_CIRCUIT_BIN:-build-circuit}"
if command -v "$BUILD_CIRCUIT_BIN" >/dev/null 2>&1; then
  "$BUILD_CIRCUIT_BIN" "$CIRCUIT_PATH" "$APP_ASSET_DIR/${ASSET_PREFIX}.wcd"
else
  echo "  skip .wcd (build-circuit not installed)"
fi

echo "Done. Verifier: $CONTRACTS_DIR/Groth16Verifier.sol  Proofs: $PROOF_DIR"
