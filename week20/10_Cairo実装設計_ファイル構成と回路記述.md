# Cairo実装設計 ── ファイル構成と回路記述方法

作成日: 2026-07-25 / 目的: circom/Noir/Nova（`week20/09`）に続く4本目の候補スタックとして、
StarkWareのCairo（+STARKプルーバー）でRSSI整合回路を実装する場合の設計（実装方法・ファイル構成・
実際の回路記述）をまとめる。**本ドキュメントは設計のみで、実装・実機検証はまだ行っていない**
（`week20/09`の§0〜§3と同じ、実装着手前の設計メモという位置づけ）。
関連: `week20/09`（circom/Noir/Nova実装+性能比較）、`week19/02_フレームワーク比較.md`・
`week20/00_スマホで実装できるフレームワーク.md`（Cairoを「別土台のため今回は見送り」としていた
過去の判断）。

---

## 0. 前提の更新 ── なぜ今Cairoを再検討するか

過去の調査（`week19/02`, `week20/00〜03`）では、Cairoは一貫して「モバイル実行力はある/有望だが
StarkNetという別の土台に乗るため今回は見送り」という位置づけだった。しかしこのプロジェクトが
Noir/Nova（`week20/09`）で実際にモバイル実装まで進めた経験を踏まえて再整理すると、この「別土台」
という懸念は一部**過大評価だった可能性がある**。

- Cairoでの証明生成に使う`stwo`（StarkWareの次世代STARKプルーバー、Rust製、2024年OSS化）は、
  **StarkNetチェーンへのデプロイを前提としない**。circomにsnarkjs/rapidsnark、Noirに
  barretenbergがあるのと同様に、Cairoプログラムの実行トレースからスタンドアロンでSTARK証明を
  生成・検証できる（`week19`調査時点の想定は「Cairo＝StarkNetの言語」という理解に寄っていた
  可能性がある）。
- 一方で、以下は実際に**残る制約**として確認できる。
  - **Moproに公式Cairoアダプタが無い**（circom/Halo2/Noirのみ公式。`week20/09` §0参照）。
    → Novaと同じく**カスタムUniFFIアダプタを自作する**必要がある（Nova-mobileの実装パターンが
    そのままテンプレートになる。§2参照）。
  - **オンチェーン検証の着地点が未整備**: 本プロジェクトの`contracts/`はGroth16(BN254)向け
    （`AggregateVerifier.sol`はgnark生成）。CairoのSTARK証明はStark252という別の素体・別の証明
    形式のため、EVM側で検証するには別途STARK verifier契約（例: StarkWare系の"Integrity"、または
    Solidity STARK verifier）が要る。既存資産の再利用ができない。
  - **既存の登録型検証(`AttestationRegistry`)との整合**は要再設計（Groth16を1件ずつ検証する現行
    方式をSTARK用に置き換えるか、STARK証明はオフチェーン集約してから別ルートで載せるか）。

結論として、Cairoは「モバイルで動く見込みが無いから見送り」ではなく、**「Mopro公式アダプタが無く
自作コストがかかる」「オンチェーン着地の資産がゼロから」という実装コストの問題**として捉え直すのが
正確（Novaも同じ理由で見送られかけていたが、実際に自作したところ最もクリーンにモバイル到達できた
という前例がある。`week20/09` §5.4参照）。

---

## 1. Cairoの回路（＝プログラム）の考え方 ── circom/Noir/gnarkとの違い

| | circom | Noir | gnark | **Cairo** |
|---|---|---|---|---|
| モデル | R1CS DSL（signal配線を手書き） | ACIR（関数として記述、コンパイラがACIRへ） | Go DSL（`frontend.API`で制約を手書き） | **CairoVM命令列**（関数として記述、実行トレースがそのまま証明対象） |
| 素体 | BN254 scalar field | BN254 (Barretenberg) | BN254 | **Stark252**（$2^{251}+17\cdot2^{192}+1$、Cairo独自） |
| 比較/絶対値 | `Num2Bits`+`LessThan`を自前構築（`lib_uav_safety.circom`） | 標準ライブラリのu64比較（range-check組込み） | `std/math/cmp`（`IsLess`等） | **corelibの符号付き/符号無し整数型＋比較演算子**（range-check builtinで自動処理、Noirに近い書き味） |
| 証明系 | Groth16（トラステッドセットアップ要） | UltraHonk（不要） | Groth16（要） | **STARK（トラステッドセットアップ不要、FRIベース）** |
| 公開/非公開の指定 | signal宣言（`input`/`output`） | 引数の`pub`修飾子 | `frontend.Variable`のpublic/secretタグ | **プログラムの出力（`main`の戻り値）が公開、引数はデフォルトで非公開witness**（要実装時確認、§4） |

