# Nova（方式B）── 複数ノードで証明を蓄積可能にするための設計課題

作成日: 2026-07-29 / 目的: 「現行のNova実装（`nova_poc/`）は複数ノードの証明を蓄積できるか」という問いに対し、
`week20/11`で「回路ロジックは可能だが、実際のノード間受け渡しは未実装」と回答した内容を掘り下げ、
**Sonobe自体が何を提供していて何を提供していないか**をコード（`nova_poc/sonobe/folding-schemes/`）から
確認した上で、**実現に必要な設計課題と対処案**を整理する。**設計文書であり、実装はまだ行っていない。**

---

## 0. 結論（先に）

**Sonobeのライブラリ自体は「複数の当事者(parties)間でIVC状態を受け渡して継続する」ことを明示的に
想定して設計されている**（`FoldingScheme::from_ivc_proof`のdocコメントに明記、§2）。つまり
「ノード間で証明を渡して蓄積を続ける」という**核となる仕組み自体はSonobeにすでに存在する**。
本プロジェクトの`nova_poc/`コードがこれを使っていないだけ、というのがまず重要な事実。

ただし、それだけでは足りない。実際に複数ノードで安全に運用するには、以下**6つの課題**を追加で
解く必要がある（詳細は§3以降）。

| # | 課題 | Sonobe側の現状 | 本プロジェクト側で必要な作業 |
|---|---|---|---|
| ① | 状態の転送（誰から誰へ渡すか） | `ivc_proof()`/`from_ivc_proof()`/`CanonicalSerialize`は**用意済み** | 転送経路(チェーン/blob)の実装・サイズ実測（未着手） |
| ② | 受け取った状態を信用する前の検証 | `from_ivc_proof`自体は正当性チェックを**しない** | 「受信→verify→from_ivc_proof」の運用ルールと実装 |
| ③ | 入力真正性（誰の観測データか） | 関与しない（フレームワーク外） | 署名検証・freshnessを回路に追加（未着手・方式Aと同じ穴） |
| ④ | 二重計上防止・メンバーシップ | 関与しない | z構造の拡張（Merkle/ビットマップ）が必要（未着手） |
| ⑤ | 並行更新の衝突（誰が次を畳むか） | **Novaは多重インスタンス折り込みを設計上サポートしない**（後述） | 排他制御 or 順序決定の仕組みが必須（week20/04の前提を修正要） |
| ⑥ | 端末のストレージ／転送コスト | 走行witnessはIVCProofに内包（サイズ大） | 実サイズ計測・端末での保持可否の検証（未着手） |

---

## 1. 前提の再確認

`week20/11`で回答した通り、現状の`nova_poc/uav_chain_step.rs`・`nova_poc/nova-mobile/`は**1プロセス内で
同じ`Nova<...>`インスタンスに複数の観測を順番に`prove_step`しているだけ**で、別々のノード（別プロセス・
別デバイス）が実際に証明を受け渡すコードは一度も書かれていない。本ドキュメントはこれを可能にするための
設計課題を整理する。

---

## 2. 重要な発見: Sonobe自体は「マルチパーティ継続」を想定して設計されている

`nova_poc/sonobe/folding-schemes/src/lib.rs`の`FoldingScheme`トレイト定義を確認したところ、
以下のメソッドが**まさにこの用途のために**用意されていた（本プロジェクトの`nova_poc/`コードは
これを一度も呼んでいない＝未使用の既存機能）。

```rust
// folding-schemes/src/lib.rs:213
/// constructs the FoldingScheme instance from the given IVCProof, ProverParams, VerifierParams
/// and PoseidonConfig.
/// This method is useful for when the IVCProof is sent between different parties, so that they
/// can continue iterating the IVC from the received IVCProof.
fn from_ivc_proof(
    ivc_proof: Self::IVCProof,
    fcircuit_params: FC::Params,
    params: (Self::ProverParam, Self::VerifierParam),
) -> Result<Self, Error>;
```

