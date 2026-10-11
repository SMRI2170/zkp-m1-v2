# HyperNova実行・秘密保護型引継ぎ・最新Sonobeの安全性検証

実施: 2026-10-12。実機なし、合成入力のみ。指定された3件を実行した。

| 依頼 | 結果 | 実行証拠 |
|---|---|---|
| ① HyperNova依存修正→Folding/verify | **LOCAL_COMPLETE**：固定ブランチの修正版で240fold、関連38テスト成功 | [結果](logs/hypernova-execution.json) / [テスト](logs/hypernova-fixed-tests.log) |
| ② 元Witness非共有A→B→C | **一般再帰の別方式で成立**：新しい観測の3独立prover、proof/publicのみ転送、C最終verify成功。HyperNova/NovaBlindFoldの秘密継続は未成立 | [新規証明](logs/fresh-secret-chain.json) / [公開入力改竄](logs/fresh-chain-negative.log) |
| ③ 最新Sonobe改竄・漏洩再実行 | **LOCAL_COMPLETE_WITH_FINDINGS**：132改竄拒否、6Witness省略拒否。生状態に7canaryが露出、両Hで再現 | [全件ログ](logs/sonobe-current-security.json) |

#39/#41を一括DONEにしない。HyperNovaによるZK跨Prover継続が実装済みとは記載しない。
[再現手順](poc/sonobe-current/README.md)、[固定版・hash](manifests/hypernova-current-and-secret.json)。

## ① HyperNova：ビルド失敗を修正して実行

対象: `revamp/hypernova` commit `9c4e61f8d1a5be87c00f28838a0ef657a3cf479f`。
前回の混在依存による1064コンパイルエラー、元ツリー、失敗lock/full logを保存した。
新しいignoredツリーで次を修正した。[差分](poc/sonobe-current/hypernova-ark06.patch)。

- ff/ec/relations/r1cs-std/serialize/曲線/crypto-primitives/poly-commitをcrates.io **0.6.0**へ固定。
- 古い0.5系fork patchを外し、廃止された`joint_scalar_mul_be`を`scalar_mul_le`の和へ移植。
  最新mainと同じMSM演算を使い、generator不足は明示的に拒否してzipの黙った切り捨てを防ぐ。
- relation、commitment opening、SumCheck、transcript、test assertionは削除・緩和していない。

`ark-crypto-primitives-macros`だけは0.5.0である。
これは公式`ark-crypto-primitives 0.6.0`自身が指定するproc-macro helperで、FF/EC型が0.5/0.6混在する以前の原因とは異なる。
このパッケージも[依存一覧](logs/hypernova-dependencies.json)に明示し、隠していない。

既存HyperNovaテストはHyperNova/HyperNova2、Pedersen H=true/false、
(M,N)=(1,1),(1,3),(3,1),(3,3),(0,5),(5,0)、各10round。
**240回のprove→decide_running→verify一致**を実行した。
最終修正版でsonobe-fs 3件、sonobe-primitives 35件、合計38件成功、失敗/ignoreなし。
原ソースの無修正版が成功したという意味ではなく、2ファイルの明示した研究patchを適用した結果である。
これらは小規模代数回路であり、ドローン観測や跨Prover ZK継続の検証ではない。

## ② API確認：Folding成功と秘密継続を区別する

[compile capability probes](logs/hypernova-api-probes.json)を実行した。

- `sonobe_fs::hypernova::NovaBlindFold`のimportはE0432。**この名前のAPIは当該固定ブランチにない**。
- HyperNova＋CycleFoldNova＋Poseidonの`CycleFoldBasedIVC`はIVC traitを満たし、compile probeが成功。
  ブランチにHyperNova IVCアダプタはある。名称不在だけでIVC全体が存在しないとは言えない。
- `FoldingSchemeProver::prove`はrunning/incoming witnessを引数に取り、HyperNovaの
  `LCCCSWitness`/`CCCSWitness`には`w`とcommitment randomnessが含まれる。
- 最新Sonobe mainの`IVC::prove`もWitnessを含む`Proof`を必要とする。
  `Decider`はWIP traitであり、当該mainで最終ZK proof→継続状態への変換を実証していない。