Cairoは「制約を書く」のではなく「計算を書く」──circomのように明示的にsignalを配線する必要が無く、
Noir/gnarkに近い「関数を書けばコンパイラ/VMが証明対象のトレースを作る」モデル。RSSI整合判定のような
「四則演算＋比較＋条件分岐」中心の回路とは相性が良い（絶対値やレンジ比較を自前でビット分解する必要が
circomよりずっと少ない）。

---

## 2. ファイル構成設計

### 2.1 単体の回路（デスクトップでの検証用）── `week19/noir_rssi_consistency/`と同じ形

```
week19/cairo_rssi_consistency/
├── Scarb.toml              # パッケージマニフェスト（Nargo.tomlに相当）
├── src/
│   └── lib.cairo             # RSSI整合判定（remoteid_consistency_rel.circom / main.nr 相当）
├── tests/
│   └── rssi_consistency_test.cairo   # 整合/なりすまし双方のケース（#[test]関数、Prover*.tomlの代わり）
└── target/                  # `scarb build`/`scarb execute`の出力（.gitignore対象）
```

`Nargo.toml`の`Prover.toml`/`Prover_spoofed.toml`/`Prover_forged.toml`（外部TOMLで入力値を分離する
Noirの流儀）と異なり、Cairoは**テスト関数の中に入力値を直接書く**のが標準的（`#[test]`関数内で
`rssi_consistency_ok(...)`を複数の入力セットで呼ぶ）。実行時証明生成用の入力は`scarb execute
--arguments ...`または`--arguments-file`で別途与える（§3.3）。

### 2.2 モバイル向けカスタムアダプタ（Novaと全く同じ形を踏襲）

Moproに公式Cairoアダプタが無い点はNovaと同条件のため、**`nova_poc/nova-mobile/`で実証済みの構成を
そのまま転用する**（§0で述べた通りテンプレートとして最も信頼できる前例）。

```
week19/mopro_uav_cairo/            # 新規、nova-mobileと同じ形のRust cdylibクレート
├── Cargo.toml                      # 依存: stwo-prover（or cairo-lang-runner等、要選定）+ uniffi
├── src/
│   ├── lib.rs                      # UniFFI公開API（下記）
│   └── bin/
│       ├── uniffi-bindgen.rs        # Kotlinバインディング生成用（nova-mobileと同じ構成）
│       └── on_device_bench.rs       # UI無しの素バイナリ実機ベンチ（nova-mobileと同じ構成）
└── tests/
    └── rssi_consistency.rs          # ネイティブでの機能テスト
```

公開するRust API（Nova版`nova_preprocess`/`nova_init`/`nova_prove_step`/`nova_verify`と対になる形。
Cairoはチェーン化ではなく単発関係の証明なので、Novaより単純でcircom/Noirの形に近い）:

```rust
#[uniffi::export]
pub fn cairo_prove_rssi_consistency(inputs: RssiConsistencyInput) -> CairoProofResult;

#[uniffi::export]
pub fn cairo_verify_rssi_consistency(proof: CairoProofResult) -> bool;
// RssiConsistencyInput = drone_lat/lon/alt, target_lat/lon/alt, measured_range_cm（UniFFIのdictionary型、
// circom版main.dartの7フィールドと同じ）
```

Android/iOS向けクロスコンパイル・`libmopro_uav_cairo.so`生成・Kotlinバインディング生成・実機dlopen
確認までの手順は、`week20/09` §6（nova-mobile再現手順）の1〜5と同型（sonobe→stwo-proverに読み替え）。

---

## 3. 実際の回路（Cairoプログラム）の記述方法

`circuits/remoteid_consistency_rel.circom`と全く同じ関係式（幾何距離の二乗 vs
`measured_range_cm`の相対許容帯±90%、平方根/除算なし・整数演算のみ）を、Cairo 2.x（corelib方式）で
書く場合の設計。