さらに`IVCProof`構造体（`folding-schemes/src/folding/nova/mod.rs:426`）自体が
`#[derive(CanonicalSerialize, CanonicalDeserialize)]`（arkworksのバイト列シリアライズ）を持っており、
中身は継続に必要な状態を過不足なく含む:

```rust
pub struct IVCProof<C1, C2> {
    pub i: C1::ScalarField,               // 現在のステップ数
    pub z_0: Vec<C1::ScalarField>,        // 初期状態
    pub z_i: Vec<C1::ScalarField>,        // 現在の公開状態
    pub W_i: Witness<C1>,   pub U_i: CommittedInstance<C1>,   // 走行インスタンス(witness込み)
    pub w_i: Witness<C1>,   pub u_i: CommittedInstance<C1>,   // 直近インスタンス(witness込み)
    pub cf_W_i: CycleFoldWitness<C2>,     pub cf_U_i: CycleFoldCommittedInstance<C2>, // CycleFold側
}
```

**つまり理論上の手順は次の4行で書ける**（Sonobeが既に提供する部品だけで足りる）:

```rust
// ノードA側
let bytes = ivc_proof_a.serialize_compressed(&mut buf)?;   // 送信用にシリアライズ

// ノードB側
let ivc_proof = IVCProof::deserialize_compressed(&bytes[..])?;
let mut fs_b = N::from_ivc_proof(ivc_proof, (), (prover_params, verifier_params))?;
fs_b.prove_step(rng, my_observation, None)?;                // 自分の観測を畳んで継続
```

**§2の結論**: 「別ノードが証明を受け取って継続する」という核心部分は**Sonobeの標準APIで実現可能**であり、
新規のクリプト設計は不要。ここは`week20/04`§5.1が「省メモリ代替」として温存していた設計の**実装面での
裏付け**になる。残る課題は§3以降の「運用として安全に成立させる」部分。

---

## 3. 課題① 状態の転送設計（誰から誰へ、どの経路で渡すか）

`from_ivc_proof`はAPIとして存在するが、**転送そのもの（チェーンへの記録・blob保存・取得）は本プロジェクトが
自前で作る必要がある**。`week20/04`§5.2の設計（方式Aと共通の許可型チェーン利用）をそのまま踏襲できる:

- **オンチェーンに置くもの**: 公開状態`z_i`＋走行累積（`IVCProof`全体）のハッシュ＋取得先。
- **本体（`IVCProof`のシリアライズ結果）の置き場**: witness込みで**数十KB〜MB級**（`week20/04`§5.1で
  見積もっていた通り）と推定されるが、**実際に`serialized_size()`で計測したことは一度もない**。
  まず着手すべきは「1ステップ分の`IVCProof`を実際にシリアライズしてバイト数を測る」という最小実験。
- **経路**: `week20/04`と同じく、許可型チェーン（`contracts/besu-qbft`, QBFT合意）のストレージ or
  併設blob置き場＋ハッシュ結合。パブリックチェーンのガス制約が無いため許可型なら現実的だが、
  スマホ側の**アップロード/ダウンロード帯域**は未検証（`week20/09`のPixel 8実測は全てローカル完結の
  ベンチマークで、ネットワーク転送を含む実測は一度も行っていない）。

---

## 4. 課題② 受け取った状態を信用する前の検証ステップ

`from_ivc_proof`の実装（`folding-schemes/src/folding/nova/mod.rs:884`）を読むと、渡された`IVCProof`の
フィールドをそのまま`Self`（`Nova`インスタンス）に詰め直すだけで、**正当性チェックは一切行わない**
（`verify()`は独立したメソッドとして別に存在する）。

