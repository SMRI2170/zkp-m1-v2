# 実装進捗：再帰PCDと二重計上防止

更新日: 2026-09-28

## 目的

この研究の最終目標は、複数の登録済み端末が行った UAV / Remote ID
観測を、個人位置・端末ID・RSSI値を公開せずに一つの証明へ集約し、EVMで
検証できるようにすることである。

最終証明が意味することは次の通りである。

> 同じドローン・同じ時間窓・同じ方針について、登録済み端末だけが各1回
> ずつ参加し、観測の整合／矛盾の件数と判定結果が正しく集計された。

## 今回までに実装したもの

### 1. 最終proofの共通仕様

- `final-attestation-v1` の9個の公開入力ABIを固定した。
- EVM上の `sessionId` は proof 入力ではなく、version / drone / time bucket /
  policy から `keccak256(abi.encode(...))` で一意に導出する。
- v1用の入力範囲チェック、session再利用拒否、version付き最終recordを持つ
  Solidity registry とテストを追加した。

仕様: [`../docs/protocol/final-attestation-v1.md`](../docs/protocol/final-attestation-v1.md)

### 2. 端末の登録と二重計上防止

- `memberRoot` により、登録済み端末の公開鍵だけを受け入れる Merkle
  membership 回路を実装した。
- session固有の `nullifier` を導入した。同じ端末が同一sessionで再度参加
  しようとすると、そのleafは既にゼロでなくなり証明できない。
- `PairCircuit` を追加した。これは2端末を次のように回路内で順序付きに
  消費する。

```text
oldRoot -- 端末 A --> intermediateRoot -- 端末 B --> newRoot
```

2台目は `intermediateRoot` に対して未使用であることを証明するため、端末Aを
再利用することはできない。

実装: [`../aggregator/nullifier`](../aggregator/nullifier)

### 3. 固定鍵の再帰検証

既存の `chainpoc` は教育用PoCであり、前段の検証鍵をwitnessとして受け取る
ため、本番用の固定PCDとしては使えないことを確認した。

そのため `PinnedBLS12ProofCircuit` を実装した。

- BLS12-377の子proofをBW6-761回路の中で再帰検証する。
- 子のverification keyはprover入力ではなく回路定数として固定する。
- 別の鍵で作られた有効proofを渡しても拒否される回帰テストを追加した。

実装: [`../aggregator/pcd/pinned_bls12.go`](../aggregator/pcd/pinned_bls12.go)

### 4. 2入力の順序付きPCDノード

`NodeBW` を実装した。固定された子VKで左右2つのBLS12-377 proofを回路内で
検証し、以下を強制する。

```text
left.session metadata == right.session metadata
left.newNullifierRoot == right.oldNullifierRoot
out.counts == left.counts + right.counts
```

これにより、別sessionの証明を混ぜたり、途中のnullifier状態を飛ばしたり、
件数を任意に増やしたりできない。

実装: [`../aggregator/pcd/node_bw.go`](../aggregator/pcd/node_bw.go)

## 検証済みの内容

以下はローカルで成功している。

```text
cd aggregator && go test ./...
cd contracts && npm test
```

- Go: membership / nullifier / curve-cycle / 固定鍵拒否 / NodeBWの正常・改ざん
  拒否テスト。
- Solidity: 36件のHardhatテスト。ABI、session、policy/root制約、proof再利用
  拒否を含む。

## 未完了（本番化のために必要なもの）

1. `NodeBW` のproofを受ける反対側の `NodeBLS` と、両ノードの固定リリース鍵
   成果物を作る。
2. 現在のBN254 leaf観測proofをPCD状態へ変換する `BridgeBW` を実装する。
3. 順序付きappendではなく、任意の二つの既存nullifier集合を非交差であると
   証明して統合するbinary unionを実装する。
4. PCD rootを検証して9入力のEVM向けGroth16/BN254 proofを発行する `FinalBN` を
   実装・ceremonyする。
5. 実際のleaf proofからEVM登録までを通すE2E性能測定と、公開artifactを整備する。

したがって、今は「安全な状態遷移と固定鍵再帰検証の基盤」までは実装済みであり、
「実leafからEVMまでの本番proof一本化」は未完了である。
