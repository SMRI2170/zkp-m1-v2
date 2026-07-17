# 調査 — モバイルで動く ZKP フレームワークと現行回路の実現性

作成日: 2026-07-16 / 目的: 現行スタック（circom→rapidsnark→gnark集約）の代替/拡張候補を、
「今の回路を実現できるか」「端末で証明生成が現実的か」「移行コスト」の観点で比較する。
出典は末尾。数値・対応状況は 2026年前半時点、採用前に最新版で再確認すること。

---

## 0. 現行回路の要件（この基準で各FWを評価する）

対象回路: `circuits/uav_witness_attestation.circom`（約11.8k制約(実測)）＋ `remoteid_consistency_rel.circom`（~650制約）

必要なプリミティブ:
- **Poseidon ハッシュ**（各種コミットメント・drone_id_commitment・operator_commitment）
- **EdDSA(Poseidon) 署名検証 ×2**（端末署名・ドローン署名、Baby JubJub 曲線）
- **比較・範囲チェック**（LessThan / LessEqThan / Num2Bits / AbsDiff）
- **RSSI 相対許容の二乗比較**（`d_meas/r ≤ d_claim ≤ d_meas×r`）

制約: 証明系 **Groth16 / BN254**、**オンチェーン検証**（AttestationRegistry, 約348k gas）、
**gnark による再帰集約（M2, サーバ側）**。★1=トラステッドセットアップは実施済みだが根治はしたい。

→ 評価軸: ①回路実現性（上記プリミティブが書けるか）②モバイル証明の現実性（約11.8k制約(実測)）
③移行コスト（circom資産の再利用度）④トラステッドセットアップ ⑤オンチェーン検証コスト ⑥集約適性。

**全般の前提（FibRace, 2025）**: 現代のスマホの多くは**5秒以内**で証明生成が可能。
性能は主に **RAM と SoC** に依存し、**3GB以上のRAM**で安定。約11.8k制約(実測)は Groth16 では小規模で、
どのFWでも「証明が回るか」自体は問題になりにくい。差が出るのは③〜⑥。

---

## 1. circom + rapidsnark（現行・基準）

- ①実現性: ◎ すでに実装済み（circomlib の Poseidon/EdDSAPoseidonVerifier/comparators）
- ②モバイル: ○ rapidsnark は arm64 対応。約11.8k制約(実測)は数百ms〜秒級
- ③移行: 基準（ゼロ）
- ④セットアップ: △ 回路別 Groth16 セレモニー必要（実施済み）
- ⑤オンチェーン: ◎ 348k gas・定数
- ⑥集約: gnark(サーバ)で再帰検証（現行 M2）
- 位置づけ: 現状維持。以下はこの改善/代替。

---

## 2. Mopro（zkmopro / PSE）— 最小移行の本命

- 何者か: 複数の証明バックエンド（**circom+Groth16(rapidsnark)** / halo2 / **Noir(Barretenberg)** /
  arkworks / plonk 系）を **iOS(Swift)/Android(Kotlin)/Flutter/React Native** のバインディングとして生成するツールキット。
- ①実現性: ◎ **今の circom 回路をそのまま**使える（回路の書き直し不要）
- ②モバイル: ◎ ブラウザ実行比 最大10倍。arm64 実機で実用
- ③移行: **小**。現行 rapidsnark を Mopro 経由に載せ替えるだけ。**Flutter パッケージ（`mopro_flutter_package`）があり、今のアプリ構成と直結**
- ④セットアップ: 現行のまま（Groth16 なら回路別、halo2/Noir を選べば緩和）
- ⑤オンチェーン: 現行のまま（Groth16 を選べば 348k gas 維持）
- ⑥集約: 変更なし（gnark 継続）。将来 halo2/Noir へ切替も同一ツールで可能
- 判定: **今のアプリで最短の実務的アップグレード**。回路・検証・集約を変えずにモバイル生成を堅くできる。
  注意: iOS シミュレータ非対応、Android は x86_64 エミュ非対応（arm64 実機/エミュが必要）。

---

## 3. Noir + Barretenberg（UltraHonk）— トラステッドセットアップ根治候補

- ①実現性: ◎ **Poseidon 標準対応**、**EdDSA(Baby JubJub) 実装あり（約24,472制約 ≒ circom 同等）**、比較も可
  → 現行回路は Noir へ**書き直せば実現可能**
