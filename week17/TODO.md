# TODO — マルチ端末 × ブロックチェーンによる UAV RemoteID 検証

作成日: 2026-07-08 / ブランチ: `acoustic-detection-zk`
関連: [DESIGN_multi_witness_blockchain.md](DESIGN_multi_witness_blockchain.md)

現状（実装済み）と今後（残作業）は [status_and_roadmap.pptx](status_and_roadmap.pptx) も参照。

---

## 優先度：高（直近）

- [ ] 回路 `circuits/remoteid_consistency.circom` を **相対許容（±%）版**に更新する
  - 固定 `TOL_CM` は RSSI の現実（相対誤差）に合わない
  - `lower = claimed*(1-r)`, `upper = claimed*(1+r)` に変更
  - 整合 / 詐称サンプルで再検証
- [ ] **実機 DJI で RSSI 較正**（本命の検証）
  - 複数スマホで RemoteID を受信し `(rssi, 真距離)` を収集
  - `scripts/rssi/rssi_ranging.py` で `A / n` を fit → `TOL` を確定
  - 30m で本当に矛盾検出できるかを実測で確認
- [ ] `consistency_ok` を **M1 レジストリ / witness 回路に統合**
  - 多端末で「放送位置の真偽」を合意できるようにする

## 優先度：中

- [ ] **M2 再帰アグリゲータ**（gnark or Sonobe）
  - N台の証明を集約 proof 1個に畳み込む
  - 「同一ドローン・端末相異・各 within30」を回路内で強制（定数 gas）
- [ ] **M3 真正性（耐偽装の核）**
  - [ ] ドローン署名 RemoteID（DRIP / F3411 Auth）を回路内検証 → 偽ドローン ID 封じ
  - [ ] 端末アテステーション（Android Key Attestation / iOS App Attest）でセンサ値の出所を署名
  - [ ] 署名メッセージに直近ブロックハッシュを混ぜてリプレイ防止
- [ ] **許可型 EVM（Besu / Quorum）** へコントラクトをデプロイ
  - Sybil 耐性・プライバシー・コストの観点で本システムに適合

## 優先度：低 / 整備

- [ ] アプリの未コミットな大規模リファクタを収束させる（`main.dart` モノリス＋孤立モジュールの整理）
- [ ] RSSI 較正用のログ収集 UI / 整合判定の表示を整える
- [ ] 多 witness 三角測量（AoA / TDoA）による精密化（RSSI 単独の粗さ・リレー攻撃への対処）

---

## 設計上の位置づけ（忘れない）

- 現状は「K台合意 ＝ **登録署名が揃った**」段階で、「K台合意 ＝ **真正**」はまだ未達
- 軸は「接近の証明」ではなく「**なりすまし検出の証明**」に置く
- 耐偽装の核は M3（真正性）＋実測裏取りに依存する ＝ これらは「任意」ではなく **必須**