調査範囲は固定HyperNovaブランチと最新main、既存旧版、固定Microsoft Novaの関連コード。
固定[Microsoft Novaの圧縮コード](https://github.com/microsoft/Nova/blob/01b1e2d662a847ed7029770ecbaf6687398899dd/src/nova/mod.rs)は
圧縮前にrandom instanceをfoldするが、出力はCompressedSNARKで、通常のRecursiveSNARK::prove_stepの入力とは別型である。
random fold/最終ZK化の存在と、次Proverが継続できる秘密保護状態の存在を同一視しない。
[HyperNova論文](https://eprint.iacr.org/2023/573)は関連構成の一次資料。今回PDF全文の直接取得は403だったため、全文照合完了とはしない。

### ②の肯定的実行証拠：一般再帰フォールバック

既存のgnark finite recursion回路はそのまま、新しい合成観測でA/B/Cを**別プロセス**からproveした。
受信者は前段proof/publicと受信側のtrusted VKを使う。元assignmentを保存/転送/読み込まない。
Groth16 setupは新規生成せず、意図的に保存したfixtureを検査して使った。

- main/relations/go.mod/go.sumの元source hash一致を確認。
- 全15artifactのhashを受信側inventoryに固定し、各proverで再照合。
- B/Cのartifactは以前の公開hashとも一致。Aはsource＋native verifyを事前検査。
- **全段で現在ソースからCCSを再構築し、保存CCSのserialized hashと一致してからPKを読む**。
- mismatch/不完全なら停止して保存する。自動削除や無条件cache再利用はしない。

[inspection inventory](manifests/fresh-chain-fixtures.json)。preflightは16 GiB、memory_pressure free 57%、
swap used約5.03 GiB。RSS 4.5 GiB・swap 7,500 MiBの停止上限を設け、全段で未到達。

| Prover | 新規prove | 1秒pollで観測したRSS最大 | proof＋public転送 |
|---|---|---|---|
| A | 単回（stage1ログ） | 5,292,032 bytes（短い処理のためpeakを捕捉したとはしない） | 464 bytes |
| B | 18.449秒 | 1,671,102,464 bytes | 496 bytes |
| C | 24.106秒 | 2,301,018,112 bytes | 496 bytes |

wall timeはB約90.37秒、C約111.89秒で、hash検査・CCS再構築・大きいPKの読込み・proveを含む。
prove時間と混同しない。3つの最終proofはそれぞれ別native verifyでも成功。
最終公開状態はmemberMask=7、consistent=2、suspicious=1、steps=3。
BへのA、CへのA/B canaryのexact 32-byte LE/BE照合は0件。
Cの公開9入力（version/session/RID/bucket/policy/member/counts/steps）の改変は**実Groth16 verifierで全9件拒否**。
構造確認・canary検査はZK安全性証明ではなく、ゼロ知識性はGroth16等の暗号学的仮定に依存する。

この成功は固定3段一般再帰の成立例で、HyperNova/NovaBlindFold、動的参加/分岐統合、FinalBNV2 EVMの成功ではない。

## ③ 最新Sonobe：改竄拒否は改善、生状態の秘匿は別問題

`git ls-remote origin refs/heads/main`で2026-10-12時点のlatest mainが
`7f042351e73d38f99c05167ba41f1e282178b067`と確認。upstream sourceは変更せず使った。
小規模な7秘密入力の「全て非zeroならcount+1」回路と、公開session/RID/bucket/policy/countの5状態を追加。
これは秘匿入力とproof構造を調べるtoy回路であり、既存RSSI回路や実RF計測ではない。

両HでA/B/Cの6独立プロセスが受信verify→prove→最終verifyを実行した。
上流Proofは六つのpublic fieldのtupleで、公式CanonicalSerializeを備えていないため、
各fieldを明示的にencode/decodeする研究用wire adapterを作った。
non-hidingのNull randomnessだけは値を持たないため0 bytes。受信正常検証がadapterのroundtripを確認する。

各段22件×3段×2H＝**132件**の改竄を拒否：
primary running w/e/cmW/cmE/u/x、incoming w/cmW/x、CycleFold w/e/cmW/cmE/u/x、
step、initial state、session/RID/bucket/policy/count。
旧版で受理されたincoming cmW改竄も、当該mainでは拒否した。
incoming witnessを全zeroに置換した6件も拒否。Witnessを省けば同じ検証済み継続状態になるわけではない。

**漏洩結果：各段のincoming witnessに、その参加者の元7canaryが完全一致で残った。両Hで同じ。**
B受信時にはA、C受信時にはBの7canaryが読めた。serialized raw stateでも一致を確認。
転送サイズはH=true 5,273,696 bytes、H=false 5,273,536 bytes。
H=trueのPedersen commitmentがhidingでも、raw Witness fieldを共有すれば秘匿されない。
これは生のWitness-bearing stateの結果であり、Sonobeの最終ZK証明の破壊や、全新版の脆弱性とは主張しない。

## 判断と残件

- 修正後HyperNovaはFolding/verificationが動作するため「ビルドできない」は解消した。
- 現在確認した生IVC継続状態を秘密非共有A→B→C経路へ採用しない。受信verifyによる改竄拒否だけではprivacy要件を満たさない。
- 秘密非共有の現在の実行可能経路は、今回再実行した一般再帰proof/public転送を維持する。
- HyperNova固有の秘密継続は、ZK blinding層/公開状態binding/継続APIを別に実装・検証する課題として残す。
  randomなwへ差し替えたり、relation/openingを無視してgreenにする変更はしていない。

V2はclaimed RIDと観測者署名の研究PoC。DRIP、センサー真値、実UAV同一性、観測者hardware認証を保証しない。
fixture/keys/proof/raw Witnessはignored owner-only領域に保存し、公開はhash・合成canaryの一致位置/件数・結果だけ。
使い捨てGroth16 VK/proofをGit・Besu・EVMへpublish/deployしていない。
既存UAV Python 61件、aggregator Go、contracts 48件も成功。