- **含意**: 悪意あるノードが改ざんした`IVCProof`を渡してきても、`from_ivc_proof`自体はエラーにならず
  「継続できてしまう」。安全性は「その後の`prove_step`が失敗する」か「最終的な`verify()`で弾かれる」
  ことに委ねられており、**受信直後に明示的に`N::verify(vp, ivc_proof.clone())`を呼んで正当性を確認してから
  `from_ivc_proof`に進む、という運用ルールをアプリケーション側で必ず実装する必要がある**（ライブラリは
  強制してくれない）。
- **未検証事項**: 改ざんされた`IVCProof`（例: `z_i`だけ書き換えて`W_i`/`U_i`はそのまま）を実際に
  `from_ivc_proof`→`prove_step`に通した場合に、具体的にどの段階でエラーになるか（`prove_step`内の
  NIFS証明生成で失敗するのか、それとも一見成功して後の`verify()`でしか気づけないのか）は
  **`week20/08`の否定系テストでは検証していない**（あちらは「完成した`IVCProof`のz_iを直接書き換えて
  `verify()`にかける」ケースのみ検証済み。「継続の入口＝`from_ivc_proof`」を狙った改ざんは未検証）。
  実装時に最初に潰すべき検証項目。

---

## 5. 課題③ 入力真正性（誰の観測データか）

現行の`ChainStepCircuit`（`nova_poc/nova-mobile/src/lib.rs`・`nova_poc/uav_chain_step.rs`）は
`ObservationInput`/`external_inputs`を**無条件に信頼して受け取る**。単一ノードのシミュレーションでは
問題にならないが、複数の別ノードが実際にデータを持ち寄る場合、「このステップの観測は本当に登録済みの
ノードXが出したものか」を回路内で強制する仕組みが無いと、誰でも好きな観測をでっち上げて畳める。

- これは`week20/04`§14(b)で挙げていた**方式A/B共通の未実装項目**（R3: ドローン署名検証・freshness、
  `circuits/uav_witness_attestation.circom`相当）そのもの。単一ノードPoCでは問題が顕在化しなかっただけで、
  マルチノード化する時点で必ず対応が必要になる。
- **対処案**: `ExternalInputs`に署名・公開鍵（またはその一部）・タイムスタンプを追加し、回路内で
  Poseidon/EdDSA等の検証を`generate_step_constraints`に足し込む。circomのuav_witness_attestation
  （署名+freshnessで約11.8k制約）に相当するロジックをarkworksのR1CSに移植する作業になる。
- **性能への影響（未計測）**: `week20/08`の実測（1ステップ130〜280ms）は署名検証を含まない軽量な
  ステップ回路での数字。署名検証を追加すると1ステップあたりの証明生成コストが増える。circom版が
  「軽い整合判定(649制約)」と「重い署名+freshness(11.8k制約)」を別回路に分けているのと同様、
  Nova側でも**署名検証を毎ステップ行うか、末端ノード側でcircom等の軽量証明として済ませてNova回路には
  結果だけを持ち込むか**の設計判断が要る（後者は方式Aの「スマホは軽いwitness証明だけ・重い再帰はラズパイ」
  という役割分担、`week20/04`§6と同じ発想）。

---

## 6. 課題④ 二重計上防止・メンバーシップ（Sybil対策）

現行の状態`z = (drone_id, time_bucket, consistent_count, suspicious_count, step_count)`には、
**「どのノードが何回計上されたか」を追跡する項目が存在しない**。`drone_id`/`time_bucket`は
「同じドローン放送についての判定である」ことは保証するが、「同じノードが2回登録されて
`consistent_count`を水増しする」ことを防ぐ仕組みは無い。

- `NEXT_STEPS.md`のStep C（「membership（登録端末のMerkle）＋二重計上防止」）はこの課題に対応する
  計画だが、**方式A（gnark, `aggregator/cmd/chainpoc`）向けにしか設計されておらず⬜未着手**。
  Nova側には対応する設計すら存在しない。