### 3.1 定数・型

```cairo
// src/lib.cairo
const LAT_CM_NUM: i128 = 11132000;
const LON_CM_NUM: i128 = 9128800;
const GEO_DEN: i128 = 10000000;
const TOL_NUM: u128 = 90;
const TOL_DEN: u128 = 100;
```

circom版は全信号がBN254 scalar field上の非負整数（符号は`AbsDiff`が内部で吸収）だが、Cairoは
`i128`（符号付き）が標準corelibに存在するため、**緯度・経度差分の符号をそのまま扱える**
（circomのように`AbsDiff`をビット分解から自作する必要がない。§1の比較表参照）。

### 3.2 RSSI整合判定本体

```cairo
fn abs_diff_i128(a: i128, b: i128) -> u128 {
    if a >= b { (a - b).try_into().unwrap() } else { (b - a).try_into().unwrap() }
}

// 戻り値: (consistency_ok, claimed_dist_sq)
fn rssi_consistency_ok(
    drone_lat_e7_norm: i128, drone_lon_e7_norm: i128, drone_alt_cm: i128,
    target_lat_e7_norm: i128, target_lon_e7_norm: i128, target_alt_cm: i128,
    measured_range_cm: u128,
) -> (bool, u256) {
    let dlat_raw: u256 = abs_diff_i128(drone_lat_e7_norm, target_lat_e7_norm).into();
    let dlon_raw: u256 = abs_diff_i128(drone_lon_e7_norm, target_lon_e7_norm).into();
    let dalt_cm: u256 = abs_diff_i128(drone_alt_cm, target_alt_cm).into();

    // circom版と同じく「割ってから二乗」ではなく、スケール(分母)を保持したまま
    // 二乗・比較の最後まで持ち越す（丸め誤差を判定に混入させないため。§3.2末尾の注意点参照）。
    let lat_num: u256 = dlat_raw * LAT_CM_NUM.try_into().unwrap();
    let lon_num: u256 = dlon_raw * LON_CM_NUM.try_into().unwrap();
    let geo_den: u256 = GEO_DEN.try_into().unwrap();

    // claimed_dist_sq * geo_den^2 = lat_num^2 + lon_num^2 + (dalt_cm*geo_den)^2
    let claimed_dist_sq_scaled: u256 =
        lat_num * lat_num + lon_num * lon_num + (dalt_cm * geo_den) * (dalt_cm * geo_den);
    let geo_den_sq: u256 = geo_den * geo_den;

    let base: u256 = measured_range_cm.into();
    let lower: u256 = base * (TOL_DEN - TOL_NUM).into();
    let upper: u256 = base * (TOL_DEN + TOL_NUM).into();

    // claimed_dist_sq_scaled/geo_den_sq を実際に割らず、両辺に geo_den_sq を掛けて比較する
    let lhs: u256 = claimed_dist_sq_scaled * (TOL_DEN * TOL_DEN).into();
    let ok = lhs >= lower * lower * geo_den_sq && lhs <= upper * upper * geo_den_sq;

    (ok, claimed_dist_sq_scaled / geo_den_sq) // 出力用のclaimed_dist_sqのみ最後に割る（判定には使わない）
}

fn main(
    drone_lat_e7_norm: i128, drone_lon_e7_norm: i128, drone_alt_cm: i128,
    target_lat_e7_norm: i128, target_lon_e7_norm: i128, target_alt_cm: i128,
    measured_range_cm: u128,
) -> (bool, u256) {
    rssi_consistency_ok(
        drone_lat_e7_norm, drone_lon_e7_norm, drone_alt_cm,
        target_lat_e7_norm, target_lon_e7_norm, target_alt_cm,
        measured_range_cm,
    )
}
```

要注意点（実装時に必ず検証。circomでも今回`json_to_hashmap`の沈黙バグを踏んだのと同種の
「動くが値が違う」落とし穴になりやすい箇所）:

- **オーバーフロー**: `claimed_dist_sq_scaled`や`lower*lower*geo_den_sq`のような多段の掛け算が
  u256の上限（約1.15×10^77）に収まるかは、circom版の実測値（`claimed_dist_sq≈1.17×10^19`）を
  もとに桁数を積み上げて確認する必要がある。u128では溢れる可能性が高いためu256を使う設計にしたが、
  実測して確定させる。
