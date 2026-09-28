# Nova（方式B・Folding）PoC ── 設計と実装結果

作成日: 2026-07-23 / 目的: `week20/04` §0・§5・§9 で「省メモリ代替」として温存していた**方式B（Nova/Folding）**を
実際に実装し、方式A（gnark再帰, `week20/06`）と同じRSSI整合ステップ回路を作って**実測で比較**する。
関連: `week20/04`（設計）、`week20/06`（方式A実装結果）、`week20/07`（gnark版のスマホ実行可否調査）。

**結論を先に**: **成功**。Sonobe（`privacy-ethereum/sonobe`, Rust, BN254/Grumpkin曲線サイクル）でNova+CycleFold
のIVCを実装し、方式Aと同じ3ステップ・同じ検知結果（consistent 1→2→2、suspicious 0→0→1）を再現。
**方式Bはメモリ・時間とも方式Aより1桁以上軽い**（ピークメモリ 4GB→456MB、1ステップの証明生成 7〜9秒→
130〜280ミリ秒）。実装過程でRustエコシステム側の破壊的なバージョン移行（arkworks 0.5.0→0.6.0が
ちょうど今週起きていた）に巻き込まれ、依存解決だけで16回のビルド試行を要した。加えて、ライブラリの
比較API選択を誤ったことによる**論理バグ**（回路は正しくコンパイル・証明できるのに判定結果が常に false
になる）も踏んだ。両方とも原因と対処を記録する。

---

## 1. 設計

### 1.1 なぜSonobeか

`week20/04` の時点では「Nova/Sonobe」と並記していたが、実装にあたり現在(2026-07時点)のRust folding
schemesライブラリの状況を調査した。

| 候補 | 最終更新 | 判断 |
|---|---|---|
| `nalinbhardwaj/Nova-Scotia`（circom→Nova変換ミドルウェア） | 2024-03-01（2年以上前） | 見送り。事実上メンテ停止 |
| `microsoft/Nova`（原論文の参照実装） | 2026-06-19 | 現役だが低レベルAPI |
| `lurk-lang/arecibo`（Novaのfork） | 2025-03-03 | 見送り |
| **`privacy-ethereum/sonobe`（旧PSE, folding-schemes crate）** | **2026-07-19（4日前）** | **採用**。Nova/HyperNova/ProtoGalaxy＋CycleFold、EVM verifier出力(`solidity-verifiers`)まで揃い、最も活発 |

Sonobeは`FCircuit`トレイトを実装する形でステップ回路を書く（arkworksのR1CS制約系で直接記述。
circom/Noirの実験的フロントエンドもあるが「計算量とオーバーヘッドあり」と明記されているため、
方式Aと同じく**素のarkworks(gnarkのfrontend.APIに相当)で直接実装**する方針にした）。

### 1.2 ステップ回路の設計（方式Aとの対応）

`aggregator/cmd/chainpoc`（方式A, week20/06）と**同じ関係**をNova/SonobeのFCircuitとして実装。

```rust
impl<F: PrimeField> FCircuit<F> for ChainStepCircuit<F> {
    type ExternalInputs = [F; 7];   // drone_lat/lon/alt, target_lat/lon/alt, measured_range_cm（秘匿）
    fn state_len(&self) -> usize { 5 } // z = (drone_id, time_bucket, consistent_count, suspicious_count, step_count)

    fn generate_step_constraints(&self, cs, i, z_i, external_inputs) -> Result<Vec<FpVar<F>>> {
        let ok = rssi_consistency_ok(...);       // week20/06 §1.4と同じ相対許容帯判定
        Ok(vec![
            z_i[0].clone(),                       // drone_id はそのまま引き継ぐ
            z_i[1].clone(),                       // time_bucket も同様
            &z_i[2] + &ok,                         // consistent_count += ok
            &z_i[3] + (1 - &ok),                   // suspicious_count += (1-ok)
            &z_i[4] + 1,                            // step_count += 1
        ])
    }
}
```

