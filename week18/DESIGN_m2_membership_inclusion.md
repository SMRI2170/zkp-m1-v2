# 設計 — M2 の登録メンバーシップ（Sybil）と包含性証明（検閲）

作成日: 2026-07-11 / 関連: security_attack_surface.pptx（#3）/ m2_recursive_aggregator.pptx

#3 は2つの穴を塞ぐ:
- **3a Sybil**: M2集約が device_pubkey の相異(distinct)のみ強制し、**登録済みかを未検証**だった。
- **3b 検閲**: 集約者が有効な proof を間引ける（結果の水増し）。

---

## 3a. 登録メンバーシップ（実装済み）
各 device_pubkey が「登録端末の Merkle ルート」のメンバーであることを**集約回路内で検証**する。

- 回路: `aggregator/membership/membership.go`
  - leaf = MiMC(ax, ay)、Merkle パスを畳んで Root へ、`Root` は public。
  - `go test ./membership/` : 登録3台→成功 / 未登録鍵混入→失敗（groth16・plonk）。
- 契約: `AttestationRegistry.deviceRoot`（+ `setDeviceRoot`）。
  - registerDevice で登録集合が変わったら、その MiMC Merkle ルートを設定。
  - 集約が公開する `Root == deviceRoot` を submitAggregate が確認 → **定数gas**で
    「相異なる"登録済み"K台」を保証。

### 集約回路への統合（残配線）
現状 M2 集約（`aggregator/cmd/aggregate`）は device_pubkey が emulated 要素。統合手順:
1. 各 witness の `device_pubkey`(emulated limbs) から leaf を作る（limbs を MiMC）。
2. membership.Circuit と同じ畳み込みで Root へ、`Root` を集約の public 出力に追加。
3. `submitAggregate` で `Root == deviceRoot` を require。
→ これで M2 は distinct だけでなく **登録メンバーシップ**も強制。
（コスト: 集約回路に N×Depth 回の MiMC。emulated 部より軽く、setup 1回のみ。）

---

## 3b. 包含性証明（検閲対策・設計）
集約者が「提出された全有効 proof を取り込んだ」ことを証明し、間引きを不可能にする。

- **方式**: 提出プールを DA 層（Ethereum blob / Celestia / EigenDA）に置き、その
  コミット（Merkle/KZG ルート）を集約回路の入力にする。集約は「そのルート配下の
  全有効 proof を処理した」ことを証明する（全走査 or 各リーフの取り込み証明）。
- **段階**: メンバーシップ(3a)と同じ Merkle 機構を、提出集合側にも適用する形。
  - 3a = 「含めた鍵が登録集合のメンバー」
  - 3b = 「登録集合(or 提出集合)の全メンバーを含めた」（網羅性）
- **当面の代替**: **M1 直接フォールバック**（実演済 `demo_m1_direct.js`）。各端末が
  自分の proof を直接チェーンに出せるので、集約者に検閲されても迂回できる。
- **許可型チェーン**では BFT合意＋全複製で検閲/DAがほぼ自動的に解ける（別デッキ参照）。

---

## まとめ
| 穴 | 状態 |
|---|---|
| 3a Sybil（登録メンバーシップ） | ✅ 回路実装＋テスト、契約に deviceRoot アンカー |
| 3a 集約への統合 | ⬜ 残配線（手順は上記） |
| 3b 検閲（包含性証明） | ⬜ 設計（DA＋網羅性）／当面 M1直接・許可型で緩和 |

到達点: 「相異なる"登録済み"K台」を回路で保証する仕組みが揃った。
残るは集約回路への統合と、網羅性（包含性証明）による検閲の根本封じ。