- **対処案（方式Aの設計を参考にした移植案）**:
  1. `state_len`を5→6以上に拡張し、`z`に**参加済みノード集合のコミットメント**（例:
     included済みビットマップのハッシュ、またはMerkle風の累積）を追加する。
  2. `ExternalInputs`にノードの識別子（登録Merkleに対する自分の葉＋non-membership証明、または
     ビットマップの該当ビット未セット証明）を追加し、`generate_step_constraints`内で
     「このノードがまだ未計上であること」を制約として強制、計上後は集合を更新する。
  3. 登録ノード数の上限（ビットマップ方式ならサイズ固定・Merkle方式なら深さ固定）を設計時に決める
     必要がある。
- **性能への影響（未計測）**: `state_len`の拡張・membership証明の追加は制約数を増やし、
  `week20/08`の実測（130〜280ms/step）より遅くなる。どの程度かは実装して測るまで分からない。

---

## 7. 課題⑤ 並行更新の衝突（誰が次を畳むか）── week20/04の前提とSonobe実装の食い違い

`week20/04`§5.4は「複数ノードが並行して累積を伸ばしても、**可換なfold**にしておけば後から1本に合流できる」
という前提を置いていた。しかし今回`prove_step`の実装（`folding-schemes/src/folding/nova/mod.rs:669-701`）を
確認したところ、次のガードが存在する:

```rust
fn prove_step(
    &mut self,
    ...
    // Nova does not support multi-instances folding (by design)
    _other_instances: Option<Self::MultiCommittedInstanceWithWitness>,
) -> Result<(), Error> {
    ...
    // Nova does not support (by design) multi-instances folding
    if _other_instances.is_some() {
        return Err(Error::NoMultiInstances);
    }
    ...
```

**Sonobeの`Nova`実装は設計上、複数インスタンスの同時折り込み（multi-instance folding）をサポートしない**
（`other_instances`に何か渡すと即エラー）。つまりNovaは**厳密に1本の逐次チェーン**であり、2つのノードが
それぞれ独立に`acc_{i-1}`から枝分かれして`acc_i^A`・`acc_i^B`を作ってしまった場合、**それを1本に「合流」
させる標準的な仕組みはNova自体には無い**（`week20/04`§5.4が期待していた「可換foldでの後合流」は、
少なくとも素のNovaでは前提が成立しない可能性が高い。HyperNova/ProtoGalaxyなど同じSonobe内の
他方式ではmulti-instance折り込みに対応するAPIがある可能性があり、要調査だが本ドキュメント作成時点では
未確認）。

- **含意**: マルチノード運用では「誰がどの順番で`acc_{i-1}`を取得し`acc_i`を書き戻すか」を**厳密に
  直列化（排他制御）する**必要がある。`week20/04`§5.2が触れていた「同時書き込みが競合しても
  チェーンの合意で1本に確定」という記述のうち、**「後から合流」の部分はNovaでは使えない**と読み替える
  必要がある（先着1本のみ有効、競合した側は自分の`acc_{i-1}`が古くなったので取り直して再試行、
  という単純な直列キューモデルにするしかない）。
- 許可型チェーンのトランザクション順序（QBFT合意）がこの直列化を天然に提供してくれる可能性はあるが、
  「acc取得→fold計算(数百ms)→書き戻し」の間に他ノードが割り込む競合ウィンドウをどう扱うかは
  未設計・未実装。

---

## 8. 課題⑥ 端末のストレージ・転送コスト

継続に必要な`IVCProof`は走行witness（`W_i`/`w_i`/`cf_W_i`）を丸ごと含むため、方式A（渡すのは
約200バイトのGroth16証明1個）と比べて**桁違いに大きい**。具体的なバイト数は未計測だが、
`week20/04`§5.1の見積もり（数十KB〜MB級）が妥当だとすると:

- スマホ自身が次のノードへ渡す・受け取る場合、**モバイル回線での転送コスト**が新たに発生する
  （`week20/09`の実機実測はすべてローカル完結で、ネットワーク越しの転送を含んでいない）。
