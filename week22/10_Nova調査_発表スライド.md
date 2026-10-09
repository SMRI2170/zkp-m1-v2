---
marp: true
paginate: true
---

<!-- _class: lead -->

# Novaによる逐次集約

## Week 22 調査と採用判断

---

# Novaの仕組み

Novaは、同じ状態更新を繰り返す計算を扱うIVC方式。

```text
状態 z₀
  ↓ step F(w₀)
状態 z₁
  ↓ step F(w₁)
状態 z₂ … zₙ
```

各stepの実行をfoldし、累積proofで検証する。

*出典: week22/01 §「Novaとは何か」*

---

# この研究との適合性

端末の観測を一件ずつ追加する、順序付き集約に向く。

- 観測ごとに状態を更新できる
- 同じstep回路を繰り返し使える
- 最終状態までの実行を一つのIVC proofで検証できる

Novaは、独立した二つの集合を任意にmergeする仕組みではない。

*出典: week22/01 §「この研究でNovaに向く部分」「Novaだけでは解決しない点」*

---

# 既存のleaf proofとの接続

NovaにCircom / Groth16 proofを渡すだけでは、その正しさは保証されない。

1. Novaのstep内でleaf proofを検証する
   既存leafを維持できるが、stepごとの検証が重くなる
2. leafの関係をNovaのstep回路へ移植する
   検証経路は単純になるが、回路の再実装が必要

短期は固定VKで検証するBridgeを作り、接続方法と性能を確認する。
長期案ではCircomの関係をNova向けに再実装する。

*出典: week22/01 §「既存leaf Groth16 proofの接続」*

---

# 実装候補と比較対象

**Microsoft Nova**

- Novaの参照実装
- 調査・比較の基準にしやすい
- 低レベルAPIのため、既存アプリへの接続は別途必要

**Sonobe**

- Nova / CycleFold等を扱うRustライブラリ
- EVM Deciderを見据えた構成
- 調査時点ではpre-releaseのため、API変更に注意

本研究のPoCはSonobeを使用。最終判断では直接再帰Groth16とも比較する。

*出典: week22/01 §「実装候補の評価」「採用判断」*

---

# PoCで確認した範囲

- RSSI整合の判定と件数更新を3 stepで実行
- Pixel 8で各step 485〜1,198 ms、最終検証172 msを確認
- M2 Macでは各step 135〜281 ms、最終検証28 ms
- countを書き換えたproofを拒否

計測環境が異なるため、端末間の時間は直接比較しない。

**未確認:** 実leaf proofの検証、membership、nullifierによる二重計上防止、EVM最終検証

このPoCは逐次更新の実証であり、本番用の証明経路全体を実証したものではない。

*出典: week20/08 §5.1、week20/09 §5.3.1、week22/01 §「2026-10-02時点の実装照合」*

---

# 採用判断と次の検証

Novaは逐次集約の候補。本番採用は、次の経路を一つのproofで確認してから判断する。

1. leaf proofを固定VKで検証
2. membershipとnullifierをstepへ接続
3. 10 step程度で正常系・否定系を検証
4. Decider proofをEVMで検証し、V1 ABIとgasを測定

直接再帰Groth16と同じ条件で、時間・メモリ・proofサイズも比較する。

*出典: week22/01 §「採用判断を更新するための必須条件」、week22/07 §「完了とみなす条件」*
