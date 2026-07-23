# CLAUDE.md — プロジェクト・オンボーディング

このファイルは Claude Code が自動で読み込む。**まずここを読んで全体像を掴み、次に `NEXT_STEPS.md`
（今の作業）と `week20/04_再帰ZKP_証明チェーン設計.md`（確定した設計）を読むこと。**

---

## 1. このプロジェクトは何か（一言）

**zk-UAV スプーフィング検知**: ドローンを改造せず、周囲の複数の witness 端末が受信した RemoteID 放送の
**物理的整合性（RSSI と放送位置が矛盾しないか）をゼロ知識証明で示し、複数端末の証明を集約して
「なりすまし合意（K-of-N）」を作り、許可型ブロックチェーンに記録する**。
＝「**なりすまし検知の証明（proof of spoofing detection）**」。

- **証明すること**: 「登録端末が、同一ドローン放送について、座標・生RSSIを隠したまま RSSI 整合を判定し、K台で合意した」
- **隠すこと**: 端末の正確な GPS 座標・生 RSSI サンプル
- **非目標**: 放送位置が"真"である証明・中継/ワームホール対策・ドローン側の改造（詳細 `week20/02`）

---

## 2. アーキテクチャ（3層）

```
[端末層] スマホ/ラズパイが各自 RSSI 整合を証明
   circom/Groth16(BN254) を rapidsnark でオンデバイス生成
   回路: circuits/remoteid_consistency_rel.circom（軽・整合の核）
        circuits/uav_witness_attestation.circom（重・端末/ドローン署名+freshness, ~11.8k制約）
        │  N 個の witness 証明
        ▼
[集約層] gnark(Go) が N 個の証明を再帰検証し関係を回路内で強制 → 1つの集約証明
   aggregator/ … drone_id/time_bucket 一致・distinct端末・K-of-N集計
   membership(Sybil)・completeness(検閲検知) を併設
        │
        ▼
[チェーン層] 集約証明を1回検証し trusted/spoof を記録（定数 gas）
   contracts/ … AttestationRegistry.sol + AggregateVerifier.sol(gnark生成)
```

**現在進行中の発展**: 上記の「木・一括集約(M2)」を、各ノードが**前の証明を内包しながら逐次積み上げる
再帰チェーン(IVC)** に組み替える設計を確定済み（→ `week20/04`・`NEXT_STEPS.md`）。

---

## 3. ディレクトリ地図（現状・正確）

| パス | 中身 |
|---|---|
| `circuits/` | **現行の Circom 回路**。`remoteid_consistency_rel`（RSSI整合の核）/ `uav_witness_attestation`（署名+freshness）/ `lib_uav_safety`（共通lib）。※旧 `distance_30m_*` は削除済 |
| `aggregator/` | **gnark(Go) 集約器**。`main.go`=Spike A(snarkjs証明をgnarkで検証するinterop) / `cmd/aggregate`=集約 / `cmd/verify1`=単一検証 / `cmd/deviceroot`=端末Merkle根 / `membership/`・`completeness/` |
| `contracts/` | Hardhat。`AttestationRegistry.sol`(K-of-N集計) / `AggregateVerifier.sol`(gnark生成) / `Groth16Verifier.sol` |
| `rapidsnark_app/` | **Flutter アプリ**（Android）。`lib/main.dart` に回路**選択式**UI。`assets/circuits/` に zkey/wcd（`remoteid_consistency` 等） |
| `zk-distance/` | 回路ビルド成果物・サンプル入力・最適化比較。`build/` はgitignore(要再生成) |
| `uav/` | Raspberry Pi 側 RemoteID(OpenDroneID/ASTM F3411) 送信・センサ統合 |
| `week15`〜`week20/` | **週次の設計ドキュメント（日本語 md）**。最新の設計思考はここ。特に week18(RSSI位置特定)・week19(モバイルZKPフレームワーク調査)・week20(再帰ZKP設計) |
| `scripts/` | ビルド `.sh`（数本）＋ **スライド生成器 `generate_*_slides.py`（~45本, python-pptx）** |
| `siles-pptx/` | 生成した進捗スライド（一部tracked）。※新規 `.pptx` はgitignore＝スクリプトから再生成 |

