# プライバシー保護型K-of-N設計案（コミットメント・nullifier・Nova）の実現性検証

作成日: 2026-07-29 / 目的: ユーザから提示された「各ユーザが位置・時刻・RSSIを秘密witnessとして保持し、
コミットメント・nullifier・Merkleメンバーシップ・NovaによるFoldを組み合わせて、個人観測を公開せず
K-of-N判定を実現する」という設計案を検証する。**Sonobeのソースコードを実際に読み、どこまでが素の
Nova(Sonobe)で実現可能で、どこに具体的な障害があるかを裏付ける。設計文書であり実装はまだ行っていない。**

---

## 0. 結論（先に）

**提案された設計の大部分（コミットメント・回路内チェック内容・累積結果のみの公開・nullifier・Merkle
メンバーシップ・K-of-N判定・非信頼リレー）は健全で、標準的なZK技術で実現可能。** 一方で、
**設計案の核心である「Novaで前ユーザの状態を、witnessを受け取らずに引き継ぐ」（提案書§6-8）は、
素のNova（Sonobe）のIVCProofをそのまま使う限り成立しない**ことを、Sonobeのソースコードから
具体的に確認した（§3）。提案書自身の§13がこの懸念を正しく予見しており、対処として挙げていた
「PCD構成」「各ユーザが独立証明を作り最後に統合」の方向性は妥当。

| 提案書の項目 | 実現可能性 | 根拠 |
|---|---|---|
| §1-3 秘密witness・コミットメント | ✅ | 標準的なハッシュコミットメント |
| §4 回路内チェック内容 | ✅ | `circuits/uav_witness_attestation.circom`が同種の検証を実装済み |
| §5 累積結果のみ公開 | ✅ | `week20/04`§4の`z`構造と同じ設計 |
| **§6-8 Novaでwitnessを渡さず継続** | ❌（素のNovaでは不可） | §3で実証。要PCD化 |
| §9 nullifier（二重計上防止） | ✅・未実装 | `NEXT_STEPS.md`のStep C相当 |
| §10 Merkleメンバーシップ | ✅・未実装 | `week20/04`§3項目3、Step C相当 |
| §11 K-of-N判定・結果のみ公開 | ✅ | 既存設計と一致 |
| §12 非信頼リレー | △条件付き | §6-8が解決しない限りwitnessも一緒に流れる |

---

## 1. 検証対象の設計（提案書の要約）

ユーザから提示された設計案の骨子:

1. 各ユーザ端末が保持する秘密情報 `w_i = (position_i, timestamp_i, RSSI_i, secret_i)`
2. 観測データのコミットメント `C_i = H(sessionID, position_i, timestamp_i, RSSI_i, r_i)`
3. 回路内で確認: コミットメント一致・Remote ID受信・時刻範囲・距離計算・整合判定・二重計上でない
4. 外部公開は累積結果のみ（セッションID・観測数・整合数・K-of-N成立結果・nullifier集合Root・ZKP）。
   個人の座標・時刻・RSSI・実名・端末ID・整合/不整合の個人結果は非公開
5. **前の蓄積状態を「公開状態＋前状態のハッシュ＋証明」として受け取り、前ユーザの位置・RSSI・
   Witnessは受け取らない**（提案書§6、原文ママ）
6. 自分の観測をFold: `S_i = Fold(S_{i-1}, w_i)`
7. nullifier `N_i = H(userSecret_i, sessionID)` で同一セッション内の二重参加を防止
8. 登録済み端末であることをMerkle Treeメンバーシップで匿名に証明
9. 最終的にK-of-N判定（`consistentCount ≥ K` 等）のみを公開
10. 非信頼リレー（サーバ/分散ストレージ）を中継に使うが、位置・RSSI・時刻・秘密鍵・Witnessは渡さない
11. **提案書自身の懸念（§13）**: 「通常のNova実装では次のFoldにprover内部状態が必要になる場合があり、
    その内部状態に前ユーザの秘密Witnessが含まれる場合、直接共有してはいけない」

---

## 2. 実現可能な部分（§1-5, 9-12）

これらは本プロジェクトの既存設計・既存回路の延長線上にあり、新規のクリプト設計を要しない:

- **コミットメント（§2-3）**: ハッシュコミットメント自体は標準技術。circom/gnark/arkworksいずれでも
  Poseidon等で実装可能。
- **回路内チェック（§4）**: `circuits/uav_witness_attestation.circom`が「署名検証＋freshness＋
  RemoteID束縛」という同種のチェックを既に実装済み（`CLAUDE.md`§3参照、約11.8k制約）。今回の
  コミットメント一致・時刻範囲・整合判定を追加するのは既存パターンの延長。
- **累積結果のみの公開（§5, §11）**: `week20/04`§4の累積状態`z = (drone_id_commitment, time_bucket,
  consistent_count, suspicious_count, included_acc, step_count)`と設計思想が完全に一致する。
