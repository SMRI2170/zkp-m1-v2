# NEXT_STEPS — 次にやること（M2 Mac で着手）

最終更新: 2026-07-23 / 前提を掴むには先に `CLAUDE.md` → `week20/04_再帰ZKP_証明チェーン設計.md` を読む。

---

## 0. いまの一文サマリ

設計は「**再帰チェーン(IVC)・方式A＝gnark 再帰**」で確定済み。実装は「木・一括集約(M2, `aggregator/`)」まで。
**次は、各ノードが前の証明を回路内で検証して内包する"逐次チェーン"を gnark で 2〜3 ステップ動かす PoC（Step A）。**

---

## 1. 直近ゴール：再帰チェーン PoC Step A

**「ノードi が、前のノードの証明 π_{i-1} を自分の回路内で再帰検証し（＝内包）、
自分の観測を足した新しい証明 π_i を作る」を 2〜3 ステップ連結して動かす。**

### 回路内で強制すること（Step A の最小セット）
1. **前の証明 π_{i-1} を再帰検証**（gnark `std/recursion/groth16`）＝前を内包
2. `drone_id_commitment` と `time_bucket` が前の累積 z_{i-1} と一致（同一ドローン・同一時間窓）
3. `consistent_count += ok`（この段では ok は入力で可。RSSI整合はStep Bで載せる）
4. 更新した累積 z_i を public 出力にして π_i を生成

### 成功条件
- 正常系: 3 ステップ連結して最終 π_3 が生成・検証でき、`consistent_count` が正しく育つ。
- 否定系: drone_id/time_bucket を食い違わせる or 偽の π_{i-1} を渡すと**π_i が生成できない**ことを確認。
- 各中間 π_k が**単体で検証できる**こと（方式Aの肝＝「取ってきて検証」）。

---

## 2. 流用する既存資産（ゼロから作らない）

- `aggregator/main.go` … **Spike A（snarkjs Groth16 を gnark-crypto で検証する interop）**。点の座標変換は解決済み。
- `aggregator/snarkimport/` … snarkjs の vkey/proof/public を gnark 表現へ変換。
- `aggregator/cmd/aggregate/`, `cmd/verify1/` … 集約・単一検証のエントリ。**木→チェーンに組み替える土台**。
- `aggregator/membership/`, `completeness/` … Sybil・検閲検知（Step C 以降で接続）。
- `circuits/uav_witness_attestation.circom` の public 信号（idx6/10/11/12/13/14）= 累積が参照する値。

> gnark 版 `aggregate_circuit.go`（N proof 再帰検証＋関係制約）の有無を最初に確認し、
> **木構造(N一括)を "前の1件を検証して1歩進める" 逐次ステップに変形**するのが Step A の実体。

---

## 3. その後の段階（Step B→D）

| Step | 内容 |
|---|---|
| **A** | gnark で 2〜3 ステップの逐次再帰検証（前を内包）＝上記 |
| **B** | **RSSI 整合**を step 回路に折り込む（`remoteid_consistency_rel` 相当を回路内で計算し ok を出す） |
| **C** | **membership（登録端末のMerkle）＋二重計上防止**（included_acc に未包含のときだけ畳む）を追加 |
| **D** | **最終圧縮 → EVM verifier 出力** → Hardhat で1回検証し trusted/spoof 記録・gas 定数を確認 |

---

## 4. 設計上まだ埋めるべき穴（week20/04 §14 より・実装時に効く）

実装で必ず考慮する 3 点（目的①複数ノードでRSSI検証／②危険か否かを内包して証明 のため）:
- **(a) 危険判定を回路内で計算し `is_spoof` を証明の公開出力に**（②の核）。判定規則を一意に
  （例: `suspicious ≥ K → 危険` / `consistent ≥ K → 安全` / それ以外 `undetermined`）。
- **(b) 各ステップに入力真正性(R3)**: ドローン署名検証・freshness・観測と放送の束縛（①の核。無いと捏造で"整合"を作れる）。
- **(c) GPS真正性＋RSSI較正**を設計に明示・証明にバインド（多ノード検証が意味を持つ前提）。

---

## 5. 代替案（今は選ばない・記録のみ）

- **方式B（Nova/Sonobe, Rust）**: 1ステップが軽く省メモリ＝エッジで各ノードが折り畳む構成向き。
  ただし中間が単体検証不可で「取ってきて検証」とズレる。**"スマホ自身に折り畳ませたい/連鎖が非常に長い"
  となったら PoC で gnark と実測比較**して再検討。

---

## 6. 着手コマンド（M2）

```bash
cd aggregator
go build ./...            # まず arm64 でビルドが通るか
go test ./...            # 既存テストが緑か
go run .                 # Spike A(interop検証) が通るか＝再帰の土台がある確認
# → 通ったら aggregate_circuit を逐次チェーン化する Step A に着手
```
