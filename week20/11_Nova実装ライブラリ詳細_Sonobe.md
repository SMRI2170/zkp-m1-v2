# Nova（方式B）── 使用ライブラリ・リポジトリの詳細

作成日: 2026-07-29 / 目的: `week20/08`（Nova方式B PoC実装結果）・`week20/09`（モバイル実装）に
分散している「実際に何を使ってNovaを実装したか」という情報を1箇所にまとめ、ライブラリ選定の経緯・
構成・依存関係・自作コードの範囲を詳しく記録する。**新しい実装や調査はしていない**（既存2ファイルの
内容を整理・詳細化したドキュメント）。

---

## 1. 結論（一言）

**Nova本体のライブラリとして [`Sonobe`](https://github.com/privacy-scaling-explorations/sonobe)
（Rust製、`folding-schemes` crate）を採用し、`nova_poc/sonobe/` に vendored clone（gitignore対象、
再生成可能）として置いている。** その上に、本プロジェクト独自のステップ回路（RSSI整合判定）と
モバイル向けUniFFIラッパーを自作した（`nova_poc/uav_chain_step.rs`・`nova_poc/nova-mobile/`、
どちらも追跡対象＝Git管理下）。「Nova」は使った折り込み(folding)方式の**名前**（論文名）であり、
ライブラリそのものの名前ではない点に注意（§2）。

---

## 2. 用語整理：「Nova」とは何で、「Sonobe」とは何か

- **Nova**: Kothapalli, Setty, Tzialla による2021年の論文
  [*Nova: Recursive Zero-Knowledge Arguments from Folding Schemes*](https://eprint.iacr.org/2021/370.pdf)
  で提案された **folding scheme**（IVC構成法）の名前。gnarkの「再帰検証」のように前の証明を回路内で
  検証するのではなく、前のインスタンスと新しいインスタンスを1つに**折り畳む(fold)**ことでIVCを実現する
  （詳細は`week20/04`§9・`week20/08`§1.3）。Novaは方式の名前であって、特定の実装コードを指さない。
- **Sonobe**: そのNova（および関連するHyperNova・ProtoGalaxy・CycleFold）を実装した**Rustライブラリ**。
  0xPARCとPSE（Privacy & Scaling Explorations, Ethereum Foundation系チーム）が共同開発。
  本プロジェクトが実際に使ったのはこれ。
- 本プロジェクトの文書内で「Nova」「Nova/Sonobe」「方式B」はほぼ同義で使っているが、厳密には
  「Sonobeというライブラリで、Novaという折り込み方式を使った」という関係。

---

## 3. リポジトリ情報

| 項目 | 内容 |
|---|---|
| リポジトリ | Sonobe（`folding-schemes` crateを含むワークスペース） |
| URL（Cargo.tomlの`workspace.package.repository`） | `https://github.com/privacy-scaling-explorations/sonobe/` |
| URL（README・vendored clone時に実際に使ったURL、`week20/08`§7・`week20/09`§6） | `https://github.com/privacy-ethereum/sonobe.git` |
| 開発元 | 0xPARC + PSE（Privacy & Scaling Explorations） |
| ライセンス | MIT（`nova_poc/sonobe/LICENSE`） |
| 採用時の最終更新 | 2026-07-19（クローン時点で4日前）── 4候補中もっとも活発（比較は§4） |
| 本プロジェクトでの配置 | `nova_poc/sonobe/`（vendored clone、`.gitignore:88`で除外・再生成可能） |
| 取得済みコミット | `git clone --depth 1` の浅いクローン（特定コミットへのpin無し。再現手順を実行した時点のHEADに依存する点は再現性上の注意点） |

**注意（リポジトリURLの表記ゆれ）**: Sonobe自身の`Cargo.toml`のメタデータ上は
`privacy-scaling-explorations/sonobe` を指しているが、実際に`git clone`で使ったURL・READMEの
バッジ/注記は`privacy-ethereum/sonobe`になっている。両方とも解決してSonobeの同じプロジェクトに
辿り着く（PSE＝Privacy & Scaling ExplorationsがGitHub組織名を`privacy-ethereum`へ改称した過渡期に
あたっているとみられる）。どちらのURLでも`git clone`は成功することを確認済み。今後の再現時に
リンク切れが起きた場合はまずこの組織名の違いを疑うこと。

---

## 4. なぜSonobeを選んだか（`week20/08`§1.1の再掲・詳細化）

`week20/04`の設計時点では「Nova/Sonobe」と並記するだけで具体的な実装ライブラリまでは
確定していなかった。`week20/08`の実装着手時に、2026年7月時点でのRust folding schemesライブラリの
状況を調査し、以下の4候補を比較した。

| 候補 | 実体 | 最終更新 | 判断 |
|---|---|---|---|
| `nalinbhardwaj/Nova-Scotia` | circom回路→Nova変換ミドルウェア（Microsoft/Novaの上に構築） | 2024-03-01（2年以上前） | 見送り。事実上メンテ停止 |
| `microsoft/Nova` | Nova原論文の著者による参照実装 | 2026-06-19 | 現役だが低レベルAPI（folding schemeそのものだけで、HyperNova/ProtoGalaxyやEVM verifier出力等の周辺機能がない） |
| `lurk-lang/arecibo` | `microsoft/Nova`のfork（Lurk言語向けに拡張） | 2025-03-03 | 見送り |
| **`privacy-scaling-explorations/sonobe`** | **Nova/HyperNova/ProtoGalaxy＋CycleFold統合、EVM verifier出力(`solidity-verifiers`)込み** | **2026-07-19（4日前）** | **採用** |

選定理由:
1. **もっとも活発**（比較時点で4日前更新）。
2. **Nova単体でなくCycleFold（曲線サイクルによる折り込み）まで実装済み** — BN254で最終的に
   EVM verifierを出せる設計であり、`week20/04`で確定している「BN254/EVM着地」の方針と整合する。
3. **`solidity-verifiers`crateでオンチェーン検証コントラクトの出力まで見据えている** — Step D
   （最終圧縮→EVM verifier出力、`NEXT_STEPS.md`§3）で流用できる可能性がある。
4. HyperNova・ProtoGalaxyなど周辺方式も同じライブラリ内にあり、将来方式を変える場合の切替コストが低い。

---

## 5. 使っている折り込み方式・曲線・コミットメントスキームの具体

`nova_poc/nova-mobile/src/lib.rs`（モバイル版）・`nova_poc/uav_chain_step.rs`（デスクトップ版、
`week20/08`）で共通の型パラメータ:

```rust
type N = Nova<
    Projective,              // 主曲線: BN254 (ark_bn254::G1Projective)
    Projective2,              // 副曲線: Grumpkin (ark_grumpkin::Projective) ── CycleFold用
    ChainStepCircuit<Fr>,     // 自作のステップ回路（§6）
    KZG<'static, Bn254>,      // 主曲線側のコミットメント: KZG
    Pedersen<Projective2>,    // 副曲線(CycleFold)側のコミットメント: Pedersen
    false,                    // (Sonobeのconst genericフラグ、H=false)
>;
```

- **折り込み方式**: Nova + CycleFold（`folding_schemes::folding::nova::Nova`）。
  CycleFoldは`week20/04`で言及していた「曲線サイクルを使ってスカラー乗算の非ネイティブ算術コストを
  避ける」ための補助折り込み（Kothapalli-Setty, 2023）で、Sonobeが標準搭載している。
- **曲線サイクル**: BN254（主）↔ Grumpkin（副、CycleFold用の巡回曲線）。BN254を主曲線にしているのは
  最終的にEVM（Solidity）検証が視野にあるため（BN254はEthereumのプリコンパイルで扱える曲線）。
- **コミットメントスキーム**: 主曲線側はKZG（多項式コミットメント、trusted setupが必要）、
  CycleFold側（副曲線）はPedersen（trusted setup不要）。この組み合わせはSonobeの標準構成。
- **回路記述**: Sonobeの`FCircuit`トレイトを、arkworksのR1CS制約系（`ark-r1cs-std`の`FpVar`等）で
  直接実装する方式（gnarkでいう`frontend.API`に相当）。Sonobeにはcircom/Noir/Nonameの実験的
  フロントエンドもあるが「計算量とオーバーヘッドあり」と明記されているため、方式A(gnark)と同じく
  素のarkworksで直接書く方針にした（`week20/08`§1.1）。

---

## 6. 自作した部分（Sonobe自体には含まれないコード）

Sonobeは折り込みエンジン（`FoldingScheme`トレイトの`Nova`実装・コミットメント・EVM出力等）を
提供するだけで、「何を証明するか」（ステップ回路）はライブラリ利用者が`FCircuit`トレイトを実装して
渡す。本プロジェクトで自作したのは以下の2つ。

### 6.1 `ChainStepCircuit`（RSSI整合ステップ回路）

`circuits/remoteid_consistency_rel.circom`（circom版）・`aggregator/cmd/chainpoc`（gnark/方式A版）・
`week19/noir_rssi_consistency`（Noir版）と**同じ関係**（申告位置と自位置から距離二乗を求め、
RSSI実測レンジの相対許容帯±90%と比較）をarkworksのR1CS制約として実装したもの。

```rust
impl<F: PrimeField> FCircuit<F> for ChainStepCircuit<F> {
    type ExternalInputs = [F; 7];  // drone_lat/lon/alt, target_lat/lon/alt, measured_range_cm（秘匿）
    fn state_len(&self) -> usize { 5 }  // z=(drone_id, time_bucket, consistent_count, suspicious_count, step_count)
    fn generate_step_constraints(&self, cs, i, z_i, external_inputs) -> Result<Vec<FpVar<F>>> {
        let ok = rssi_consistency_ok(...);
        Ok(vec![z_i[0].clone(), z_i[1].clone(), &z_i[2]+&ok, &z_i[3]+(1-&ok), &z_i[4]+1])
    }
}
```

比較演算（`lower_sq <= claimed_scaled`等）は`ark-r1cs-std`の`FpVar`専用API`is_cmp`/`enforce_cmp`を
使う（`week20/08`§4で、自作のビット分解+辞書式比較だと論理バグを踏んだため、専用APIに置き換えた
経緯がある）。実体は2箇所に存在:
- `nova_poc/uav_chain_step.rs` … デスクトップ実行用（`week20/08`のPoC本体、`cargo run --example`）
- `nova_poc/nova-mobile/src/lib.rs`内 … モバイル向けに同じ回路を再実装したもの（§6.2参照。
  コードは似ているが独立した実装で、UniFFIの制約上プリミティブ型(`u64`)の外部APIに合わせている）

### 6.2 `nova-mobile`（UniFFIラッパー、モバイル向け薄いAPI）

`nova_poc/nova-mobile/`（追跡対象、Git管理下）── Sonobeの`Nova<...>`インスタンスを直接
Swift/Kotlinから呼べる形に薄くラップしたcrate。`week20/09`§2.3.1で設計し、§5.3で実装・実機確認済み。

```
ChainState::new(drone_id, time_bucket)   preprocess(1回だけ, OnceLockでキャッシュ)+init
ChainState::prove_step(obs)              1ステップ進める(消費的、内部でMutexロック)
ChainState::verify() -> bool             現在までのIVC証明を検証
ChainState::state() -> Vec<String>       z=(drone_id, time_bucket, consistent, suspicious, step)
```

- `#[derive(uniffi::Object)]`でRust構造体をハンドルとして公開、`#[uniffi::export]`で各メソッドを
  公開する（UniFFIはMozilla製、Rust→Swift/Kotlinバインディング自動生成ツール。§7参照）。
- `preprocess`（回路にのみ依存する高コストな前処理、M2 Mac実測625ms・実機Pixel 8では0.5〜2.3秒）は
  `static NOVA_PARAMS: OnceLock<NovaParams>`でプロセス内に1回だけキャッシュし、以降の`ChainState::new`
  では再利用する設計。
- `ObservationInput`（秘匿観測7項目）・`NovaMobileError`（`thiserror`＋`uniffi::Error`）もこのcrateで定義。
- ビルド成果物: `[lib] crate-type = ["lib", "cdylib", "staticlib"]` — Androidには`cdylib`
  （`libnova_mobile.so`）を使用。
- 追加の実行バイナリ2つ:
  - `src/bin/uniffi-bindgen.rs` … Kotlinバインディング(`nova_mobile.kt`)生成用CLI
  - `src/bin/on_device_bench.rs` … UIもUniFFI越境も介さず、素のRust実行ファイルとして実機で
    直接ベンチマークを取るためのバイナリ（`week20/09`§5.3の「UI組込みを待たずに実測」で使用）
- テスト: `tests/chain_state.rs` — 3ステップ実行してconsistent/suspicious/stepの値が
  `week20/08`のデスクトップ実装と完全一致するか検証（`assert_eq!`で固定値チェック）。

このcrateは`nova_poc/sonobe/`workspaceの新規メンバーとして扱う必要があるが、`sonobe/`自体は
gitignore対象なので、追跡している`nova_poc/nova-mobile/`のソース一式を毎回手動コピーしてビルドする
運用になっている（§8の再現手順参照）。

---

## 7. モバイル配線（UniFFI・Kotlin・Androidアプリ）

`week20/09`§5.3・§5.3.1の詳細をここに要約する。

```
[nova-mobile crate]                 Rust。ChainStateをuniffi::Objectとして公開
   │ cargo build --target aarch64-linux-android
   ▼
libnova_mobile.so (aarch64, 4.8MB)  依存は libdl.so/libm.so/libc.so のみ（libc++系の依存なし）
   │ uniffi-bindgen generate --language kotlin
   ▼
nova_mobile.kt (1587行, 自動生成)   nova_poc/kotlin_bindings/uniffi/nova_mobile/ に出力
   │ jniLibsへ.so、kotlinソースへ.ktを配置
   ▼
nova_poc/nova-android-demo/         最小構成のネイティブAndroid(Kotlin)アプリ
   AGP 8.7.0 / Kotlin 2.1.0 / Gradle 8.10.2
   MainActivity.kt … 「3ステップ実行」ボタン1つ+ログ表示のみのUI
```

**circom/Noirとの重要な違い**: circom・Noirは`Mopro`（zkmoproのモバイル用公式フレームワーク、
Flutter向けバインディング込み）を経由しているが、**NovaにはMopro公式アダプタが存在しない**ため、
UniFFIを直接使う自作ラッパーになっている（`week20/09`§0で確認済み。Nova-Scotiaのカスタムアダプタ
実装例はあるが、本プロジェクトはNova-Scotiaを使っていないため参考にとどめた）。UniFFIの出力が
生のKotlinであるため、Flutterアプリ（circom/Noirの方はここに統合済み、`week19/mopro_uav_circom`・
`week19/mopro_uav_noir`）には組み込まず、**素のネイティブAndroidアプリ**として独立させている
（`nova_poc/nova-android-demo/`）。3スタックの中でNovaだけアプリの土台が異なる点は把握しておくこと。

Nova(Sonobe)がNoirのような`libc++` ABI不一致問題を踏まなかった理由: Rust製で、C++ランタイムに
依存する外部Cライブラリ（Aztecのbarretenbergのような）を使っていないため。`nm`/`readelf`で
`libnova_mobile.so`の動的依存を確認したところ`libc.so`/`libm.so`/`libdl.so`のみで、
Noirが踏んだ「別のC++コンパイラで作られた静的ライブラリのtypedef mangling不一致」が原理的に
発生しない構造だった。

---

## 8. 依存関係・ビルドで直接触った版数（`week20/08`§2の要約）

Sonobeのvendored clone取得時、`ark-groth16`を古いgitコミット（0.5.0世代）に固定する一方で
`ark-ff`等の基盤crateをrev無指定（HEAD追従）にしていたため、ちょうど取得時期にarkworks本体が
0.5.0→0.6.0へ一斉に上がっていたことと衝突し、依存解決だけで16回のビルド試行を要した
（詳細な原因分析・教訓は`week20/08`§2）。最終的に採用した方針:

- `nova_poc/sonobe/Cargo.toml`の`[workspace.dependencies]`にある全arkworks familyを`^0.6.0`
  （crates.io正式公開版）に統一。`[patch]`セクションは全廃。
- `folding-schemes/src/commitment/{pedersen,ipa}.rs`内、フォーク独自API`joint_scalar_mul_be`
  （2点同時スカラー倍の最適化）を、公式`ark-r1cs-std`に未マージだったため`scalar_mul_le`の2回呼び出し
  +加算に置換（6箇所、`week20/08`§3）。

この2つのパッチは「Sonobeを本プロジェクトのarkworksエコシステムで動かすための最小限の修正」であり、
Nova/CycleFoldのロジック自体には手を入れていない。

`[workspace] members` は元のSonobeから`folding-schemes`と（本プロジェクトが追加した）`nova-mobile`
の2つに絞っている（vendored clone取得後、不要なmember＝`examples`ワークスペース外のcli等を
`Cargo.toml`から外した状態、`nova_poc/sonobe/Cargo.toml`参照）。

---

## 9. ファイル構成まとめ

| パス | 追跡状態 | 内容 |
|---|---|---|
| `nova_poc/sonobe/` | **gitignore対象**（`.gitignore:88`） | Sonobeのvendored clone本体。`folding-schemes/`（ライブラリ本体）・`nova-mobile/`（§6.2を手動コピーしたビルド用配置）・`examples/uav_chain_step.rs`（§6.1を手動コピーしたビルド用配置） |
| `nova_poc/uav_chain_step.rs` | **追跡対象** | デスクトップ版ステップ回路+実行ドライバの正本（`week20/08`） |
| `nova_poc/nova-mobile/` | **追跡対象** | モバイル向けUniFFIラッパーの正本（Cargo.toml, src/lib.rs, src/bin/{uniffi-bindgen,on_device_bench}.rs, tests/chain_state.rs） |
| `nova_poc/kotlin_bindings/` | **gitignore対象**（`.gitignore:89`） | `uniffi-bindgen`が生成したKotlinバインディング（再生成可能） |
| `nova_poc/nova-android-demo/` | **追跡対象**（一部gitignore、`.gitignore:92-98`） | 最小構成のネイティブAndroidアプリ。`local.properties`・`.gradle/`・`build/`・生成`.kt`・`libnova_mobile.so`本体は除外、`MainActivity.kt`・Gradle設定は追跡 |

---

## 10. 参照

- Sonobe: https://github.com/privacy-scaling-explorations/sonobe （Cargo.tomlメタデータ表記／§3参照）
- Sonobe README上の参照先: https://github.com/privacy-ethereum/sonobe
- Nova論文: https://eprint.iacr.org/2021/370.pdf
- CycleFold論文: https://eprint.iacr.org/2023/1192.pdf
- UniFFI（Mozilla, Rust→Swift/Kotlinバインディング生成）: https://mozilla.github.io/uniffi-rs/
- `week20/04_再帰ZKP_証明チェーン設計.md` … 方式A/B選定の設計判断
- `week20/08_Nova方式B_PoC実装結果.md` … Sonobe採用の経緯・依存解決の詳細・デスクトップ実測
- `week20/09_モバイル実行_circom_Noir_Nova_設計.md`§2.3, §5.3, §5.3.1 … UniFFI設計・モバイル実装・実機実測
