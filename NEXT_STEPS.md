# NEXT_STEPS — 研究進捗・次の作業

## 2026-10-11 研究方針を更新：Nova/SuperNova/HyperNovaの位置付けとWi-Fi Beacon実機観測

**[研究移行ADR（一次記録）](docs/research/2026-10-11_nova-to-remoteid-besu_adr.md)** を参照。2026年7月時点のNova実装成果は維持し、**2026年10月の研究上の次の問いは「独立した観測端末の秘密ZKPを、検証者/受付者を無条件に信用せず集計・監査できるか」**とする。

- **Nova**：端末内IVCの効率・実行を実測済み。一方、既存のSonobe走行`IVCProof`の跨端末受け渡しはWitness漏洩の懸念があり、登録・重複・共同受付/確定の仕組みは別途必要。
- **SuperNova**：非一様ステップのIVCに強いが、今回の独立観測者・受付合意の問題は自動的には解決しないのでMVPでは保留。
- **HyperNova**：CCS・複数インスタンスのFoldingでPCDなどの可能性があり、**数学的に不適合と断定しない**。Witnessを安全に保持する分散Proverプロトコル、提出順と重複の管理、最終証明とEVM検証の性能評価は別途必要。将来の集約方式比較として残す。
- **Besu/QBFT＋Solidity**：各端末の独立Groth16 proofをオンチェーン直接検証し、同じRemote ID session内の登録、重複、確定、監査履歴を扱う**参照アーキテクチャの候補**。Novaの計算圧縮機能を置き換えるものではない。
- **実験で得た情報**：研究室のDJIはBLEではなく**Wi-Fi BeaconのRemote IDを受信した**との報告。機体はMatrice 300 RTK/350 RTKのどちらか未確定（型番/FW/チャネル/生Beaconデータを確認）。Pi4×2・Pixel8全員の同時Beacon/RSSI受信は**未実証**。

