# 設計 — 包含性（網羅性）証明で検閲を封じる（#3b）

作成日: 2026-07-11 / 関連: security_attack_surface.pptx（検閲）/ censorship_solutions.pptx /
`aggregator/completeness/`（核を実装・テスト済み）

## 問題
集約は改ざんはできないが、**有効な proof を"間引く"（検閲）**ことで結果を歪められた
（例: 矛盾(spoof)票だけ落として consistentCount を水増し）。

## 解の核: 提出集合ルートの一致（実装済み）
1. 集約前に、提出集合（含めるべき全 device_pubkey）を **SubmissionRoot**（MiMC Merkle
   ルート）として **DA 層（Ethereum blob / Celestia / EigenDA）にコミット**する。
2. 集約は、自分が含めた葉から **同じ SubmissionRoot を再現できる**ことを回路内で証明する。
3. 契約は `集約の SubmissionRoot == DA コミット値` を確認する。
→ 集約者が1件でも間引くと Root が変わり一致しない → **間引き＝検閲を検知・拒否**。

- 回路: `aggregator/completeness/completeness.go`
  - 含めた N 台の leaf=MiMC(ax,ay) から Merkle ルートを構築し、public `SubmissionRoot` に一致を強制。
  - `go test ./completeness/` : 全提出を含める→成功 / 1件差し替え(間引き)→失敗。
- 回路外: `completeness.Root(axs,ays)` が DA にコミットする値を計算（回路と一致）。

## 集約回路 / 契約への統合（残配線）
- 集約回路（`cmd/aggregate`）に SubmissionRoot 出力を追加（#3a の Root と同様、
  含めた device_pubkey から completeness ルートを構築して public 出力）。
- 契約 `submitAggregate(proof, [.., SubmissionRoot])` で
  `require(SubmissionRoot == committedSubmissionRoot)`。committed 値は DA から取得/アンカー。
- コスト: #3a と同様、MiMC の軽微な上乗せ＋ setup 1回。

## 3a との違い（役割分担）
- **3a メンバーシップ**: 「含めた鍵が"登録集合"のメンバーか」（Sybil）。
- **3b 網羅性**: 「"提出集合"の全メンバーを含めたか」（検閲）。
- 両者は同じ MiMC Merkle 機構を、別の集合（登録 / 提出）に適用したもの。

## 前提と限界（正直に）
- **DA が必要**: SubmissionRoot は集約前に公開コミットされている前提（誰が・いつ提出集合を
  確定するか＝順序/締めの運用が要る）。
- **各 proof の検証と併用**: 空/無効スロットを埋められないよう、集約は各位置の proof も
  検証する（既存の再帰検証）。網羅性＝「committed 集合の全位置を有効 proof で満たした」。
- **当面の代替**: M1 直接フォールバック（実演済）と許可型チェーン（BFT合意＋全複製）で
  検閲は実運用上緩和できる。#3b は"無許可・トラストレス"環境で間引きを暗号学的に封じる形。

## 位置づけ
検閲対策の核（提出集合ルートの一致証明）を実装・テスト。
これで当初の攻撃面（★1 セットアップ / ★2 真正性 / 3a Sybil / 3b 検閲 / 4 集権）の
"核"がすべて実装まで到達した。残るは各機構の集約回路への本統合（重い setup 再実行）と、
DA 層の実接続。