---

## 4. マイルストーン（現在地）

| # | 内容 | 状態 |
|---|---|---|
| M1 | 端末が circom/Groth16 で witness 証明 → `AttestationRegistry` が1件ずつ検証しK台数える | ✅ 実装・E2E実証済 |
| M2 | gnark が N証明を**再帰検証+関係強制**し1つに集約 → オンチェーン**定数gas** | 🟡 `aggregator/` 実装あり（Spike A/B 相当） |
| week18 | RSSI で位置特定・K-of-N合意・multilateration の設計＋スライド | ✅ md/pptx 完成 |
| week19 | モバイルZKPフレームワーク調査・Mopro実機PoC・処理時間実測 | ✅ 完成（circom rapidsnark≈0.01s vs Noir bb≈0.13s 実測） |
| week20 | スマホ実装可否・ZKP要件(R1-R7)・**再帰チェーン(IVC)設計** | ✅ 設計確定（方式A/gnark主軸） |
| **次** | **再帰チェーン PoC（各ノードが前を内包）Step A** | ⬜ 未着手 → `NEXT_STEPS.md` |

---

## 5. 確定している設計判断（重要・蒸し返さない）

- **再帰の内包は「方式A＝再帰検証（gnark）」を主軸**、方式B(Nova/Folding)は省メモリ代替。
  理由: 各累積が**単体検証可能**で「チェーンから取ってきて検証」に忠実・BN254/EVM着地・現行aggregator流用。
  （詳細 `week20/04`・`week20/05`。gnark vs Nova の比較も結論済み＝現状 **gnark**）
- **ノードは全員対等**（スマホもラズパイも「ノード」）。ただし**重い再帰検証はラズパイが担い、
  スマホは軽い witness 証明(circom/Groth16)だけ**出す能力ベース分担。
- 端末層は **circom/Groth16(rapidsnark)** で確定（Flutter で唯一"即使える"・実装済）。Noir は条件付き(Android は Zig)。
- 共有経路は**許可型ブロックチェーン**（取得→検証→書き戻し）。

---

## 6. ビルド/実行/テスト（M2 arm64）

```bash
# 依存の再取得（gitignoreで除外したビルド物を作り直す）
npm install                          # ルート
(cd contracts && npm install)        # Hardhat
(cd rapidsnark_app && flutter pub get)
(cd aggregator && go build ./...)    # ※旧 aggregate/verify1 は x86_64 バイナリ。arm64で作り直す

# テスト/実行
(cd contracts && npx hardhat test)                       # コントラクト
(cd aggregator && go test ./...)                         # 集約器
(cd aggregator && go run . )                             # Spike A: interop検証(引数省略で既定入力)
python3 scripts/generate_week19_unified_slides.py        # スライド生成(要 pip install python-pptx)
```

必要ツール: `circom` `snarkjs` `node` `go(1.25+)` `flutter` `python3`（＋Noir系を触るなら `rust`/`nargo`/`bb`）。

---

## 7. 作業の流儀（ユーザの好み）

- **ドキュメントは日本語 md**。週次(`weekNN/`)に設計思考を残す文化。
- **スライド**は python-pptx で生成。デザインは「進捗第11回」スタイル（白背景・黒字・Yu Gothic/Courier New・
  藍色アクセントは控えめ）。体言止め＋■(大)/・(インデント小)の階層。
- **教授レビューを想定**: 比較は「暫定・同条件でない」と明記、結論を先に、APKビルドと実機証明を区別、専門用語を噛み砕く。
- 変更のたびにコミットしない（**ユーザが依頼した時だけ**）。

---

## 8. リポジトリ / 移行メモ

- このリポジトリは **`SMRI2170/zkp-m1-v2`（private）**。Intel Mac から M2 Mac へ移行済み。
- 除外物（M2で再生成）: `build/` `node_modules/` `.dart_tool/`・x86_64バイナリ(`aggregator/aggregate,verify1`)・生成`.pptx`。
- 現行ブランチは `acoustic-detection-zk`（移行時に main へ push）。
```