- ②モバイル: ◎ クライアント証明が速い（ある比較で Groth16 系の 5〜50倍）。Mopro/noir-rs で端末実行。
  ただし WASM 実行はネイティブ比 3.5〜4倍遅い（モバイルはネイティブ推奨）
- ③移行: **中**。circom → Noir の回路移植が必要（言語は書きやすい部類）
- ④セットアップ: **◎ 回路別セレモニー不要**（universal SRS を再利用）→ ★1 の根本対策になる
- ⑤オンチェーン: **✕ 弱点**。UltraHonk 検証が **約2.4M gas（Groth16 の約7倍）**。
  オンチェーン検証＋集約を持つ本案件ではコスト増が痛い
- ⑥集約: Honk 系の再帰はあるが、現行 gnark(BN254 Groth16 集約)とは別設計に組み替えが要る
- 判定: **「トラステッドセットアップを消す＋端末で速く証明」**なら第一候補。
  ただし**オンチェーン検証コストと集約系の作り直し**がトレードオフ。決済レイヤの再設計込みで検討。

---

## 4. halo2（PSE / Zcash）

- ①実現性: ○ Poseidon gadget あり。ECC gadget はあるが **Baby JubJub の EdDSA は自作寄り**で手間大
- ②モバイル: ○ Mopro が halo2 プローバのモバイル生成に対応
- ③移行: **大**。chip/gadget 設計の学習コストが高い（新規者に難しいとされる）
- ④セットアップ: ○ 回路別不要（KZG は universal SRS、IPA なら完全 transparent）
- ⑤オンチェーン: △ verifier は書けるが Groth16 ほど安くない
- ⑥集約: halo2 の再帰は可能だが実装重い
- 判定: halo2 固有機能（複雑な lookup/custom gate）が要らなければ**費用対効果が悪い**。積極採用しない。

---

## 5. arkworks / ark-circom（Rust・Groth16）

- ①実現性: ◎ **circom の R1CS を読み込んで Groth16** を回す（回路ロジックは現行のまま）
- ②モバイル: ○ Rust を arm64 にクロスコンパイル
- ③移行: 小〜中（Rust 化）。ただし **Mopro が内部でこれをラップ**しているので、
  単体採用するより Mopro 経由の方が楽
- ④/⑤: 現行 Groth16 と同じ（セットアップ必要・348k gas）
- ⑥集約: gnark 継続 or arkworks 側で再帰も可
- 判定: 実質 Mopro の構成要素。**単体で選ぶ理由は薄い**（Mopro に含めて考える）。

---

## 6. Plonky2 / Plonky3（Polygon Zero）

- ①実現性: **△ 相性注意**。Poseidon は Goldilocks 上でネイティブ高速だが、
  現行 **EdDSA は Baby JubJub(BN254 系)** ＝ Plonky2 の Goldilocks 体と体が違う。
  BN254 上の署名検証は**非ネイティブ演算**になり高コスト・実装大
- ②モバイル: ○ FRI ベースで証明は速い・Rust でクロスコンパイル可
- ③移行: **大**（Rust 記述＋体の不一致対応）
- ④セットアップ: ◎ 不要（transparent）
- ⑤オンチェーン: △ FRI 証明は大きく、EVM 検証は wrap が必要で高価
- ⑥集約: ◎ **再帰が速く、集約を端末側へ寄せる**のに向く
- 判定: **署名検証を含む現行回路には不向き**（体の不一致）。ハッシュ主体に再設計するなら候補。集約用途としては魅力。

---

## 7. Nova / HyperNova / folding（Sonobe など）

- ①実現性: ○ arkworks ベースで **BN254/Baby JubJub を扱える**。ステップ関数として書き直し
- ②モバイル: ◎ **folding はメモリ消費が小さく**、端末での逐次集約に向く
- ③移行: 中〜大（step-circuit へ再設計）
- ④セットアップ: ○ folding 自体は回路別不要。最終圧縮(Groth16/Spartan等)で必要な場合あり
- ⑤オンチェーン: 最終圧縮の証明系に依存
- ⑥集約: **◎ 本命用途**。N 端末の witness を**端末/コーディネータ上で逐次 fold**し、M2 をサーバ非依存にできる可能性
- 判定: **per-witness 回路の置換ではなく「集約(M2)の代替」**として最有力の研究的選択肢。