- 端末が一時的に保持するメモリ・ストレージ量への影響も未検証。`week20/07`が方式Aを「不可」と
  判定した基準（ピークメモリ4GB級）とは別軸の懸念（1回あたりの転送データ量）であり、
  方式Bのメモリ優位性（約456MB, `week20/08`）がこの転送コストにそのまま当てはまるとは限らない。

---

## 9. 実装ロードマップ（優先度つき）

| 優先度 | 作業 | 目的 | 見積もりの根拠 |
|---|---|---|---|
| 1 | `IVCProof`の`serialize_compressed`実サイズ計測 | §3・§8の見積もりを実測値に置き換える | 数分でできる最小実験、着手コストが最も低い |
| 2 | 2プロセス間（同一マシン上でよい）で`ivc_proof()`→シリアライズ→`from_ivc_proof()`→`prove_step()`の疎通確認 | §2の理論をコードで実証 | Sonobeの既存APIのみで完結、新規暗号設計は不要 |
| 3 | 改ざんした`IVCProof`を`from_ivc_proof`に通すテスト（§4の否定系） | 「受信→verify必須」の運用ルールを裏付け・弱点の有無を確認 | 安全性の根幹、他の作業より先に潰すべき |
| 4 | 並行更新の直列化設計（§7） | Novaがmulti-instance非対応という制約を踏まえた運用モデルを決める | 許可型チェーンのトランザクション順序をどう使うかの設計判断が先に必要 |
| 5 | 入力真正性（署名+freshness）の回路組込み（§5） | 方式A/B共通の既知の穴を埋める | circomのuav_witness_attestationからの移植、性能再実測とセット |
| 6 | 二重計上防止・メンバーシップのz拡張（§6） | Step C相当をNovaに移植 | 方式A側のStep C自体もまだ⬜未着手のため、先に方式Aで設計を固めてから移植する方が手戻りが少ない可能性 |
| 7 | 実機でのネットワーク転送込みベンチマーク（§8） | モバイル運用の現実性を最終確認 | 上記1〜6が一定形になってから |

---

## 10. 未確認・要調査事項（正直な棚卸し）

- `IVCProof`の実際のシリアライズサイズ（バイト数）── 未計測。
- 改ざんされた`IVCProof`を`from_ivc_proof`→`prove_step`に通した際の失敗箇所 ── 未検証。
- HyperNova/ProtoGalaxy（同じSonobe内）がmulti-instance折り込みに対応しているか ── 未調査
  （Novaが非対応であることのみ確認済み、`folding-schemes/src/lib.rs`に`MultiFolding`トレイトの
  存在は確認したが中身は未調査）。
- 許可型チェーンのトランザクション順序が§7の直列化要件を実際に満たせるか ── 未検証（設計上の期待のみ）。
- モバイル回線でのIVCProof転送の実測（時間・失敗率） ── 未実施。

---

## 11. 参照

- `week20/11_Nova実装ライブラリ詳細_Sonobe.md` … 本ドキュメントの前提となるライブラリ詳細
- `week20/04_再帰ZKP_証明チェーン設計.md`§5, §6, §14 … マルチノード転送・役割分担・未実装項目の元設計
- `week20/08_Nova方式B_PoC実装結果.md` … 単一ノードでの実測（本ドキュメントの比較対象）
- `NEXT_STEPS.md`§3 … Step C（membership＋二重計上防止, 方式A向け・⬜未着手）
- Sonobeコード直接参照:
  - `nova_poc/sonobe/folding-schemes/src/lib.rs:190-219`（`FoldingScheme`トレイト定義）
  - `nova_poc/sonobe/folding-schemes/src/folding/nova/mod.rs:426-445`（`IVCProof`構造体）
  - `nova_poc/sonobe/folding-schemes/src/folding/nova/mod.rs:669-701`（`prove_step`のmulti-instanceガード）
  - `nova_poc/sonobe/folding-schemes/src/folding/nova/mod.rs:884-934`（`from_ivc_proof`実装）