RSSI整合計算（`rssi_consistency_ok`/`abs_diff`）は`circuits/remoteid_consistency_rel.circom`と
同じ係数・同じロジック（week20/06 §1.4の対応表と同一）。

### 1.3 方式Aとの設計上の違い（実装して初めて明確になった点）

- **z_iの継続性はNovaフレームワーク自身が保証する**。方式A(gnark)では「前の証明を再帰検証して取り出した
  drone_id/time_bucketが新しい主張と一致するか」を回路内で自分でassertする必要があった
  （`week20/06` の`ChainCircuit.Define()`内の`api.AssertIsEqual(c.DroneID, prevDroneID)`）。
  Novaでは`z_i`はIVCエンジンが管理する**真の状態**であって参加者が毎回「主張」し直すものではないため、
  ステップ関数はz_iを単に受け取って使うだけでよい。この一致チェックのassertが**不要**になる。
- **自己再帰の「箱サイズ問題」が存在しない**（`week20/06` §1.2・§1.3で見つけた、方式A特有の落とし穴）。
  Novaは「前の証明を検証する」のではなく「前のインスタンスを折り畳む」ため、GenesisCircuit相当の
  特別な起点回路も、段ごとに回路を作り直す必要もない。**同じ1つのFCircuitをそのまま何ステップでも
  使い回せる**。これは方式Bの構造的な利点として実装で確認できた。

---

## 2. ハマった所①: arkworksエコシステムの破壊的バージョン移行（依存解決だけで16ビルド）

### 2.1 何が起きたか

Sonobeの`Cargo.toml`は`ark-groth16`を特定のgitコミット(`b3b4a15`, 2025-08)に固定する一方、
`ark-ff`等の基盤crateは**rev無指定でHEAD追従**にしていた。ところが**ちょうど2026年7月中に
arkworks本体（algebra/std/snark/crypto-primitives/r1cs-std等）が0.5.0→0.6.0へ一斉に上がり**、
Sonobeが要求する`^0.5.0`と噛み合わなくなっていた（Sonobe自体は4日前に更新されているが、
この特定の依存関係の綻びには追随していなかったとみられる）。

症状: `ark-crypto-primitives`が「パッチ済みのフォーク版」と「パッチされなかった素のarkworks版
（HEAD=0.6.0）」の**2つのバージョンが同時にコンパイルされ**、`ark_ff::SmallFp`（0.6.0で追加された型）が
見つからずビルド失敗。

### 2.2 やったこと（結果的に不要だった回り道も含めて記録）

1. **v0.5.0タグへのrev固定**（`[patch.crates-io]`にrevを追加）→ 一部解決したが、`ark-groth16`が
   crates.io経由でなく**直接gitで**`arkworks-rs/{crypto-primitives,r1cs-std}.git`を参照しており、
   `[patch.crates-io]`では差し替わらないことが判明。
2. **`.git`サフィックス付きURLへの個別パッチ**（`[patch."https://.../X.git"]`）を追加 →
   一部は成功したが、一部（`ark-relations`, `ark-bn254`等）は**「patches must point to different sources」
   エラー**で拒否された。試行錯誤の結果、**フォーク先が別リポジトリのもの（crypto-primitives, r1cs-std）は
   `.git`個別パッチが必要**だが、**同一リポジトリのrev違いを解決するだけのもの（algebra, snark, std,
   poly-commit）は`[patch.crates-io]`だけで十分**（`.git`個別パッチを足すと逆に「自分自身へのパッチ」と
   見なされてエラーになる）という**非対称なルール**があることが分かった。ただしこの切り分けも
   Cargoのpatch検証順序に依存する部分があり、完全な一般則としては確信が持てていない。