- **nullifier（§9）／Merkleメンバーシップ（§10）**: `week20/04`§3の項目3（登録端末のMerkle
  メンバーシップ、Sybil対策）・項目4（二重計上でないことの強制）にそのまま対応する。これは
  `NEXT_STEPS.md`のStep C（「membership（登録端末のMerkle）＋二重計上防止」）として**既に計画済みだが
  ⬜未着手**の項目そのもの。設計は既にあり、実装が追いついていないだけ。

---

## 3. 実現できない部分の具体的根拠 ── §6-8「Novaでwitnessを渡さず継続」

### 3.1 `IVCProof`は生のwitnessベクトルを直接含む

Sonobeの`Witness<C>`構造体（`nova_poc/sonobe/folding-schemes/src/folding/nova/mod.rs:171-176`）:

```rust
pub struct Witness<C: Curve> {
    pub E: Vec<C::ScalarField>,   // 生の値（コミットメントではない）
    pub rE: C::ScalarField,       // ブラインディング乱数
    pub W: Vec<C::ScalarField>,   // 生の値 ← 回路内のprivate wireの値そのもの
    pub rW: C::ScalarField,
}
```

`IVCProof<C1, C2>`（同ファイル:426-445）はこの`Witness`を`W_i`・`w_i`としてそのまま含む。つまり
提案書§6が「受け取らない」としている「前ユーザのWitness」は、**提案書自身が§6で受け取る対象として
挙げている「前状態が正しいことを示す証明」の中に、実質そのまま同梱されている**。

### 3.2 現行実装は非ブラインディング設定（H=false）

本プロジェクトのNova実装（`nova_poc/nova-mobile/src/lib.rs`・`nova_poc/uav_chain_step.rs`）は
いずれも次の型で構成されている:

```rust
type N = Nova<Projective, Projective2, ChainStepCircuit<Fr>,
              KZG<'static, Bn254>, Pedersen<Projective2>, false>;
//                                                          ^^^^^ H=false（非ブラインディング）
```

`H`はSonobeのdocコメントで「commitment schemeがブラインディングかどうかを指定する」と説明されている
（`nova_poc/sonobe/folding-schemes/src/folding/nova/mod.rs:451`付近）。`H=false`では`rW`/`rE`は常に
ゼロになる（同ファイル`Witness::new`実装、§4参照）。ただし**`H=true`にしても`IVCProof.W_i`自体が
生の`W`ベクトルを含む点は変わらない**ため、ブラインディング設定の有無に関わらず問題は解消しない。

### 3.3 具体的な漏洩の証明（1ステップ目で完全復元できる）

NIFSの折り込み演算（`nova_poc/sonobe/folding-schemes/src/folding/nova/nifs/nova.rs:104-127`,
`fn fold_witness`）を確認したところ、witnessは次の線形結合で更新される:

```rust
let W: Vec<C::ScalarField> = W_i.W.iter().zip(&w_i.W)
    .map(|(a, b)| *a + (r * b)).collect();
// つまり: W_new = W_old + r * w_incoming
```

（インスタンス側`U_i.x`も`nifs/nova_circuits.rs:142-149`で同型の`U_i.x + r*u_i.x`という線形結合。
Nova論文のNIFS構成通り。）

1人目のFold（`i=1`）では`W_0`はダミー（全ゼロ、`Nova::init`のダミーwitness）なので:

```
W_1 = W_0 + r_1 * w_1 = r_1 * w_1
```

`r_1`はFiat-Shamirチャレンジであり、**公開されている委譲/コミットされたインスタンスから誰でも
再計算できる値**（秘密ではない）。よって`IVCProof`（＝提案書§6の「前状態が正しいことを示す証明」）を
受け取った2人目（あるいはそれを中継する非信頼リレー）は:

```
w_1 = W_1 / r_1
```

として**1人目の生witnessベクトル（回路内のprivate wireすべて、＝座標・時刻・RSSIから計算された
中間値一式）を完全に復元できる**。§6「前ユーザの位置・RSSI・Witnessは受け取らない」は、
素のNovaの`IVCProof`をそのまま回す限り**成立しない**。

（2ステップ目以降は`W_2 = r_1 w_1 + r_2 w_2`のように複数ステップが混ざるため単純な割り算では
分離できなくなるが、`r_1`・`r_2`は依然として公開値であり、後続の各ステップでも新たに`w_i`が
そのまま線形結合に加わり続けるため、原理的な情報漏洩自体は解消されない。多ステップでの漏洩量の
定量評価は未実施。）

---

## 4. 提案書§13の対処案の評価

提案書自身が§13で挙げていた4つの対処案を、Sonobeの実際の機能に照らして評価する。

