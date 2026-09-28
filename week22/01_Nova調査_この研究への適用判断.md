# Nova調査：この研究に適用すべきか

調査日: 2026-09-28

## 結論

**Novaは「同じ状態遷移を何度も繰り返す」部分には非常に適している。**
この研究では、端末観測を1件ずつ追加してnullifier rootと件数を更新する
順序付き集約に採用候補になる。

ただし、Novaは「任意のGroth16 leaf proofをそのまま2つ内包してマージする」
仕組みではない。その用途だけを期待して既存BN254 leaf proofの上にNovaを重ねると、
leaf verifierを各step回路に入れる必要があり、利点が小さくなる。

したがって方針は次の通りにする。

```text
端末で既存BN254 leaf proofを作る        : 維持
leafをNova stateへ持ち込むBridge         : 必要
Nova IVCで nullifier / count を順次更新  : 有力候補
最後にEVM用Decider / Groth16へ圧縮       : 必須
```

## Novaとは何か

Novaはfolding schemeを使うIncrementally Verifiable Computation (IVC) である。
各stepで「前の状態に、今回の秘密入力を使って同じ関数を1回適用した」ことを
foldし、回数に依存しない大きさの累積proofを作る。

```text
z0 -- F(w0) --> z1 -- F(w1) --> z2 -- F(w2) --> ... --> zn
                         \_______________________________/
                           最後に1つへ圧縮できる累積proof
```

Nova論文は、foldingの検証回路が小さく、各stepのprover負荷を抑えられることを
主眼にしている。[Nova論文 (IACR ePrint 2021/370)](https://eprint.iacr.org/2021/370.pdf)

## この研究でNovaに向く部分

1台の端末を受理するたびに、次のstateを更新する関数を `F` として定義できる。

```text
入力 state:
  version, droneId, timeBucket, policy, memberRoot,
  nullifierRoot, consistentCount, suspiciousCount

今回のprivate witness:
  端末鍵、membership path、nullifier path、観測の秘密値、署名

出力 state:
  同じsession情報,
  更新されたnullifierRoot,
  consistency_okに応じて+1されたcount
```

これなら「前のstateから次のstateへ正しく進んだこと」を、台数分だけ繰り返し
証明できる。端末の重複は、既に使用済みのnullifier leafをゼロとして示せないため
stepそのものが成立しない。

現在実装している `PairCircuit` / `NodeBW` の順序付きroot連結は、Novaで表現する
state machineと同じ安全不変条件を持つ。

## Novaだけでは解決しない点

### 1. 既存leaf Groth16 proofの接続

Novaの標準的な使い方は、同じstep回路 `F` を繰り返すことだ。既存のCircom
BN254 leaf proofを単に入力として受け取るだけでは、そのleafが正しい保証には
ならない。

安全に接続する方法は二つある。

| 方法 | 内容 | 判断 |
| --- | --- | --- |
| A. step内でleaf proofを検証 | 既存leafを保てるが、毎stepの再帰検証が重い | Bridge用途に限定 |
| B. leafの関係をNova stepへ移植 | 証明経路が単純で高速化しやすいが、Circom回路の再実装が必要 | 本命 |

本研究では、短期はAでBridgeを作り、検証後はBへ移行するのが安全である。

### 2. 独立した2集合の任意binary merge

Novaは本質的に `z(i+1) = F(z(i), w(i))` の逐次状態機械に向く。二つの既存
nullifier集合を「交差していない」と示して任意順でunionする問題は、Novaを使っても
別の集合証明設計が必要である。Novaを入れるだけでこの問題は解決しない。

### 3. EVMへの最終検証

foldされた途中proofをそのままEVMで安価に検証するのではなく、最後にDecider
proofへ圧縮する必要がある。Microsoft Nova実装はEVM featureを持つ一方、実際の
proof形式・Solidity ABI・trusted setup要否は選ぶDeciderに依存する。

## 実装候補の評価

### Microsoft Nova

- Rust実装。Novaの原著実装で、EVM featureを提供する。
- IVC・圧縮proofの研究・比較の基準として最も読みやすい。
- 本プロジェクトのFlutter/Go/Circom構成へ直接組み込むための高水準frontendは
  用意されていない。

参照: [Microsoft Nova README](https://github.com/microsoft/Nova)

### Sonobe

- Nova、CycleFold、HyperNova等を抽象化し、EVM Deciderを目標にするRustライブラリ。
- 現時点のREADMEではNova / CycleFoldはstableと記載される一方、パッケージは
  `0.1.0-alpha.1` のpre-releaseでAPI変更の可能性があり、production利用には
  注意が必要と明示されている。
- Circom frontendは実験的・再整備中であり、このプロジェクトのleafをそのまま
  取り込む最短経路とは言えない。

参照: [Sonobe README](https://github.com/privacy-ethereum/sonobe)、
[Sonobe Decider/EVM説明](https://sonobe.pse.dev/design/nova-decider-onchain.html)

## 採用判断

| 判断項目 | Nova | この研究での評価 |
| --- | --- | --- |
| 端末を順番に追加する | 得意 | 採用候補 |
| 任意の2proofを直接内包して木マージ | 主目的ではない | 現行の直接再帰PCDも比較維持 |
| 既存Circom Groth16 leafの再利用 | Bridgeが必要 | 追加実装が必要 |
| EVM最終検証 | Decider圧縮が必要 | 可能だが実証必須 |
| モバイル | Rust/WASMは候補、ネイティブFFIも可能 | 実機ベンチ必須 |
| 本番成熟度 | 原理は成熟、周辺ライブラリは変化中 | 研究PoCとして有力、即本番採用は不可 |

## Week 22で行うべき最小PoC

1. RustでNovaまたはSonobeの最小 `F` を作る。
2. `F` は実観測ではなく、まず `(nullifierRoot, consistent, suspicious)` の安全な
   状態遷移だけを証明する。
3. 3〜10 stepをfoldし、最後のstateが期待値と一致することを確認する。
4. 同じnullifier、異なるdrone/bucket、count改ざんを拒否するテストを書く。
5. DeciderのEVM verifierを生成し、既存V1 ABIとの違いを表にして採用判断する。

このPoCに成功しても、既存leafを安全に接続するBridgeと実機性能測定が終わるまで、
Novaを最終アーキテクチャとして確定しない。
