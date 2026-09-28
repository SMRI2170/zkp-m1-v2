# Week 20・Week 21 実装まとめ

更新日: 2026-09-28

## 一言でいうと

Week 20では、スマホが作った複数のゼロ知識証明を「証明のまま」つなげる方法を
調査して動く試作を作った。Week 21では、その試作を実運用へ近づけるために、
端末の重複参加防止・固定検証鍵・最終的にEVMへ記録するための仕様と契約を追加した。

```text
スマホの観測
  → 個別ZK proof
  → 複数proofを検証しながら集約
  → 最終proof
  → EVMへ「信頼／なりすまし疑い」を記録
```

## Week 20：方式の選定と「証明チェーン」のPoC

### 何を解決したか

複数端末の観測を集めるとき、集約者を信用せずに、前の結果が正しいことを次の
証明の中で確認する必要がある。これを再帰ZKP（proof-carrying data / PCD）として
試作した。

### 実装したこと

| 実装 | できること | 意味 |
| --- | --- | --- |
| RSSI整合回路 | 放送位置からの幾何距離と、電波から推定した距離を回路内で比較 | 位置・RSSIの生値を公開しない |
| 個別端末leaf proof | 距離、時刻、映像検知、端末署名、Remote ID署名を1端末分として証明 | 端末観測の真正性を作る |
| gnark再帰チェーンPoC | 前のproofを次の回路内で検証し、整合・矛盾の件数を増やす | 集約者が途中結果を改ざんできない |
| Nova / Sonobe / Circom / Noir / Cairo調査 | モバイル実行性と再帰方式を比較 | EVMとの互換性を残す構成を選ぶ |
| Flutter可視化 | セッション、端末、判定、チェーン状態を見える形にする | hashだけでは分からない問題を解消する入口 |

### Week 20で確認できたこと

- 3段の再帰チェーンを動作させた。
- 同じドローン・同じ時間窓でない入力、前の公開値の改ざん、RSSI判定の偽装を
  証明生成段階で拒否できた。
- ただし、当時のチェーンは段ごとに回路形状を作り直すPoCであり、無制限に延長
  できる本番PCDではなかった。

## Week 21：安全な状態遷移とEVM接続の土台

### 何を解決したか

Week 20のPoCだけでは、「同じ端末を何度も数える」「別の回路のproofを混ぜる」
「EVM上で何を最終結果として検証するかが曖昧」といった問題が残る。Week 21では
これらを仕様・回路・契約として固定した。

### 実装したこと

| 実装 | できること | 防ぐ問題 |
| --- | --- | --- |
| v1最終proof ABI | 9個の公開入力、sessionId導出、値域を固定 | 実装ごとの入力解釈のずれ |
| V1 Solidity Registry | policy/root/version検証、session/proof再利用拒否、最終record保存 | 同じ結果の付け替え・二重確定 |
| membership Merkle回路 | 登録端末だけを参加可能にする | 未登録端末・Sybil攻撃 |
| nullifier回路 | 同一端末を同一sessionで一度だけ消費する | 二重計上 |
| PairCircuit | 2端末を `oldRoot → 中間Root → newRoot` と安全に連結 | 途中状態を飛ばす再利用 |
| 固定VK再帰検証 | 子proofの検証鍵を回路定数にする | relayerによる別回路proofの混入 |
| NodeBW | 固定鍵で2子proofを回路内検証し、session一致・root連結・件数加算を強制 | 集約値の改ざん・別session混入 |
| artifact manifest / CI / E2Eスクリプト | 回路成果物のハッシュ検証と継続テスト | 再現不能なビルド・回帰 |

### NodeBWが行うこと

```text
左の子proof: oldRoot ──観測群A──> midRoot
右の子proof: midRoot ──観測群B──> newRoot
                    │
                    └─ 一致しなければマージproofは作れない

出力: AとBの整合件数・矛盾件数の合計
```

## 動作確認

以下をローカルで成功させている。

```text
cd aggregator && go test ./...
cd contracts && npm test
```

- Go: membership、nullifier、曲線サイクル、固定鍵拒否、NodeBWの正常系・改ざん拒否。
- Solidity: 36件のHardhatテスト（ABI、policy、root、session、proof再利用を含む）。

## 現在地と残る実装

現在は「端末の個別証明を安全に順序付きで集約する基盤」まで実装済みである。
最終的な本番フローはまだ未完了で、次が必要となる。

1. `NodeBW` と対になる `NodeBLS` を作り、固定形の曲線サイクルを完成させる。
2. 現在のBN254 leaf proofを再帰状態へ変換する `BridgeBW` を作る。
3. 二つの既存nullifier集合を安全に統合する非交差unionを作る。
4. PCD rootを9入力のEVM向けGroth16/BN254 final proofへwrapする。
5. ceremony成果物と、実leafからEVMまでの性能評価を公開する。

関連資料:

- [Week 20資料一覧](../week20/)
- [再帰PCD仕様](../docs/protocol/recursive-pcd-v1.md)
- [nullifier仕様](../docs/protocol/nullifier-v1.md)
- [最新の実装進捗](03_実装進捗_再帰PCDと二重計上防止.md)