- **除算のセマンティクス**: Cairoの整数型の`/`は**切り捨て除算**（Rustと同様。circomの回路内除算
  ＝有限体上の乗算逆元とは根本的に意味が違い、むしろNoir/gnarkのuint除算と同じ意味）。circomは
  「割り算を使わない」ために分子分母を保持したまま二乗比較する設計だったが、Cairoでも同じ理由
  （丸め誤差を回路の判定結果に混入させない）でこの設計方針を踏襲している（上記コードの`ok`計算は
  除算を行わず、出力用の`claimed_dist_sq`だけ最後に1回割っている）。
- **public/private分離の実際の指定方法**: `main`の引数が実際に「証明の中で秘匿されるwitness」に
  なるのか、`scarb execute`にどう渡すかで公開/非公開の境界が決まる（§4で詳述、要実装時確認）。

### 3.3 テスト

```cairo
#[cfg(test)]
mod tests {
    use super::rssi_consistency_ok;

    #[test]
    fn test_consistent_observation() {
        // zk-distance/samples/sample_remoteid_consistent.json と同じ値（他言語版と同条件）
        let (ok, claimed_dist_sq) = rssi_consistency_ok(
            1256891390, 3196917000, 1200,
            1256891590, 3196917180, 1000,
            341,
        );
        assert!(ok, "expected consistent");
        assert_eq!(claimed_dist_sq, 11656910617856000000_u256); // snarkjs実行結果と一致するはず
    }

    #[test]
    fn test_spoofed_observation() {
        let (ok, _) = rssi_consistency_ok(
            1256891390, 3196917000, 1200,
            1256891590, 3196917180, 1000,
            5000, // なりすまし: 帯域外のRSSI申告レンジ
        );
        assert!(!ok, "expected inconsistent");
    }
}
```

`scarb test`で実行できる（Noirの`nargo execute`+`Prover_*.toml`3種、circomの
`test_remoteid_consistency_rel`と同じ役割）。

---

## 4. 未確定・実装時に確認が必要な点（正直ベースの整理）

このドキュメントは設計段階であり、以下は**実装前に手を動かして確認するまで確定しない**。

1. **public/private witnessの実際の指定方法**: Cairo/`scarb execute`は、circomのsignal宣言や
   Noirの`pub`修飾子のような**言語レベルでの明示的な公開/非公開指定を持たない**（`main`の引数は
   `--arguments`で与えられるprogram input、戻り値がoutput、という実行系の慣習に依る）。
   本プロジェクトが要求する「座標・生RSSIは隠したまま整合判定結果だけ公開する」という性質を
   Cairoでどう表現するか（秘匿したい値をhint経由で読み込み、`main`はconsistency_okと
   claimed_dist_sqだけをreturnする、など）は実装時に確定させる。
2. **証明生成ツールチェーンの正確なコマンド**: `scarb execute`でトレース生成→`stwo`
   （または`cairo-prove`等の周辺CLI）で証明生成→検証、という大枠は把握しているが、正確な
   CLI名・バージョン間の非互換は`week20/08`のsonobeで踏んだのと同種の「導入だけで数十回のビルド
   試行」リスクが十分あり得る。実装フェーズの最初に切り分ける。
3. **`stwo-prover`のRustクレートとしての公開状況・モバイル(aarch64-linux-android)クロスコンパイル
   可否**: Novaの`folding-schemes`(sonobe)がクロスコンパイルに成功した実績はあるが、`stwo`が
   同様にNDK向けにビルドできるかは未検証（FRIベースのSTARK特有の大きめメモリ・多項式FFT処理が
   モバイルでどの程度重いかも未知数）。
4. **オンチェーン最終着地**: §0で述べた通りSTARK verifierの資産が本プロジェクトに無いため、
   Step D相当（`week20/06` §3 D「最終圧縮→EVM verifier出力」）をCairoでやる場合は**別建て**になる。

---

## 5. 位置づけ・次の一手

- **優先順位は低い**: `week20/09`でcircom（単発証明の最速）・Nova（モバイルIVCの最速）が実機実証済み、
  Noirも残1シンボルまで来ている中、Cairoは①Mopro公式アダプタなし（自作要）②オンチェーン資産ゼロ、
  という2つの追加コストがある。**現行の本流（circom端末証明→gnark/Nova集約→EVM）を止めてまで
  着手する理由は今のところ無い**。