3. **最終的に採用した方針（0.6.0への完全移行）**: パッチ機構と格闘し続けるより、**crates.ioに
   正式公開済みの0.6.0系にすべて揃える**方が筋が良いと判断（ユーザ判断で選択）。確認したところ
   `ark-groth16`自体は2026-07-10に0.6.0対応が`master`へマージ済みで、`ark-groth16 0.6.0`を含む
   全arkworksファミリがcrates.ioに公開済みだった。**`[patch]`セクションを全廃し、
   `[workspace.dependencies]`のバージョン指定を`^0.5.0`→`^0.6.0`に置換するだけ**で、
   依存解決の矛盾は完全に消えた。

### 2.3 教訓

- **rev無指定（HEAD追従）のgit依存は、エコシステムが動いている最中に致命的な非決定性を生む**。
  Sonobeのように意欲的にNova/HyperNova/EVM連携まで抱える活発なリポジトリほど、上流の破壊的変更に
  巻き込まれやすい。
- Cargoの`[patch]`は「クレート名」単位ではなく**「差し替え元ソースの正確な文字列」単位**で効く。
  crates.io経由の依存と、深い依存が直接gitで参照している依存は**別物として扱われる**ため、
  後者を捕まえるには`.git`サフィックスの有無まで含めて正確に一致させる個別`[patch."URL"]`が要る。
- 依存が**フォーク**（差し替え先が別リポジトリ）なのか、**単なるバージョン不整合**（差し替え先が
  同じリポジトリの別rev）なのかで、必要なpatch戦略が変わる。後者は上位互換のバージョンが
  crates.ioに出た時点で**パッチ自体が不要になる**（今回のケース）。

---

## 3. ハマった所②: フォーク独自APIとの非互換（`joint_scalar_mul_be`）

0.6.0へ揃えた後、`folding-schemes`自体のソースコードでコンパイルエラー。原因は、Sonobeが元々
依存していた`ark-r1cs-std`のフォーク（`flyingnobita/r1cs-std_yelhousni`, "perf/sw-updated"ブランチ）が
独自に追加していた**`joint_scalar_mul_be`**（2点を同時にスカラー倍する最適化、Shamirのトリック相当）
というメソッドを、`commitment/pedersen.rs`と`commitment/ipa.rs`が使っていたが、公式0.6.0の
`ark-r1cs-std`にはこの最適化が未マージだった。

**対処**: 機能的に等価な`scalar_mul_le`の2回呼び出し+加算に置換（6箇所）。正しさは同一、
効率のみ僅かに劣る（Pedersen/IPAコミットメントの検証ゲート部分のみへの影響。回路全体で見れば
限定的）。詳細は`nova_poc/sonobe/folding-schemes/src/commitment/{pedersen,ipa}.rs`のコメント参照。

---

## 4. ハマった所③: 比較APIの選択ミスによる論理バグ（値は正しいのに判定結果が常にfalse）

ビルドが通った後の**最初の実行結果がすべて誤り**だった: 整合な観測(本来ok=1)なのに
`consistent_count`が育たず`suspicious_count`ばかり増える。

### 4.1 デバッグの経緯

回路内の中間値を`eprintln!`と`.value()`（witnessの実値取得）で直接確認したところ、
`claimed_dist_sq`・`lower_sq`・`claimed_scaled`・`upper_sq`は**すべて数学的に正しい値**
（`week20/06`のgnark版と完全一致）だったにもかかわらず、`lower_sq <= claimed_scaled`
（`ge_lower`）と`claimed_scaled <= upper_sq`（`le_upper`）が**両方とも`false`**になっていた。
値は合っているのに大小比較の結果だけが誤る、という切り分けに至った。

原因として使っていたのは、`FpVar`を`to_bits_be()`でビット分解し、`[Boolean<F>]`の
`CmpGadget`（辞書式比較のblanket実装）で比較する方法（`week20/06`のgnark版`cmp.IsLessOrEqual`と
同じ発想）。ビット長は両辺とも254bitで一致しており、`is_constant`もfalse（定数畳み込みの影響でもない）
ことを確認したが、それでも結果が誤っていた。

### 4.2 対処

