# 週18 タスク — RSSI による RemoteID なりすまし検知

作成日: 2026-07-09 / ブランチ: `acoustic-detection-zk`
前提: [week17/TODO.md](../week17/TODO.md) / [week17/DESIGN_multi_witness_blockchain.md](../week17/DESIGN_multi_witness_blockchain.md)

## 週18のゴール（1行）

**「RSSI で RemoteID の偽り（位置詐称・中継）を、本当に検知できるか」を定量評価と実機で示す。**
既存資産: `circuits/remoteid_consistency.circom` / `scripts/rssi/rssi_ranging.py` /
`rapidsnark_app/lib/core/rssi_ranging.dart`（アプリ配線済）。

---

## Phase 1 — 判定ロジックを現実に合わせる

- [x] **1-1. 相対許容(±%)版の回路** ✅
  `circuits/remoteid_consistency_rel.circom`（新規, ±90% = TOL 90/100・約650制約）
  - 受け入れ: 整合→1 / 詐称→0 を確認済（固定版は残置）
  - アプリ側 `lib/core/rssi_ranging.dart` は既に相対帯（relBand, 既定±91%）で回路と整合
- [x] **1-2. ロバスト化（単発 RSSI は粗い）** ✅
  複数サンプルの中央値で `measured_range` を出す（外れ値・マルチパス対策）
  - `rssi_ranging.py` `distance_from_samples` 追加。真30m・外れ値20%で 14.3m→4.5m に改善
  - Dart `distanceFromSamples` / `checkRssiConsistencyFromSamples` 追加
  - アプリ: 直近10件の RSSI を中央値集約して判定（BLE/WiFi 両経路, analyze clean）
- [ ] **1-3. 環境プロファイル**
  `n`(伝搬指数) を自由空間/市街地で切替可能に（既定と、実測 fit 値の差し替え口）

## Phase 2 — 偽装シナリオ定義と合成評価（週18の核）

- [x] **2-1. 脅威モデルの明文化** ✅ `week18/THREAT_MODEL.md`
  - 攻撃 A 位置詐称(主眼) / B 捏造 / C リプレイ / D 中継(限界) / E Sybil / F witness GPS詐称 / G DoS
- [x] **2-2. 評価ハーネス** ✅ `scripts/rssi/eval_spoof_detection.py`
  - Δ掃引: 30m を N=5 で検知率91%(AUC0.98) / 20m 75% / 10m 28%（粗い詐称は検知可）
  - N掃引(Δ=30m): 1台64% → 8台98% / σ掃引: σ4dB 91% → σ8dB 48%
- [x] **2-3. 設計値の決定（暫定）** ✅
  - r=±90%（±2σ）/ 集約M=10 / witness ≥8 目安。K は実機 σ 確定後に再算出

## Phase 3 — 実機 RSSI 収集と較正（feasibility）

- [ ] **3-1. アプリにログ収集機能**
  `(rssi, broadcast_pos, phone_gps, timestamp)` を CSV/JSON 保存（既存の RSSI-check ログを永続化）
- [ ] **3-2. 実機 DJI で較正データ収集**
  既知距離（3/10/30m 等）で複数サンプル取得（`week18/rssi_calibration.csv`）
- [ ] **3-3. 較正と検証**
  `rssi_ranging.py` で `A/n` を fit → `TOL` 確定 → 実データで 2-2 の評価を再実行

## Phase 4 — 多 witness 統合デモ

- [x] **4-1. `consistency_ok` を witness 回路/レジストリに統合** ✅
  `uav_witness_attestation.circom` に `measured_range_cm` 入力＋`consistency_ok` 出力(public15)
  `AttestationRegistry` に consistentCount/suspiciousCount と ConsensusReached/SpoofAlert
- [x] **4-2. なりすまし合意のデモ** ✅
  Hardhat 11/11。整合K台→trusted / 矛盾K台→SpoofAlert、実証明3台(2整合+1詐称)でE2E確認

## Phase 5 — まとめ

- [x] **5-1. 週18スライド** ✅ `week18/week18_rssi_spoof_detection.pptx`（7枚・4:3）
  課題/原理 → 判定ロジック → 脅威モデル → 評価ROC → 回路・レジストリ統合 → 現状と今後

---

## 進め方の目安（依存順）

```
Phase1(1-1,1-2) ─┐
                 ├─▶ Phase2(評価で検知可否を数値化：ここが週18の主眼)
Phase1(1-3) ─────┘        │
                          ├─▶ Phase3(実機較正で仮定を検証)
                          └─▶ Phase4(多witnessで合意)  ─▶ Phase5(まとめ)
```

- **まず Phase 2（合成評価）** で「どの程度のズレなら検知できるか」を先に定量化する
  （実機が無くても週18の核＝"検知できるのか"に答えが出る）
- 実機（Phase 3）は較正データが取れ次第。取れない週は合成評価＋設計値確定まで進める

## 週18で答えを出したい問い

- 位置詐称は **何 m ズレたら** RSSI で検知できるか？（誤検知をどこまで抑えて）
- **何台の witness** があれば実用的な検知率になるか？
- 中継攻撃は本当に検知できないのか？（限界の明示）
