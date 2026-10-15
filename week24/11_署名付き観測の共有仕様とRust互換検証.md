# Week24：署名付き観測をGoからRustへ渡すための実装

対象：[Issue #50](https://github.com/SMRI2170/zkp-m1-v2/issues/50)の最初のタスク「共有statement・入力表現の仕様化」。
**同じMiMC・曲線・署名式をRustで実装し、Goとの判定が40ケースで一致した。**
Joltの証明生成、Kimchi／Binius64への回路移植、Piでの新しい実測はまだ行っていない。

## 今回できたこと

| 成果 | 内容 |
|---|---|
| [共有仕様](../experiments/signed-observation-interop/SPEC.md) | 整数幅、fieldの正規表現、署名対象の順序、domain、count・index・rootの拘束を固定 |
| [Rust参照検証器](../experiments/signed-observation-interop/core/src/lib.rs) | BN254/Fr・MiMC110 rounds・gnark Edwards署名式と距離を検査 |
| [Go→Rust検査](../experiments/signed-observation-interop/run.py) | 元のgnark sourceをSHA照合して複製し、新しく生成した合成入力を匿名pipeで渡す |
| RISC-Vのコンパイル検査 | 同じRust libraryをno_stdでtarget check。固定toolchainへ不足targetを追加して成功 |

既存gnarkの回路・依存・測定結果は変更していない。
この段階はZKPを生成せず、Groth16 setup／VK／proofの実体も作らない。

## 40ケースの結果

| 観測数 | 正常受理 | 改変・形状不正の拒否 | 合計 |
|---|---:|---:|---:|
| 1 | 1 | 11 | 12 |
| 2 | 1 | 13 | 14 |
| 4 | 1 | 13 | 14 |
| 合計 | 3 | 37 | 40 |

Session、Policy、RID、root、座標、整数root上下、署名S、公開鍵、別署名者の署名、配列の切詰めを検査。
2／4観測では順序入替と重複も検査した。
Go側はconstraint solverの結果。配列切詰めだけはenvelopeの形状条件。
Rust側はnative参照器の結果であり、JoltやZKP verifierによる拒否ではない。

[判定JSON](logs/signed-observation-interop/native-v2/results.json)／[環境・source hash](logs/signed-observation-interop/native-v2/metadata.json)。
新しい合成observer keyは観測数ごとにRAM生成。private key・assignment・署名・Root/PKの値は公開ログへ保存していない。
JSON内の経過時間はfixture生成／solver／参照器を合わせた診断値で、prove時間や方式間ベンチマークではない。

## 受付条件はどこまで同じか

hashと署名式が同じでも、**任意の入力について全く同じ受付集合とは限らない**。
Rust参照器はcanonical field、PKのon-curve／非identity／prime subgroup、Rのon-curveを明示検査する。
既存gnark回路では、期待する正しい登録公開鍵やencodingの検査を外部の呼出側で行う前提を別途確認する必要がある。
gnark-cryptoのnative署名parserも、回路gadgetとは独立した検査を持つ。

今回の40件はGoの正しいgeneratorで作った鍵・署名と、その改変を対象にした照合。
この結果から、任意の曲線点や不正encodingまで完全互換、公開鍵の資格検証が実装済み、とはしない。
[受付境界の比較表](../experiments/signed-observation-interop/SPEC.md#入力受付の境界差)を残した。

## コンパイルと実行は区別する

| 段階 | 状態 |
|---|---|
| GoとRustのnative照合 | 成功：40件一致 |
| Rust unit test | 成功：canonical fieldとgenerator/orderの2件 |
| RISC-V no_std library check | 成功：[記録](logs/signed-observation-interop/riscv-check.json) |
| Jolt guest ELF生成・VM実行・trace測定 | 未実施 |
| JoltのPrivateInput＋zkで実proof生成・検証 | 未実施 |
| Kimchi／Binius64の署名付き回路 | 未実装 |
| Pi上の署名付きJolt実測 | 未実施 |

RISC-Vの初回checkは、固定Rust1.97.1側のtarget未導入で失敗した。
`rustup target add --toolchain 1.97.1 riscv64imac-unknown-none-elf`で解消し、同じsourceでcheck成功。
これは端末メモリ不足・Joltの非対応・prove成功のいずれの証拠でもない。

## 再実行と次の1タスク

[READMEの手順](../experiments/signed-observation-interop/README.md)に環境・コマンドをまとめた。

次は **このRust coreを固定Jolt版のn=1 guestへ接続すること**。
PrivateInput・host zkの設定を維持し、guest実行とtraceの規模を確認してから、保護されたMac実proveへ進む。
PiはMacでの正当性・資源確認後。#50全体はOPENを維持する。

研究の対象はclaimed RIDに対するobserver-signed statementの整合性。
センサーの真値、DRIP trust chain、observer hardware／航空機の真正性は保証しない。
Week23の跨Prover秘匿状態引継ぎの不採用判断は変更しない。

## 検証コマンドと結果

- `python3 experiments/signed-observation-interop/run.py --out <NEW>`：40件一致、assignmentは匿名pipeのみ。
- `cargo +1.97.1 test --manifest-path experiments/signed-observation-interop/core/Cargo.toml --locked -j 1`：2件成功。
- 上記libraryのRISC-V target check：成功。ZKP実行ではない。
- `python3 experiments/signed-observation-interop/check_results.py`：記録のhash・判定・未実施範囲を検査。
- 既存のPython61件、aggregator Go tests、契約48件：成功。

新しいCIを独立workflowへ追加し、既存の計測manifestで固定したworkflow／indexは変更していない。
CIでもfresh合成入力の40件照合を再実行するが、JoltやPiのproofを実行するものではない。
