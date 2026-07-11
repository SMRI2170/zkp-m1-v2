# 詳細設計 — 登録メンバーシップの M2 集約回路への統合（#3a）

作成日: 2026-07-11
前提: `aggregator/membership/`（機構は実装・テスト済み）/ `aggregator/cmd/aggregate/`（現行の集約）/
`AttestationRegistry.deviceRoot`（アンカー済み）

## 目的
現行 M2 集約は device_pubkey の相異(distinct)のみ強制。**登録済みかは未検証**（Sybilの穴）。
membership.go で実証した Merkle メンバーシップを**集約回路に組み込み**、集約が
「相異なる"登録済み"K台」を保証し、契約は `Root == deviceRoot` を1回確認するだけ（定数gas）にする。

## 全体像
```
登録端末 → MiMC Merkle 木 → deviceRoot（オンチェーンに setDeviceRoot 済）
集約回路（既存の再帰検証＋関係強制）に追加:
   各 device_pubkey が deviceRoot のメンバーであることを回路内検証
   public 出力に Root を追加
契約 submitAggregate: Root == deviceRoot を require
```

## 技術設計

### 1. 鍵型の橋渡し（emulated → native）
集約回路の `device_pubkey`(ax,ay) は `emulated.Element[BN254Fr]`（多リムbs）。
membership 回路は native `frontend.Variable`。両者を繋ぐ:
- 外側フィールドも BN254 なので、reduce 済み emulated 値は native BN254 要素に一致。
- `field.Reduce(&pk)` 後、`native = Σ limb_i · 2^(64·i)`（リムbs の線形結合）で native 化。
- `native_ax, native_ay` を得て `leaf = MiMC(native_ax, native_ay)`。
- 注意: 必ず Reduce してから recompose（リムbs を正準化）。リムb幅は emulated params に一致させる。

### 2. 追加する回路 I/O（`AggCircuit`）
```go
// 追加入力（private）: 各端末の Merkle パス
Siblings [N][Depth]frontend.Variable
PathBits [N][Depth]frontend.Variable
// 追加出力（public）: 登録端末ルート
Root frontend.Variable `gnark:",public"`
```
Define 内、各 i について:
```
axN := recompose(field.Reduce(&wit[i].Public[IDX_PUBX]))
ayN := recompose(field.Reduce(&wit[i].Public[IDX_PUBY]))
leaf := MiMC(axN, ayN)
verifyMerklePath(leaf, Siblings[i], PathBits[i], Root)   // membership.go と同じ畳み込み
```
（membership.go の畳み込みロジックを共通関数に切り出して再利用）

### 3. コスト
追加分は N × (リムb recompose + MiMC(2) + Depth×MiMC(2))。
emulated ペアリング（1証明 ~2M制約）に対し MiMC は軽微 → 集約全体（N=3 で ~6.4M）に
数千〜数万制約の上乗せ程度。setup は1回だけ再実行（~15分）。

### 4. オフ回路（登録木とパス生成）
- 登録端末集合から MiMC 木を構築（`membership_test.go` の `buildTree` を共通化）。
- Root を `deviceRoot` として `setDeviceRoot(root)` でオンチェーンに設定。
- 集約時、含める N 台の (ax,ay) のパスを生成して witness に供給。
- 木の hash は gnark-crypto `MIMC_BN254`（回路内 MiMC と一致）。

### 5. 契約（`submitAggregate`）
集約 verifier を deploy し、`submitAggregate(proof, publicSignals)`:
```
require(verifier.verifyProof(proof, publicSignals));       // 集約証明
require(publicSignals.Root == deviceRoot, "stale root");   // 登録メンバーシップ
// consistentCount/suspiciousCount で trusted/spoof を記録
```
→ 定数gasで「相異なる"登録済み"K台の整合/矛盾」を確定。

## 検証計画
- gnark テスト（`aggregate_membership_test.go`）:
  - 登録木に fixture の3端末＋他数台 → Root。
  - 正: 3端末が登録済み → 集約成功、出力 Root == 期待値、consistentCount=2。
  - 否: 1台を未登録鍵に差し替え → 集約失敗（メンバーシップ不成立）。
- オンチェーン: `setDeviceRoot(root)` 後、`submitAggregate` が Root 一致で通り、
  不一致（古い root）で revert。gas が N 非依存であることを計測。

## 留意点
- **registerDevice と deviceRoot の同期**: 登録集合が変わるたびに木を再計算し setDeviceRoot。
  頻繁なら増分更新（追記専用木）や、登録をエポック単位で締める運用に。
- **オンチェーン keccak deviceId と MiMC 木は別物**: M1直接は keccak、M2集約は MiMC 木。
  契約は両方を保持（M1: registeredDevice / M2: deviceRoot）。
- **実装コスト**: 主コストは setup 再実行（~15分）。回路変更・木構築・契約配線は軽い。

## 位置づけ
機構（membership.go）は実証済み。本設計はそれを emulated 集約へ差し込む配線。
実装すれば M2 の Sybil ギャップが閉じ、「相異なる"登録済み"K台」を定数gasで保証できる。
残る #3b（包含性証明＝網羅性による検閲封じ）はより難度が高く、当面は M1直接・許可型で緩和。