`ark-r1cs-std`には**`FpVar`専用の比較API**（`fields/fp/cmp.rs`の`is_cmp`/`enforce_cmp`、
テスト付きで動作保証されている）が別に用意されていた。ビット分解+辞書式比較という自作の経路を捨て、
この専用APIに置き換えたところ**即座に正しい結果**になった。

```rust
// 誤り（値は正しいのに比較結果が常にfalseになる）
let ge_lower = lower_sq.to_bits_be()?.as_slice().is_le(claimed_scaled.to_bits_be()?.as_slice())?;

// 修正後（正しく動く）
let ge_lower = lower_sq.is_cmp(&claimed_scaled, Ordering::Less, true)?; // "<="（Less + 等号も見る）
```

`is_cmp`は「両辺が `(p-1)/2` 以下」という制約があるが、今回の値（最大でも2^80程度）は
BN254のフィールド位数（2^254程度）よりはるかに小さいため問題にならない。

**根本原因は特定できていない**（`[Boolean<F>]`のCmpGadget blanket実装のロジック自体を手でトレースした
限りでは正しく見えるため、この特定のバージョン/曲線サイクルの組み合わせにおける実装上の何らかの不具合、
または筆者の見落としの可能性が残る）。ただし実務上の教訓ははっきりしている:
**ライブラリに「専用・テスト付きのAPI」が存在する場合はそちらを優先し、自作の汎用実装
（ビット分解+辞書式比較）は最終手段にすべき**。今回もし`fields/fp/cmp.rs`の存在に最初から
気づいていれば、この論理バグは踏まずに済んだ。

---

## 5. 実行結果（M2 Mac、Sonobe/Nova+CycleFold, BN254/Grumpkin）

### 5.1 正常系・否定系

| step | 内容 | prove_step | 結果 |
|---|---|---:|---|
| 1 | 整合な観測(距離≈341cm, measured=341cm) → ok=1 | 135ms | z=(…, consistent=1, suspicious=0, step=1) |
| 2 | 整合な観測 → ok=1 | 151ms | z=(…, consistent=2, suspicious=0, step=2) |
| 3 | なりすまし観測(measured=5000cmだが幾何距離≈341cm) → ok=0 | 281ms | z=(…, consistent=2, suspicious=1, step=3) |

`consistent_count`・`suspicious_count`とも`week20/06`のgnark版と**完全に同じ推移**（1→2→2 /
0→0→1）を再現。IVC証明の検証は28msで成功。**否定系**: 検証直前に`ivc_proof.z_i[2]`
（consistent_count）を+1改ざんして`N::verify`にかけたところ、`IVCVerificationFail`で
期待通り拒否された（`z_i`はハッシュ経由で証明に束縛されているため、詳細は`folding-schemes`の
`verify()`実装 — `U_i.hash(&sponge, i, z_0, z_i)`が`u_i.x[0]`と一致するかを検証、が担保する）。

なお方式Aで実施した「time_bucket食い違い」「なりすまし観測を整合と偽る」といった否定系は、
**Novaのアーキテクチャ上そもそも成立しない**（§1.3の通り、z_iは参加者が"主張"するものではなく
IVCエンジンが管理する真の状態のため、方式Aのような「偽の主張をassertではじく」という構図自体が
存在しない）。改ざん検知は「完成したIVC証明を後から書き換えて検証にかける」という一点に集約される。

### 5.2 方式A(gnark)との定量比較 ── 最も重要な発見

| 指標 | 方式A（gnark, week20/06） | 方式B（Nova/Sonobe, 本PoC） | 比率 |
|---|---:|---:|---:|
| セットアップ（1回きり） | 約2〜3分/回路（chainA/chainB個別に） | **625ms**（preprocess、回路は1つだけ） | **200〜300倍高速** |
| 1ステップの証明生成 | 7〜9秒 | **130〜280ミリ秒** | **約30〜50倍高速** |
| 検証 | 数ミリ秒 | 28ミリ秒 | 同程度 |
| ピークメモリ（プロセス全体） | 約4.04GB（`week20/07`実測） | **約456MB** | **約9倍少ない** |