| 対処案 | 評価 |
|---|---|
| 各ステップの秘密Witnessが次ステップへ残らない構成にする | 方向性は正しい。具体的には「毎ステップ、witnessを含まない圧縮証明に変換してから渡す」ことに相当（＝実質PCD） |
| 公開状態と証明だけで更新可能なPCD構成を使う | **これが本質的な解**。Sonobeには`Decider`モジュール（`folding-schemes/src/folding/nova/decider.rs`, `decider_eth.rs`）が実装済みで、畳み込んだIVC状態を最終的にGroth16等の小さいSNARKへ圧縮する機能がある。これを毎ステップ使えばwitnessを渡さずに継続できる |
| Zero-Knowledge PCDまたはmulti-foldingへ拡張する | Sonobeの`Nova`実装自体はmulti-instance foldingを設計上サポートしない（`week20/12`§7で確認済み、`Error::NoMultiInstances`）。HyperNova等の同一Sonobe内の別方式がZK-PCD相当を提供するかは未調査 |
| 各ユーザが独立証明を作り、最後に再帰統合する | **実質「集約(aggregation)」であり、既存の`aggregator/cmd/aggregate`（M1/M2, gnark）がそのまま使える**。各ユーザの証明は自己完結（公開シグナルのみ外部に出る）ため、witness漏洩の問題自体が原理的に発生しない |

### 4.1 「毎ステップDecider」案のコスト（未計測・要注意）

`Decider`は本来「最後に1回だけ」使う想定の重い処理（Groth16等のSNARK証明生成を伴う）。これを
**毎ステップ**実行してからwitnessを渡す設計にすると、`week20/08`で確認したNova(方式B)の速度優位性
（方式Aの30〜50倍高速・130〜280ms/step）が目減りする可能性が高い。具体的にどの程度のコスト増になるかは
**未計測**であり、実装前に確認すべき最重要ポイント。

---

## 5. 段階的実装案（提案書の第1〜3段階）への評価

提案された順序は妥当と判断する。

| 段階 | 内容 | 評価 |
|---|---|---|
| 第1段階 | 1台のスマホが複数観測をNovaでFold・累積判定のみ公開・実機性能測定 | **`week20/08`・`09`で実測済み**（既完了相当） |
| 第2段階 | 複数ユーザが個別にコミットメント＋ZKPを生成、非信頼リレー経由で共有、署名・nullifier導入、K-of-N実装 | **witness漏洩の問題が原理的に起きない**（各証明が自己完結）。既存の集約(M1/M2)パイプラインへnullifier(§9)・Merkleメンバーシップ(§10)を追加する作業に相当し、`Step C`（`NEXT_STEPS.md`、まだ⬜）とほぼ同じスコープ。**最も早く安全に着手できる段階** |
| 第3段階 | ユーザ間で1つの証明付き状態を順次更新、ZK-PCD/multi-folding導入、Fork・欠落・二重計上・なりすまし評価 | §3-4の問題を解決する追加設計・実装が必須。Sonobeに「毎ステップ軽量PCD」の既製品は無く、Deciderの毎ステップ利用のコスト計測から始める研究的な作業になる |

---

## 6. 推奨する次の一手

1. **第2段階から着手する**: witness漏洩の心配がなく、既存の集約(M1/M2)パイプラインの延長として
   実装できる。nullifier生成・検証、Merkleメンバーシップ証明の回路への追加が具体的な作業になる
   （＝`Step C`の実装そのもの）。
2. **第3段階は「毎ステップDecider」のコスト実測から始める**: 1ステップだけでよいので、
   `Nova::prove_step`の後に`Decider::prove`を呼んで圧縮証明を作る時間・サイズを計測し、
   方式Bの速度優位性がどれだけ残るかを先に確認してから設計を詰める。

---

## 7. 参照

- `week20/04_再帰ZKP_証明チェーン設計.md`§3-4 … 累積状態z・登録端末Merkle・二重計上防止の元設計
- `week20/08_Nova方式B_PoC実装結果.md` … 単一ノードでの実測（第1段階の実績）
- `week20/11_Nova実装ライブラリ詳細_Sonobe.md` … Sonobeライブラリの構成
- `week20/12_Nova方式B_複数ノード蓄積を可能にする設計課題.md`§7 … Novaのmulti-instance非対応の確認
- `NEXT_STEPS.md`§3 … Step C（membership＋二重計上防止、まだ⬜未着手）
- Sonobeコード直接参照:
  - `nova_poc/sonobe/folding-schemes/src/folding/nova/mod.rs:171-176`（`Witness`構造体）
  - `nova_poc/sonobe/folding-schemes/src/folding/nova/mod.rs:426-445`（`IVCProof`構造体）
  - `nova_poc/sonobe/folding-schemes/src/folding/nova/nifs/nova.rs:104-127`（`fold_witness`の線形結合）
  - `nova_poc/sonobe/folding-schemes/src/folding/nova/nifs/nova_circuits.rs:142-149`（インスタンス側の同型の折り込み）
  - `nova_poc/sonobe/folding-schemes/src/folding/nova/decider.rs`, `decider_eth.rs`（Deciderモジュール）
