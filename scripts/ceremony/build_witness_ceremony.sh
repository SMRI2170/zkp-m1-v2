#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# セキュアなトラステッドセットアップ（Groth16 ceremony）で witness 回路をビルドする。
#
# 旧 build_witness_attestation_assets.sh は決定論的エントロピー(-e="...deterministic")
# を使っており、トラップドアがスクリプトから復元できる＝誰でも proof を偽造できた。
# 本スクリプトは:
#   - 各コントリビューションで OS 由来の真の乱数を使う（openssl rand）
#   - phase1 / phase2 とも複数コントリビューション + ランダムビーコンで確定
#   - snarkjs verify でセレモニーを監査
# により、少なくとも1人の貢献者が乱数を破棄すれば安全になる（1-of-N 信頼）。
#
# ※ 本番は各コントリビューションを「独立した参加者が別マシンで」実行すること
#   （README.md 参照）。本スクリプトは正しい手順の自動化とデモ再生成用。
# ─────────────────────────────────────────────────────────────────────────────

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CIRCUIT_STEM="uav_witness_attestation"
ASSET_PREFIX="distance30_witness_attestation"
POWER="${POWER:-15}"
NUM_CONTRIB="${NUM_CONTRIB:-3}"   # コントリビューション数（本番は独立参加者ごと）

CIRCUIT_PATH="$ROOT_DIR/circuits/${CIRCUIT_STEM}.circom"
BUILD_DIR="$ROOT_DIR/zk-distance/build/${CIRCUIT_STEM}"
APP_ASSET_DIR="$ROOT_DIR/rapidsnark_app/assets/circuits/uav_witness"
CONTRACTS_DIR="$ROOT_DIR/contracts/contracts"
FIXTURE_DIR="$ROOT_DIR/contracts/test/fixtures"
PROOF_DIR="$BUILD_DIR/proofs"
INPUT_DIR="$ROOT_DIR/zk-distance/samples/witness"
CEREMONY_DIR="$BUILD_DIR/ceremony"

mkdir -p "$BUILD_DIR" "$APP_ASSET_DIR" "$PROOF_DIR" "$CONTRACTS_DIR" "$CEREMONY_DIR" "$FIXTURE_DIR"

if ! ls "$INPUT_DIR"/input_dev*.json >/dev/null 2>&1; then
  echo "missing sample inputs. run: node scripts/gen_witness_sample.js" >&2
  exit 1
fi

rnd() { openssl rand -hex 64; }

echo "[1/8] Compile"
circom "$CIRCUIT_PATH" --O2 --r1cs --wasm --sym -l "$ROOT_DIR/node_modules" -o "$BUILD_DIR"

echo "[2/8] Phase 1 (Powers of Tau 2^${POWER}) — 乱数コントリビューション + ビーコン"
snarkjs powersoftau new bn128 "$POWER" "$CEREMONY_DIR/pot_0.ptau" -v
prev="$CEREMONY_DIR/pot_0.ptau"
for i in $(seq 1 "$NUM_CONTRIB"); do
  next="$CEREMONY_DIR/pot_${i}.ptau"
  snarkjs powersoftau contribute "$prev" "$next" --name="pot contrib $i" -e="$(rnd)"
  prev="$next"
done
BEACON_HASH="$(openssl rand -hex 32)"
snarkjs powersoftau beacon "$prev" "$CEREMONY_DIR/pot_beacon.ptau" "$BEACON_HASH" 10 -n="pot final beacon"
snarkjs powersoftau prepare phase2 "$CEREMONY_DIR/pot_beacon.ptau" "$CEREMONY_DIR/pot_final.ptau" -v
snarkjs powersoftau verify "$CEREMONY_DIR/pot_final.ptau"

echo "[3/8] Phase 2 (回路固有) — 乱数コントリビューション + ビーコン"
snarkjs groth16 setup \
  "$BUILD_DIR/${CIRCUIT_STEM}.r1cs" "$CEREMONY_DIR/pot_final.ptau" "$CEREMONY_DIR/z_0.zkey"