`week20/04`が方式Bを「省メモリ・軽量な代替」と位置づけていた**仮説が、実測で強く裏付けられた**。
gnark（方式A）は「同一曲線上での自己再帰」という設計ゆえにemulated算術のコストが非常に大きい
（`week20/07` §3で分析済み）のに対し、Nova（方式B）は折り畳み（accumulate）が本質的に軽い計算
であるため、この差が生まれている。

---

## 6. スマホ実行可否への示唆（`week20/07`の再評価）

`week20/07`はgnark版(方式A)について「1ステップあたり約4GB・7〜9秒はスマホでは非現実的」と結論した。
方式Bの実測（1ステップ130〜280ms・プロセス全体で456MB）は、**その結論を覆すものではないが、
「方式Bなら現実的な射程に入ってくる」ことを示す**:

- メモリ: 456MBは（`week20/07`で引用した）gnark WASMベンチマークの「Groth16にはWASM初期メモリ2GBが
  必須」という制約と比べても、**桁が違って有利**。ただしこれは今回の**M2 Mac・ネイティブ実行**での
  数字であり、スマホ実機・Rustのモバイル向けビルド（iOS/Android向けクロスコンパイル）でどうなるかは
  **未検証**（`nova-scotia`や`uniffi`等のRust→モバイルバインディング経由になる見込みだが、
  gomobile同様の追加オーバーヘッドが乗る可能性がある）。
- 時間: 130〜280msはM2 Mac（8コア）でのマルチスレッド実行の数字。スマホのシングル/デュアルコア
  実効性能を考えても、秒未満〜数秒のオーダーには収まりそうで、gnark版の「7〜9秒」よりは
  はるかに現実的。
- **結論**: 方式Bのスマホ実行可能性は**方式Aよりも見込みがある**。ただし実機検証（Rustのモバイル
  クロスコンパイル・実機ベンチマーク）は今回のPoCの範囲外であり、次の調査候補として記録する。

---

## 7. ファイル構成

```
nova_poc/
├── uav_chain_step.rs      ★実装したステップ回路(FCircuit)+実行ドライバ。追跡対象
└── sonobe/                 privacy-ethereum/sonobe のvendored clone（.gitignore対象・再生成可能）
    ├── Cargo.toml           workspace定義（membersをfolding-schemesのみに縮小、0.6.0系に統一）
    ├── folding-schemes/     Nova/HyperNova/ProtoGalaxy実装本体
    │   └── src/commitment/{pedersen,ipa}.rs  joint_scalar_mul_be→scalar_mul_le置換パッチ（§3）
    └── examples/uav_chain_step.rs  上記uav_chain_step.rsのコピー（cargo run --example用）
```

**再現手順**:
```bash
# 1. Sonobeを取得(vendored clone。既にnova_poc/sonobe/にあれば不要)
git clone --depth 1 https://github.com/privacy-ethereum/sonobe.git nova_poc/sonobe
# 2. Cargo.tomlの[workspace]membersをfolding-schemesのみに、[workspace.dependencies]を0.6.0系に変更(本ファイル§2.2参照)
# 3. commitment/{pedersen,ipa}.rsのjoint_scalar_mul_be呼び出しをscalar_mul_le2回+加算に置換(§3参照)
# 4. examples/uav_chain_step.rs に nova_poc/uav_chain_step.rs をコピー + folding-schemes/Cargo.tomlに[[example]]登録
cd nova_poc/sonobe
cargo run --release --example uav_chain_step -p folding-schemes
```

---

## 8. 参照

- 実装: `nova_poc/uav_chain_step.rs`
- Sonobe: https://github.com/privacy-ethereum/sonobe
- 設計: `week20/04_再帰ZKP_証明チェーン設計.md` §0, §5, §9
- 比較対象（方式A）: `week20/06_再帰チェーンPoC_StepAB実装結果.md`
- スマホ可否調査（方式A）: `week20/07_モバイル実行可否_gnarkチェーン回路の実測.md`
