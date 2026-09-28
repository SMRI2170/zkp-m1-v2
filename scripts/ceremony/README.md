# トラステッドセットアップ・セレモニー（Groth16）

## なぜ必要か
Groth16 は回路ごとに **信頼できるセットアップ（zkey）** を必要とする。
セットアップ時の秘密乱数（トラップドア）を知る者は **任意の偽の proof を作れる**。

旧ビルド（`scripts/build_witness_attestation_assets.sh`）は決定論的エントロピー
（`-e="...deterministic..."`）を使っており、トラップドアがスクリプトから復元できた
＝**誰でも偽造できる**状態だった（デモ専用）。

## 本スクリプトの対策
`build_witness_ceremony.sh` は:
- 各コントリビューションで **OS 由来の真の乱数**（`openssl rand`）を使用
- **phase1 / phase2 とも複数コントリビューション + ランダムビーコン**で確定
- `snarkjs powersoftau verify` / `snarkjs zkey verify` で **セレモニーを監査**

→ **1-of-N 信頼**：少なくとも1人の貢献者が自分の乱数を破棄すれば、
残り全員が結託してもトラップドアは復元できない。

## デモ再生成（このリポジトリ）
```bash
node scripts/gen_witness_sample.js          # 署名付き入力
bash scripts/ceremony/build_witness_ceremony.sh
# → zkey / vkey / Groth16Verifier.sol / 各端末proof / フィクスチャ を再生成
```
`NUM_CONTRIB`（既定3）と `POWER`（既定15）で調整可能。

## 本番セレモニー（重要）
上記は「正しい手順」の自動化。**本番では各コントリビューションを独立した参加者が
別マシンで実行**し、自分の乱数を確実に破棄すること:

```bash
# 参加者 i は前の人の zkey を受け取り、自分の乱数で貢献して次へ渡す
snarkjs zkey contribute prev.zkey mine.zkey --name="participant-i" -v
#   → エントロピーを対話入力（またはハードウェア乱数）。入力後この端末から破棄。
```
- 最後に**公開ランダムネス**（例: 未来のブロックハッシュ）で `zkey beacon` を適用。
- 全 zkey を `snarkjs zkey verify` で公開監査。
- 参加者・寄与ハッシュ・ビーコン値を公開し、透明性を担保。

## Release manifest

ビルド完了時に `release-manifest.json` が生成される。回路source、R1CS、zkey、
verification key、Solidity verifierのSHA-256対応表である。公開時はこのファイルを
release assetとして添付し、受領側は次で差し替えを検出できる。

```bash
scripts/zk_artifact_manifest.sh verify \
  zk-distance/build/uav_witness_attestation/release-manifest.json
```

## 注意
- `zk-distance/build/**/ceremony/` の中間ファイルは監査後に破棄してよい（zkey は gitignore 済）。
- 参加者が全員結託し、かつ全員が乱数を保持した場合のみ安全性が崩れる（1-of-N 前提）。