prev="$CEREMONY_DIR/z_0.zkey"
for i in $(seq 1 "$NUM_CONTRIB"); do
  next="$CEREMONY_DIR/z_${i}.zkey"
  snarkjs zkey contribute "$prev" "$next" --name="zkey contrib $i" -e="$(rnd)"
  prev="$next"
done
Z_BEACON="$(openssl rand -hex 32)"
snarkjs zkey beacon "$prev" "$BUILD_DIR/${ASSET_PREFIX}.zkey" "$Z_BEACON" 10 -n="zkey final beacon"

echo "[4/8] セレモニー監査 (verify)"
snarkjs zkey verify \
  "$BUILD_DIR/${CIRCUIT_STEM}.r1cs" "$CEREMONY_DIR/pot_final.ptau" "$BUILD_DIR/${ASSET_PREFIX}.zkey"

echo "[5/8] Export vkey + Solidity verifier"
snarkjs zkey export verificationkey \
  "$BUILD_DIR/${ASSET_PREFIX}.zkey" "$BUILD_DIR/${ASSET_PREFIX}_vkey.json"
snarkjs zkey export solidityverifier \
  "$BUILD_DIR/${ASSET_PREFIX}.zkey" "$CONTRACTS_DIR/Groth16Verifier.sol"

echo "[6/8] 各端末の proof 生成・検証"
for f in "$INPUT_DIR"/input_dev*.json; do
  name="$(basename "$f" .json)"
  node "$BUILD_DIR/${CIRCUIT_STEM}_js/generate_witness.js" \
    "$BUILD_DIR/${CIRCUIT_STEM}_js/${CIRCUIT_STEM}.wasm" "$f" "$BUILD_DIR/${name}.wtns"
  snarkjs groth16 prove \
    "$BUILD_DIR/${ASSET_PREFIX}.zkey" "$BUILD_DIR/${name}.wtns" \
    "$PROOF_DIR/${name}_proof.json" "$PROOF_DIR/${name}_public.json"
  snarkjs groth16 verify \
    "$BUILD_DIR/${ASSET_PREFIX}_vkey.json" \
    "$PROOF_DIR/${name}_public.json" "$PROOF_DIR/${name}_proof.json"
done

echo "[7/8] フィクスチャ・アプリアセットを更新"
cp "$PROOF_DIR"/input_dev*_proof.json "$PROOF_DIR"/input_dev*_public.json "$FIXTURE_DIR/"
cp "$BUILD_DIR/${ASSET_PREFIX}.zkey" "$APP_ASSET_DIR/${ASSET_PREFIX}_groth16.zkey"
cp "$BUILD_DIR/${ASSET_PREFIX}_vkey.json" "$APP_ASSET_DIR/${ASSET_PREFIX}_verification_key.json"

echo "[8/8] 完了"
echo "  セレモニー成果物: $CEREMONY_DIR （中間ファイルは監査後に破棄可）"
echo "  ${NUM_CONTRIB} コントリビューション + ビーコンで確定。verify 済。"
echo "  ※ 本番は各コントリビューションを独立参加者が別マシンで実行すること。"

# Releaseに添付するmanifest。最終回路のsource/r1cs/zkey/vkey/verifierの対応を
# SHA-256で固定し、第三者が差し替えを検出できるようにする。
"$ROOT_DIR/scripts/zk_artifact_manifest.sh" create "$BUILD_DIR/release-manifest.json" \
  "$CIRCUIT_PATH" \
  "$BUILD_DIR/${CIRCUIT_STEM}.r1cs" \
  "$BUILD_DIR/${ASSET_PREFIX}.zkey" \
  "$BUILD_DIR/${ASSET_PREFIX}_vkey.json" \
  "$CONTRACTS_DIR/Groth16Verifier.sol"
echo "  manifest: $BUILD_DIR/release-manifest.json"
