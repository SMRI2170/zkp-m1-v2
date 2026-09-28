#!/usr/bin/env bash
# 現在ある「端末証明 → M1登録」「M2集約」「v1最終record」を、同じ順序で確認する入口。
#
#   ./scripts/run_e2e_demo.sh          # Hardhat の高速な統合スモークテスト
#   ./scripts/run_e2e_demo.sh --chain  # 上記に加え gnark Step A/B の3段再帰 PoC
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

echo "== [1/4] M1: 3台の実 leaf proof → AttestationRegistry =="
(
  cd "$root_dir/contracts"
  npx hardhat test test/EndToEnd.test.js
)

echo
echo "== [2/4] M2: 3台分の集約 proof → AggregateVerifier =="
(
  cd "$root_dir/contracts"
  npx hardhat test test/AggregateVerify.test.js
)

echo
echo "== [3/4] M2 PoC final record: 集約結果 → FinalAttestationRegistry =="
(
  cd "$root_dir/contracts"
  npx hardhat test test/FinalAttestationRegistry.test.js
)

echo
echo "== [4/4] v1 final record: 9公開入力ABI → FinalAttestationRegistryV1 =="
(
  cd "$root_dir/contracts"
  npx hardhat test test/FinalAttestationProtocolV1.test.js test/FinalAttestationVerifierV1.test.js test/FinalAttestationRegistryV1.test.js
)

if [[ "$run_chain" == true ]]; then
  echo
  echo "== [optional] Step A/B: gnark の3段再帰チェーン =="
  (
    cd "$root_dir/aggregator"
    go run ./cmd/chainpoc
  )
fi

echo
echo "OK: leaf 証明、集約 proof、M2最終レコード、v1 ABI/state-machineを確認しました。"
echo "注意: 実Groth16 v1 final verifierは固定再帰PCD回路から未生成です。"