---

## 8. Cairo / Stwo（Starknet, STARK）

- ①実現性: ○ Poseidon ネイティブ。ただし署名は Stark 曲線が native で、**Baby JubJub は自作寄り**
- ②モバイル: ◎ **実機大規模実証あり（FibRace: 多くの端末で5秒以内）**、トラステッドセットアップ不要
- ③移行: 大（Cairo 記述）
- ④セットアップ: ◎ 不要（STARK）
- ⑤/⑥: **検証は Starknet 前提**＝現行の EVM＋gnark スタックと**エコシステムがずれる**
- 判定: モバイル証明・no-setup は魅力だが、**決済/集約レイヤを丸ごと Starknet 系に替える**話になり、
  本案件の EVM 前提と不整合。今回は不採用寄り。

---

## 9. gnark（Go）

- 現行の**集約(M2)担当・サーバ側**。gomobile で端末に載せられるが証明生成は重くモバイル向きでない。
- 判定: 集約サーバとして**継続**。モバイル証明器の候補ではない。

---

## 総括表

| FW | 現行回路の実現 | モバイル証明 | 移行コスト | 回路別セットアップ | オンチェーン検証 | 集約適性 |
|---|---|---|---|---|---|---|
| circom+rapidsnark（現行） | ◎実装済 | ○ | ― | 要 | ◎348k | gnark |
| **Mopro** | ◎そのまま | ◎(Flutter有) | **小** | 現行踏襲 | ◎維持 | 現行維持 |
| Noir+Barretenberg | ◎(要移植) | ◎速い | 中 | **不要** | ✕2.4M gas | 要再設計 |
| halo2 | ○(EdDSA手間) | ○ | 大 | 不要 | △ | 重い |
| arkworks/ark-circom | ◎(circom再利用) | ○ | 小〜中 | 要(Groth16) | ◎ | 可 |
| Plonky2/3 | △(体不一致) | ○ | 大 | 不要 | △大 | ◎再帰 |
| Nova/folding | ○(要設計) | ◎低メモリ | 中〜大 | 概ね不要 | 圧縮次第 | **◎M2向き** |
| Cairo/Stwo | ○(署名自作) | ◎実証あり | 大 | 不要 | Starknet前提 | Starknet |
| gnark | ―(集約用) | ✕重い | ― | ― | ― | 現行集約 |

---

## 推奨（本案件への当てはめ）

1. **いま最短で堅くする → Mopro（circom+rapidsnark を Flutter バインディングで）**。
   回路・オンチェーン検証・gnark集約を**一切変えず**、端末証明だけを最適化・安定化。iOS/Android 実機対応。
2. **★1トラステッドセットアップを根治したい → Noir+Barretenberg（Mopro経由）**。
   ただし**オンチェーン検証 2.4M gas と集約系の作り直し**を織り込む。回路は Poseidon/EdDSA とも移植可能。
3. **集約(M2)を軽く/端末寄りにする研究 → Nova系 folding（or Plonky2 の再帰）**。
   per-witness 回路はそのまま、**集約層だけ**を差し替える切り口。
4. **避ける/後回し**: halo2（費用対効果）、Plonky2 を per-witness 回路に使う（Baby JubJub と体が不一致）、
   Cairo/Stwo（EVM 前提と不整合）。

**結論**: 現行資産を最大活用する現実解は **Mopro**。トラステッドセットアップ根治まで踏み込むなら
**Noir**（オンチェーンコスト増とのトレードオフ）。集約の軽量化は **folding** が筋。

---

## 出典
- Mopro（対応バックエンド・プラットフォーム・Flutter）: https://zkmopro.org/docs/intro/ , https://zkmopro.org/blog/noir-integraion/
- FibRace（モバイル大規模ベンチ・5秒以内・RAM/SoC依存）: https://arxiv.org/abs/2510.14693
- ZKPシステム比較（rapidsnark/gnark/Noir・Noir≈0.6s・UltraHonk 2.4M gas・WASM 3.5-4x遅）: https://blog.base.dev/benchmarking-zkp-systems
- Noir stdlib（Poseidon/EdDSA・EdDSA≈24,472制約）: https://noir-lang.org/docs/noir/standard_library/cryptographic_primitives/ , https://github.com/noir-lang/zk_bench
- ZKPフレームワーク総説: https://arxiv.org/html/2502.07063v1
