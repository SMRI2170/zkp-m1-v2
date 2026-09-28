# Week 22：実装計画 — 本番proof一本化

開始日: 2026-09-28

## Week 22のゴール

Week 20で作った再帰proofチェーンPoCと、Week 21で作ったmembership・nullifier・
固定鍵・2入力マージを、**実際の端末leaf proofからEVM最終recordまで通る一本の
検証経路**へ近づける。

最終的に目指す流れは次の通りである。

```text
端末のBN254 leaf proof
  → BridgeBW（leafの真正性・端末membership・nullifier遷移）
  → NodeBW / NodeBLS（複数端末の再帰集約）
  → FinalBN（9入力Groth16/BN254 proof）
  → FinalAttestationRegistryV1（EVM final record）
```

## 現在の前提

すでに存在するもの:

- 端末観測のBN254 leaf circuit と個別proofの検証。
- `memberRoot` membership と、1端末・2端末順序付きのnullifier遷移。
- BLS12-377 proofをBW6-761で固定鍵再帰検証する部品。
- 左右2子のstateを順序付きに結合する `NodeBW`。
- v1の9入力ABI、V1 registry、artifact manifest、CIテスト。

まだ存在しないもの:

- 実BN254 leaf proofをPCD stateへ変換するBridge。
- `NodeBW` のproofを受ける反対側 `NodeBLS`。
- EVM向けの実FinalBN circuit / verifier artifact。

## 実装順序

### Step 1 — PCD状態の固定

`BridgeBW`、`NodeBW`、`NodeBLS`で共有する内部stateを固定する。

```text
(version, droneId, timeBucket, policy, memberRoot,
 oldNullifierRoot, newNullifierRoot,
 consistentCount, suspiciousCount)
```

完了条件:

- stateのフィールド順、値域、hash domainを仕様に記載する。
- `NodeBW` の入力・出力がこのstateと一致する。

### Step 2 — BridgeBW

実BN254 leaf proofを回路内で検証し、leaf公開信号からPCD stateを作る。

Bridgeが必ず確認すること:

1. leaf proofのVKはrelease artifactに固定されている。
2. `within30_and_detected == 1` と `drone_auth_ok == 1`。
3. 端末公開鍵が `memberRoot` のmemberである。
4. 同端末のnullifierを `oldRoot` から `newRoot` へ一度だけ遷移する。
5. `consistency_ok` を `consistentCount` または `suspiciousCount` のどちらか一方へ
   加算する。

完了条件:

- 正しい実leafでBridge proofを生成・検証できる。
- 未登録鍵、古いroot、重複端末、署名なしRemote ID、改ざんしたleaf公開値を拒否する。

### Step 3 — NodeBLSと曲線サイクル

`NodeBW`のproofをBLS12-377回路で検証する `NodeBLS` を実装する。

完了条件:

- `BridgeBW → NodeBLS → NodeBW` の少なくとも3段を連結できる。
- 子VKはすべてproof witnessではなく回路定数として固定される。
- 異なるdrone / bucket / policy / memberRoot / root連結の不一致を拒否する。

### Step 4 — FinalBN

root PCD proofを検証し、`final-attestation-v1` の9入力を出すBN254 Groth16回路を作る。

完了条件:

- countsからverdictを回路内で導く。
- verifierが `IFinalAttestationVerifierV1` ABIに一致する。
- `FinalAttestationRegistryV1` が実proofを受理する。

### Step 5 — ArtifactとE2E

- circuit source / R1CS / zkey / vkey / Solidity verifierをmanifestへ登録する。
- trusted setupの手順・参加者・hashを公開する。
- 実leaf 2台以上からEVM finalizationまでの時間、proof size、gasを測定する。

## 完了の判定

Week 22は、次のE2Eが通った時点で完了とする。

```text
登録端末Aの実leaf proof ─┐
                          ├─ 再帰集約 ─ 最終BN254 proof ─ EVM record
登録端末Bの実leaf proof ─┘
```

加えて、同一端末の二重参加、未登録端末、異なるsessionの混入、proof/VKの差し替え、
公開入力の改ざんが全て失敗することを自動テストで示す。

## 注意点

- `NodeBW` は現時点で順序付きstate mergeまで実装済みであり、任意の二つの既存
  nullifier集合をunionする機能はまだない。
- ceremony前の鍵・proofは研究用であり、実運用の信頼設定ではない。
- FinalBNをmock verifierで通すだけでは完了にしない。実Groth16 verifierと
  artifact hashが揃って初めてEVM接続完了とする。