- **一方で興味深い可能性**: STARK（Cairo/stwo）は**再帰証明（証明の中で別の証明を検証する）を
  得意とする**証明系として知られる（StarkNet自体が大量の再帰STARK証明でL2をまとめている）。
  本プロジェクトの「方式A(gnark自己再帰)/方式B(Nova folding)」に続く**「方式C」＝Cairo上でのSTARK
  再帰チェーン**は、`week20/04`の要件（各中間証明が単体検証可能＝方式Aの利点）と
  `week20/08`の要件（モバイルでの軽さ＝方式Bの利点）を**両立できる可能性がある**設計上の
  もう一つの選択肢として、頭の片隅に置いておく価値がある（現時点では未検証の仮説）。
- **次に着手する場合の最初の一歩**: §2.1の`week19/cairo_rssi_consistency/`（Scarb単体パッケージ）を
  デスクトップで動かし、§3のコードを実際に`scarb test`に通してcircom/Noir/gnark/Novaと同じ
  `claimed_dist_sq`が出るか照合するところから（circom/Noir同様、まずデスクトップでの正しさの
  確認が先、モバイル化はその後）。

---

## 6. 参照

- `week20/09_モバイル実行_circom_Noir_Nova_設計.md`（本ドキュメントの直接の前身。circom/Noir/Nova
  実装・性能比較）
- `week19/02_フレームワーク比較.md`, `week20/00_スマホで実装できるフレームワーク.md`（Cairoを
  「別土台のため見送り」としていた過去の判断の原文）
- `circuits/remoteid_consistency_rel.circom`, `week19/noir_rssi_consistency/src/main.nr`（移植元の
  正準ロジック）
- `nova_poc/nova-mobile/`（Moproに公式アダプタが無いスタックをカスタムUniFFIアダプタ化する際の
  実証済みテンプレート）
- Cairo公式: https://book.cairo-lang.org/ , https://docs.swmansion.com/scarb/ ,
  StarkWare stwo: https://github.com/starkware-libs/stwo

---

## 付録: 今回あわせて修正したエラー（2026-07-25）

Cairo設計の作業と並行して、既存3スタック（circom/Noir/Nova）実装のエラー洗い出しを行い、以下を
修正した。

1. **`week19/mopro_uav_circom/tests/circom.rs`・`tests/bindings/circom/`**: moproスケルトン生成時の
   `multiplier2_final.zkey`テストが残っており、`set_circom_circuits!{}`（`src/lib.rs`）では
   `remoteid_consistency_rel_final.zkey`のみ登録済みのため`Unknown ZKEY`で失敗していた
   （`cargo test --release`が非ゼロ終了）。実案件と無関係な旧スキャフォールドのため削除。
2. **`week19/mopro_uav_circom/flutter/integration_test/plugin_integration_test.dart`**: 生成時の
   パッケージ名`mopro_example_app`のままimportしており、実際のバインディングファイル名
   （`mopro_uav_circom.dart`）と食い違って**コンパイル不能**（`flutter analyze`で10件のエラー）
   だった。import修正に加え、実装されていない（stubのまま）Halo2/Noirのテストケースを削除し、
   実回路（`remoteid_consistency_rel`、配列wrap済み入力）1件のテストに置き換えて修正。
3. **`week19/mopro_uav_circom/flutter/lib/main.dart`**: Halo2/Noir/Gnarkタブは`mopro create`
   スキャフォールドのstub実装のまま（`generate_halo2/noir/gnark_proof`は常にpanicする設計、
   `src/stubs.rs`）で、UI上はボタンとして存在するため誤って動作すると誤解しやすい状態だった
   （実害は無い＝各ボタンは`try/catch`でpanicを捕捉しエラー表示するだけで済んでいたことを確認
   済み）。意図を明記するコメントを追加。
4. **既知の環境ギャップ（未修正・対象外）**: `tests/ffi.rs`の`kotlinc`バインディングテストは
   ローカルに`kotlinc`が未導入のため失敗する。実際のAndroidバインディング生成経路
   （`mopro build`/UniFFI codegen）とは別のスキャフォールド用テストであり、モバイル実装の実測
   結果には影響しない。導入するかはユーザ判断（`brew install kotlin`等）。
