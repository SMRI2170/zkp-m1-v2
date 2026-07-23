# Flutter で実装できる ZKP フレームワーク（再調査・2026-07）

作成日: 2026-07-23 / 目的: 「Flutter アプリでオンデバイス証明を実装できる」フレームワークを、
**実際に Flutter バインディングがあるか**の観点で再調査。関連: week20/00・01・02、week19/08。
※ 出典は末尾。状況は 2026年7月時点、採用前に最新版で確認。

---

## 結論（Flutter対応度の4段階）

| 段階 | 意味 | 該当 |
|---|---|---|
| **① 即使える公式パッケージ（pub.dev）** | Dart から呼ぶ API が用意済み | **circom/Groth16** |
| **② Mopro CLI で自分でバインディング生成** | ひな型はあるが自分で組む | circom / **Noir** / halo2 |
| ③ 自前 FFI（dart:ffi） | .so/.a を自作して配線 | Plonky2 / Nova(Sonobe) |
| ✕ Flutter 向きでない | 端末証明に不向き | gnark / RISC Zero / SP1 / Cairo(別土台) |

**要点**: **すぐ使える Flutter“パッケージ”は circom/Groth16 だけ**。Noir/halo2 は Mopro 経由で
**自分でバインディングを生成すれば** Flutter で動く（ワンタッチの pub.dev API はまだ無い）。

---

## ① 即使える公式パッケージ（pub.dev）── circom/Groth16

Dart から直接呼べる、成熟した Flutter パッケージがあるのは **circom/Groth16 だけ**。

- **`flutter_rapidsnark`**（iden3）: rapidsnark で Groth16 の証明生成・検証。**本アプリが使用中**。
- **`circom_witnesscalc`**（Dart）: `.wcd` から witness を計算。**本アプリが使用中**。
- **`mopro_flutter_package`**（pub.dev, v0.0.1）: circom(Groth16, arkworks backend) の
  `generateProof()` / `verifyProof()`。**現状 Groth16 専用**（Noir/halo2 の API は未掲載）。

→ **この案件のアプリは①で実装済**（RSSI 整合回路を選択式で追加、APK までビルド確認）。

## ② Mopro CLI で自分でバインディング生成 ── circom / Noir / halo2

Mopro 本体は circom/halo2/**Noir** を Flutter に対応。ただし**汎用パッケージではなく、
`mopro build --platforms flutter` で uniffi/flutter_rust_bridge の**バインディングを自分で生成**する。

- **Noir（UltraHonk / Barretenberg）**: Flutter で動く。ただし:
  - **Android は Zig 必須**（barretenberg の libc++ ABI。今回の PoC で確認）。
  - Android エミュは x86_64 / aarch64 のみ対応。
- **実機の証明時間（Mopro 公式ブログ）**: Noir の証明生成が **Pixel 8 で ≈4.79秒 / iPhone 16 Pro で ≈2.63秒**
  （ブラウザ ≈37秒より大幅に速い）。※回路により変動。
- **halo2**: 同様に Mopro 経由で生成可能（回路実装の難度は高い）。

→ 今回の Mopro PoC は circom アダプタで **APK まで実証**。同じ手順で Noir 版も作れる（Android は Zig 追加）。

## ③ 自前 FFI ── Plonky2 / Nova(Sonobe)

- Rust なので arm64 化は可能だが、**Flutter 用の成熟プラグインが無い** → `dart:ffi` で
  `.so`(Android)/`.a`(iOS) を自作してアプリから呼ぶ配線を書く必要。
- Nova は省メモリで端末集約に向くが、実装は研究的。

## ✕ Flutter 向きでない ── gnark / RISC Zero / SP1 / Cairo

- **gnark**: 重くサーバ（集約）向け。
- **RISC Zero / SP1**: 端末証明が重すぎ、リモート prover 前提。
- **Cairo/Stwo**: モバイル SDK はあるが検証が Starknet 前提で EVM と土台がずれる。

---

## Flutter 実装の一覧表

| フレームワーク | Flutter対応 | 実装手段 | 実機証明時間の目安 | 本案件での状態 |
|---|---|---|---|---|
| circom/Groth16 | **◎ 即使える** | flutter_rapidsnark / circom_witnesscalc / mopro_flutter | 速い（rapidsnark, native ≈0.01s※） | **アプリで実装済** |
| Noir/UltraHonk | ○ 生成で可 | mopro build --platforms flutter | Pixel8 ≈4.79s / iPhone ≈2.63s | PoC手順あり・Android要Zig |
| halo2 | ○ 生成で可 | mopro（自前バインディング） | 回路次第 | 未 |
| Plonky2 / Nova | △ 自前FFI | dart:ffi | 未計測 | 未 |
| gnark / RISC Zero / Cairo | ✕ | — | — | 集約はgnark(サーバ) |

※ circom の ≈0.01s はデスクトップ x86_64・rapidsnark native の値（week20/09 実測）。実機 arm64 は別途。

---

## この案件での結論

- **Flutter で今すぐ実装するなら circom/Groth16**（`flutter_rapidsnark`＋`circom_witnesscalc`）＝
  **唯一“即使える公式パッケージ”があり、アプリで実装済**。
- **Noir を Flutter で使うことも可能**だが、**Mopro でバインディングを自分で生成**し、
  **Android は Zig を導入**する必要がある。実機証明は数秒級（回路次第）。
- halo2 は同様（生成は可・回路作りが重い）。Plonky2/Nova は自前 FFI。gnark/zkVM/Cairo は Flutter 向きでない。

→ **要件（week20/02 の R6=スマホ生成）を満たす Flutter 実装の本命は circom/Groth16**、
セットアップ根治(R7)を取るなら **Noir（Mopro 生成＋Zig）** が次点。

---

## 出典
- Mopro Flutter パッケージ（pub.dev, circom/Groth16）: https://pub.dev/documentation/mopro_flutter_package/latest/
- Mopro × Noir（Flutter対応・Pixel8 4.79s/iPhone 2.63s）: https://zkmopro.org/blog/noir-integraion/
- Mopro 概要（対応バックエンド・プラットフォーム）: https://zkmopro.org/docs/intro/
- flutter_rapidsnark（pub.dev）: https://pub.dev/packages/flutter_rapidsnark
- iden3 rapidsnark: https://github.com/iden3/rapidsnark
