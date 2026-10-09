#!/usr/bin/env bash
# 現在ある「端末証明 → M1登録」「M2集約」「v1最終record」を、同じ順序で確認する入口。
#
#   ./scripts/run_e2e_demo.sh          # Hardhat の高速な統合スモークテスト
#   ./scripts/run_e2e_demo.sh --chain  # 上記に加え gnark Step A/B の3段再帰 PoC
#   PCD3_FINAL_ARTIFACT=/path/final-proof-v1.json ./scripts/run_e2e_demo.sh # 生成VKの実EVM検証も実行
#
# 注意: v1 registryは実装済みだが、実Groth16最終verifierは固定再帰PCD回路の生成後に
# 接続する。現時点のv1テストはABI/state-machineの検証である。
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
run_chain=false

if [[ "${1:-}" == "--chain" ]]; then
  run_chain=true
elif [[ $# -gt 0 ]]; then
  echo "usage: $0 [--chain]" >&2
  exit 2
fi

echo "== [1/5] M1: 3台の実 leaf proof → AttestationRegistry =="
(
  cd "$root_dir/contracts"
  npx hardhat test test/EndToEnd.test.js
)

echo
echo "== [2/5] M2: 3台分の集約 proof → AggregateVerifier =="
(
  cd "$root_dir/contracts"
  npx hardhat test test/AggregateVerify.test.js
)

echo
echo "== [3/5] M2 PoC final record: 集約結果 → FinalAttestationRegistry =="
(
  cd "$root_dir/contracts"
  npx hardhat test test/FinalAttestationRegistry.test.js
)

echo
echo "== [4/5] v1 final record: 9公開入力ABI → FinalAttestationRegistryV1 =="
(
  cd "$root_dir/contracts"
  npx hardhat test test/FinalAttestationProtocolV1.test.js test/FinalAttestationVerifierV1.test.js test/FinalAttestationRegistryV1.test.js test/GeneratedVerifierCompiler.test.js
)

echo
echo "== [5/5] PCD plan: 実Circom leaf proof → 固定observer roster → 3観測者batch =="
(
  cd "$root_dir/aggregator"
  go test ./pcd -run '^(TestPrepareObserverBatch|TestUnionNullifierLeaves)' -count=1
  go test ./cmd/pcd3
  go run ./cmd/pcd3 --stage=plan --allow-manifest-root-for-test
)

if [[ "$run_chain" == true ]]; then
  echo
  echo "== [optional] Step A/B: gnark の3段再帰チェーン =="
  (
    cd "$root_dir/aggregator"
    go run ./cmd/chainpoc
  )
fi

if [[ -n "${PCD3_FINAL_ARTIFACT:-}" ]]; then
  pcd3_final_artifact="$PCD3_FINAL_ARTIFACT"
  if [[ "$pcd3_final_artifact" != /* ]]; then
    pcd3_final_artifact="$root_dir/$pcd3_final_artifact"
  fi
  echo
  echo "== [optional] FinalBN artifact → generated Solidity verifier → FinalAttestationRegistryV1 =="
  (
    cd "$root_dir/contracts"
    PCD3_FINAL_ARTIFACT="$pcd3_final_artifact" npx hardhat run scripts/verify_pcd3_final_evm.js --network hardhat
  )
fi

echo
echo "OK: 既存M1/M2実proof、M2最終レコード、v1 ABI/state-machine、実leafから3観測者PCD planまでを個別に確認しました。"
if [[ -n "${PCD3_FINAL_ARTIFACT:-}" ]]; then
  echo "OK: 指定されたgenerated FinalBN proofを実verifierでEVM検証し、FinalAttestationRegistryV1へのrecordまで確認しました。"
else
  echo "注意: pcd3 --stage=plan は実leafとrosterを検証しますが、recursive proof生成とFinalBN→EVM v1 verifierは未接続です。"
  echo "      明示的な高負荷実験は cd aggregator && go run ./cmd/pcd3 --stage=run で開始します。"
  echo "      FinalBN proof artifactができた後は PCD3_FINAL_ARTIFACT=/path/final-proof-v1.json を指定すると、生成VKをローカルEVMで検査できます。"
fi
