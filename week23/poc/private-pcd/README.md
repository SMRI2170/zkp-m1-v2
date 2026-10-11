# 秘密非共有の有限3段一般再帰（fallback）

`relations.go` は既存chainpocの相対許容帯関係のコピー。
今回の回路はfixtureのversion/session/RID/timeBucket/policyを定数拘束し、
A/B/Cの固定member順と9項目の公開statementを拘束する。任意深さのPCDではない。

前段VKは回路定数。ローカルのtrusted setup出力から読み込み、今回の次段回路をcompileする。
本PoCはこのローカルのsetup/VKディレクトリを信頼する。ネットワークから渡された任意VKを許可するプロトコルではない。
端末署名・外部member registry・expiry・session replayストア・ネットワーク認証はまだ実装していない。
同じ合成fixtureをソースから推測できることと、proofが元Witnessを含まないことを区別する。

```sh
GOMAXPROCS=2 go build -C week23/poc/private-pcd -o ../../../.cache/week23/private-pcd .
mkdir -p .cache/week23/private/pcd
chmod 700 .cache/week23/private/pcd
GOMAXPROCS=2 .cache/week23/private-pcd prove .cache/week23/private/pcd 1
# 以下は実際の再帰setupを行う。監視下で逐次実行する。
python3 week23/poc/private-pcd/resource_run.py 2
python3 week23/poc/private-pcd/resource_run.py 3
GOMAXPROCS=2 .cache/week23/private-pcd verify .cache/week23/private/pcd 3
```

`plan` はcompileまで。生成・最終verifyの証拠に数えない。
次processが読む前段ファイルは `vk.bin` / `proof.bin` / `public.bin`。
private assignmentは保存せず、setup/CCS/PK/VK/proofはignored owner-onlyディレクトリに保存する。
setupはdisposable test-only fixture。公開・デプロイしない。
公開statementからcount・member集合・sessionはリンクできる。

ログの `negative-solver` は不正assignmentの制約不充足を確認するもので、改竄proofのverify試験と区別する。

`verify-host PRIVATE_DIR STAGE` は合成時計でfresh/expired/future/replayのhost判定を試す。
このTTLはfixture policyであり、ブロックチェーンの鮮度保証ではない。
`baseline PRIVATE_DIR STAGE` はA/B/Cそれぞれのsingleton proofを生成し、
`joint PRIVATE_DIR` は全3proof検証後、同じ提出集合へ3つのEd25519署名を生成・検証する。
元の `negative-solver` ログは初回版、修正版の `negative-prover` は実Groth16 proverで不正assignmentを拒否する。

完了したproofについて:
```sh
python3 week23/poc/private-pcd/check_transport.py
python3 week23/poc/private-pcd/signed_transport.py
```
`check_transport.py` はバイト改竄と合成canary検査。
`signed_transport.py` は既生成proofに対する署名転送harnessで、元proofを再生成しない。
それぞれowner-onlyの新規fixture directoryを作るため、既存directoryは削除せず別の実行先を用意する。
script中のbinary pathは実行例では `private-pcd-bench`。通常の単一buildで使う場合はそのbinary名に合わせる。
`bench-singleton` はwarmup 1回＋20回のprove/verify。再帰proofの反復benchはまだ行っていない。


追加の分岐/永続受信実験（repo rootから実行）:

```sh
(cd week23/poc/private-pcd && go build -o ../../../.cache/week23/private-pcd-forks .)
GOMAXPROCS=2 .cache/week23/private-pcd-forks fork-prove .cache/week23/private/pcd .cache/week23/private/pcd-fork-normal normal
GOMAXPROCS=2 .cache/week23/private-pcd-forks fork-prove .cache/week23/private/pcd .cache/week23/private/pcd-fork-outlier outlier
python3 week23/poc/private-pcd/persistent_gate.py
```

元A/B/C proofとsigned_transportの固定roster/keysが必要。以前の実験directoryは保存し、同名への再実行は拒否する。
分岐では元source/deps hashと再compile CCSのbyte一致を要求してsetup fixtureを明示検査する。
保存source metadataが異なると失敗する。異なる回路や任意のsetupキャッシュを自動採用しない。
永続ゲートは合成clock・固定メンバー・trusted local VK。独立DB間の合意ではない。
