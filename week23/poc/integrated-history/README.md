# オフチェーンGroth16検証→3署名→Besu履歴

```sh
cd week23/poc/private-pcd
go build -o ../../../.cache/week23/private-pcd-integrated .
cd ../../..
python3 week23/poc/integrated-history/run.py
```

前提：既存の合成 `.cache/week23/private/{baseline,pcd,pcd-fork-normal,pcd-fork-outlier}`、
BesuとJavaの固定版（`../besu-local/README.md`）、contractsのethers/solc依存。
新規fixtureやsetupを自動生成しない。欠落/mismatchは停止して既存artifactを保存する。
`main.go/relations.go/go.mod/go.sum` の既存manifestとの一致を検査し、ローカル信頼VKのhashをpinする。
受信者のtrust設定は `receipt_worker.py` のWORKに固定し、入力側の設定を信頼しない。

新しいowner-only `.cache/week23/private/integrated-history-v1/` を作成する。
既存なら停止して保存する。再実行にはrun.pyのBASEとreceipt_worker.pyのWORKを新しい同じ場所にする。
memory/swapとloopback portを起動前に確認する。全ノードはfinallyで停止する。
公開ログは `../../logs/integrated-history.json`。鍵・VK・proof・raw tx・DBはGitに含めない。

`VerifiedHistory.sol` は実験用の署名/資格/期限/履歴レジストリで、Groth16 verifierではない。
正常・競合・期限・改竄・資格変更を実Besu上でassertする。[報告](../../08_ZKP検証からBesu履歴への統合と資格管理.md)。