**次の作業（優先順）**
1. [#13](https://github.com/SMRI2170/zkp-m1-v2/issues/13)・[#14](https://github.com/SMRI2170/zkp-m1-v2/issues/14)：Wi-Fi Beacon ODID IEとRSSI/時刻/受信チャネルをPixel8とPi4×2で採集可能か確認。対応受信機を確定。
2. [#17](https://github.com/SMRI2170/zkp-m1-v2/issues/17)・[#29](https://github.com/SMRI2170/zkp-m1-v2/issues/29)：申告位置とRTK/飛行ログの真値を分け、誤差付き判定と公開入力ABIを固定。
3. [#31](https://github.com/SMRI2170/zkp-m1-v2/issues/31)：保存済みWi-Fi Beacon実データのreplayから各端末独立Groth16を生成し、同一zkeyのSolidity verifierで検証。
4. [#30](https://github.com/SMRI2170/zkp-m1-v2/issues/30)・[#34](https://github.com/SMRI2170/zkp-m1-v2/issues/34)：Besu QBFT 4 Validatorの機能テストで証明を登録し、確定遅延・gas・エラーを記録。
5. [#35](https://github.com/SMRI2170/zkp-m1-v2/issues/35)・[#36](https://github.com/SMRI2170/zkp-m1-v2/issues/36)：速報とBC確定の遅延を分け、BCなし共同署名やMerkleログと公平比較する。

**注意**：Wi-Fi Beaconの電波観測自体も、BCやZKPも、センサー入力と物理位置の真実性を自動保証しない。過去のNova実験値は新しいフル回路/RapidSnark/複数端末/BCの実測値ではない。

---


## 2026-10-11 次フェーズ：Remote ID×Groth16×Besu/Solidity（進捗正本 #28）

> **前の研究フェーズ**：Nova/Sonobe調査・逐次IVC PoC、Pixel 8 3ステップ実機実証は完了（`week20/08`、`week20/09`）。ただし**別端末へ秘密Witnessを漏らさずNova内部状態を引き継ぐ実装は未完成**（`week20/12`、`week20/13`、`week21/01`）。下の従来Next Stepsは歴史的な研究メモで、新しい着手優先順位ではない。

**現在の実装Epic**：[#28 Remote ID×Groth16×Solidity×Besu/QBFT](https://github.com/SMRI2170/zkp-m1-v2/issues/28)

**NEXT ACTION**
- [ ] [#29](https://github.com/SMRI2170/zkp-m1-v2/issues/29) Remote ID sessionId／public signals ABI／結果の状態機械・攻撃モデルを確定してgolden vectorsを作る
- [ ] [#30](https://github.com/SMRI2170/zkp-m1-v2/issues/30) Besu QBFT（4 Validator+RPC）をローカル再現起動し、deploy/tx/finalityを確認
- [ ] [#31](https://github.com/SMRI2170/zkp-m1-v2/issues/31) Circom/Groth16 proofをSolidityで検証。RapidSnarkとのEVM互換性を別途実測（過去のPixel 8 Mopro/arkworks 402msと混同しない）
- [ ] [#32–#35](https://github.com/SMRI2170/zkp-m1-v2/issues/28) 端末認証・Registry・共同提出・BC確定と独立した速報
- [ ] [#36–#37](https://github.com/SMRI2170/zkp-m1-v2/issues/28) BCなし比較、攻撃・遅延実測、標準化向け仕様

**G1完了条件**：有効な秘密入力由来のGroth16 proofがBesu上のSolidity verifierで正しく検証され、改竄proofと公開入力すり替えが拒否される。テスト・commit・ガス・レイテンシを残す。

現行の進捗と受け入れ条件は[#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28)の「現在の進捗ダッシュボード」を正本とする。

---

## 旧フェーズの作業メモ（2026-07時点。現行の着手順ではない）

最終更新: 2026-07-26 / 前提を掴むには先に `CLAUDE.md` → `week20/04_再帰ZKP_証明チェーン設計.md` を読む。
**【2026-07-26追記】Noirも実機で完全動作を確認（詳細`week20/09` §5.2.2）。「残るのはNoir側の
最後の1シンボル解消のみ」だった課題を実際に解決したところ、連鎖的にさらに4つのシンボル問題
（うち4つはAztec公式Androidプリビルドバイナリ自体のglibc依存という上流側の問題と判明）が発覚、
全て解消して`noir_rssi_consistency`回路（chain-step版、gnark/Nova版と同一関係）が実機Pixel 8で
証明生成→検証まで完走した。10回実測: prove平均926ms（範囲731〜1071ms）・verify平均37ms
（範囲10〜56ms）、全て`Proof is valid: true`。**これで circom・Noir・Nova の3スタック全てが
実機で実回路の動作を確認済み**（gnarkのみ設計上モバイル除外のまま）。**
**Step A・Step B は実装・成功済み → 詳細は `week20/06_再帰チェーンPoC_StepAB実装結果.md`。**
**chainpocのスマホ実行可否の実測 → `week20/07_モバイル実行可否_gnarkチェーン回路の実測.md`
（結論: 現状回路はメモリ4GB級で今のスマホでは不可、ラズパイ/スマホの役割分担を実測で再確認）。**
**方式B（Nova/Sonobe）も実装・成功済み → 詳細は `week20/08_Nova方式B_PoC実装結果.md`
（結論: 方式Aよりメモリ約9分の1・1ステップ約30〜50倍高速。スマホ実行の見込みは方式Bの方が高い）。**
**circom/Noir/Novaのスマホ実行設計・実装・性能評価 → `week20/09_モバイル実行_circom_Noir_Nova_設計.md`
（**circom・NovaともPixel8実機で実案件回路により実際に動作(証明生成→検証)まで確認済み**。
circomは`remoteid_consistency_rel.circom`（649制約）をFlutterアプリに組み込み、実機で
整合/なりすまし双方のケースを実測（証明402ms・検証166ms、snarkjsデスクトップ実行と出力値が
完全一致）。**Novaはネイティブ Android(Kotlin)アプリ`nova_poc/nova-android-demo/`まで組み上げ、
実機で画面をタップして3ステップの証明生成→検証が完走することを確認**（1ステップ0.5〜1.2秒、
gnark方式Aの7〜9秒より桁で高速）。Noirはランタイムlibc++ ABI不一致の根本原因(動的リンク指定)を
特定し静的リンクへ変更、症状を大幅縮小（残1シンボルのみ・`week20/09` §5.2.1、実機ではまだ起動
しないが、デスクトップでは`noir_rssi_consistency`回路が118 ACIR opcodes・証明93ms・検証12msで
動作確認済み）。**circom/Noir/Nova/gnark 4スタックの統一性能比較を`week20/09` §5.5に整理**
（結論: gnarkはモバイルから実質除外、Novaが実機実用速度でチェーン一貫性も保証できる唯一の
選択肢、circomはチェーンを強制しない単発証明として最速。詳細は同節）。
残るのはNoir側の最後の1シンボル解消のみ）。**
**エラー洗い出し＋Cairo設計 → `week20/10_Cairo実装設計_ファイル構成と回路記述.md`
（既存3スタックの実装エラー3件を発見・修正: circomクレートの旧multiplier2スキャフォールドテスト
削除、Flutter統合テストのimport不整合修正、main.dartのHalo2/Noir/Gnark未実装タブに説明コメント追加。
加えて4本目の候補としてCairo/StarkのRSSI整合回路の実装方法・ファイル構成・回路記述を設計。
結論: Moproに公式Cairoアダプタが無く自作要、オンチェーン資産もゼロからのため優先度は低いが、
STARK再帰を活かした「方式C」の可能性は今後の検討材料として残した）。**

---

## 0. いまの一文サマリ

設計は「**再帰チェーン(IVC)・方式A＝gnark 再帰**」で確定済み。**Step A（前の証明を回路内で検証して
内包する"逐次チェーン"を2〜3ステップ動かすPoC）と Step B（RSSI整合を step 回路内で計算する）は
実装・成功済み**（`aggregator/cmd/chainpoc/`、詳細 `week20/06`）。**次は Step C（membership＋二重計上防止）。**

---

## 1. 直近ゴール：再帰チェーン PoC Step A/B ✅ 完了（結果は `week20/06`）

**「ノードi が、前のノードの証明 π_{i-1} を自分の回路内で再帰検証し（＝内包）、
自分の観測を足した新しい証明 π_i を作る」を 2〜3 ステップ連結して動かす。**

### 回路内で強制すること
1. **前の証明 π_{i-1} を再帰検証**（gnark `std/recursion/groth16`）＝前を内包
2. `drone_id_commitment` と `time_bucket` が前の累積 z_{i-1} と一致（同一ドローン・同一時間窓）
3. `consistent_count += ok` / `suspicious_count += (1-ok)`（**ok はStep Bで回路内計算に変更済み**）
4. 更新した累積 z_i を public 出力にして π_i を生成

### 成功条件
- 正常系: 3 ステップ連結して最終 π_3 が生成・検証でき、`consistent_count` が正しく育つ。
- 否定系: drone_id/time_bucket を食い違わせる or 偽の π_{i-1} を渡すと**π_i が生成できない**ことを確認。
- 各中間 π_k が**単体で検証できる**こと（方式Aの肝＝「取ってきて検証」）。
- （Step B追加）実際は矛盾したRSSI観測を「整合した」と偽って計上しようとしても拒否されること。

### 結果（2026-07-23・M2 Mac）
**すべて達成**。`aggregator/cmd/chainpoc/main.go` に実装。π_1→π_2→π_3 が連結でき、
Step B適用後は `consistent_count` 1→2→2 / `suspicious_count` 0→0→1（3番目をわざと「なりすまし観測」
にして正しく検知させた）。各 π_k は単体検証OK、否定系3件とも期待通り拒否（詳細ログ・実行時間・
発見した技術的落とし穴は `week20/06_再帰チェーンPoC_StepAB実装結果.md` を参照）。
特筆点1: 自己再帰は「前の証明を受け取る箱のサイズが検証対象の回路構造に依存する」ため、
GenesisとChainCircuitで箱を作り分ける必要があった（3ステップはこれで解決。N段への一般化＝
「箱の不動点」への収束確認は未着手・`week20/06` §1.3）。
特筆点2（Step B）: `circuits/remoteid_consistency_rel.circom` と同じ相対許容帯判定を
`gnark std/math/cmp` で移植し、`ok` を外部入力から回路内計算に変更。「なりすまし観測なのに
consistentと偽る」否定系が拒否されることを確認（＝参加者はRSSI整合の判定結果を偽れない）。

---

## 2. 流用する既存資産（ゼロから作らない）

- `aggregator/cmd/chainpoc/` … **Step A/B の実装（本PoC）**。Genesis/ChainCircuit・recompose・
  段ごとの回路立て直しパターン・`rssiConsistencyOk`は Step C でもそのまま拡張して使う土台。
- `aggregator/main.go` … **Spike A（snarkjs Groth16 を gnark-crypto で検証する interop）**。点の座標変換は解決済み。
  ※実行には `zk-distance/build/`（circom/snarkjs で要再生成、M2に未インストール）が必要。
- `aggregator/snarkimport/` … snarkjs の vkey/proof/public を gnark 表現へ変換。実circom観測を
  chainpocのgenesisステップに繋ぐ際（circom leafとの接続）に使う見込み。
- `aggregator/cmd/aggregate/`, `cmd/verify1/` … 集約・単一検証のエントリ（木構造・M2）。
- `aggregator/membership/`, `completeness/` … Sybil・検閲検知（Step C で接続）。
- `circuits/uav_witness_attestation.circom` の public 信号（idx6/10/11/12/13/14）= 累積が参照する値。
- `circuits/remoteid_consistency_rel.circom`, `circuits/lib_uav_safety.circom` … Step BでgnarkへポートしたRSSI整合判定の元ロジック。

---

## 3. その後の段階（Step C→D）

| Step | 内容 | 状態 |
|---|---|---|
| **A** | gnark で 2〜3 ステップの逐次再帰検証（前を内包）＝上記 | ✅ 完了（`week20/06`） |
| **B** | **RSSI 整合**を step 回路に折り込む（`remoteid_consistency_rel` 相当を回路内で計算し ok を出す） | ✅ 完了（`week20/06`） |
| **C** | **membership（登録端末のMerkle）＋二重計上防止**（included_acc に未包含のときだけ畳む）を追加 | ⬜ 次 |
| **D** | **最終圧縮 → EVM verifier 出力** → Hardhat で1回検証し trusted/spoof 記録・gas 定数を確認 | ⬜ |

---

## 4. 設計上まだ埋めるべき穴（week20/04 §14 より・実装時に効く）

実装で必ず考慮する 3 点（目的①複数ノードでRSSI検証／②危険か否かを内包して証明 のため）:
- **(a) 危険判定を回路内で計算し `is_spoof` を証明の公開出力に**（②の核）。判定規則を一意に
  （例: `suspicious ≥ K → 危険` / `consistent ≥ K → 安全` / それ以外 `undetermined`）。
- **(b) 各ステップに入力真正性(R3)**: ドローン署名検証・freshness・観測と放送の束縛（①の核。無いと捏造で"整合"を作れる）。
- **(c) GPS真正性＋RSSI較正**を設計に明示・証明にバインド（多ノード検証が意味を持つ前提）。

---

## 5. 方式B（Nova/Sonobe）✅ PoC実装・実測比較済み（結果は `week20/08`）

`week20/04`では「省メモリ代替・今は選ばない」としていたが、`week20/07`でgnark(方式A)のスマホ実行が
非現実的と判明したため、比較のため実装・実測した。

- **結果**: 方式Aよりピークメモリ約9分の1（4.04GB→456MB）、1ステップの証明生成が約30〜50倍高速
  （7〜9秒→130〜280ミリ秒）。同じ3ステップ・同じ検知結果（consistent 1→2→2, suspicious 0→0→1）を再現。
- **トレードオフは`week20/04`記載の通り健在**: 中間が単体検証不可（IVC証明は最後にまとめて検証。
  「取ってきて検証」には方式Aの方が忠実）。EVM着地には最終圧縮(wrap)が別途必要（Sonobeの
  `solidity-verifiers`が対応、Step D相当は未着手）。
- **実装で新たに分かったこと**: (1) Novaは自己再帰の「箱サイズ問題」（`week20/06`§1.2）が原理的に
  存在しない＝同じ回路をそのまま使い回せる、(2) z_iの継続性はIVCエンジン自身が保証するため
  方式Aのような「前の主張との一致assert」が不要、(3) 依存関係(Rust/arkworks)がちょうど0.5→0.6の
  破壊的移行期にあり、環境構築だけで16回のビルド試行を要した（詳細`week20/08`§2-4、教訓含む）。
- **次の一手**: スマホ実機でのRustクロスコンパイル・実測（今回はM2 Mac実行のみ）、Step D相当の
  最終圧縮→EVM verifier出力。

---

## 6. 着手コマンド（M2）

```bash
brew install go            # 未インストールなら（今回導入・go1.26.5）
cd aggregator
go build ./...            # arm64 でビルドが通るか
go test ./...              # 既存テストが緑か
go run ./cmd/chainpoc      # Step A/B PoC（3ステップ連結+RSSI整合の回路内計算・所要約5分）を再実行して確認
# go run .                 # Spike A(interop検証) は zk-distance/build/ の再生成(circom/snarkjs)が要る

# 方式B（Nova/Sonobe, Rust）
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y   # 未インストールなら
cd nova_poc/sonobe        # vendored clone（無ければ week20/08 §7の手順で再生成）
cargo run --release --example uav_chain_step -p folding-schemes   # 所要ビルド込み数分、実行は約2秒
```
