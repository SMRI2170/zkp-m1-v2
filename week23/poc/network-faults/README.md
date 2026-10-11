# Besuの実P2P障害試験

```sh
python3 week23/poc/network-faults/run.py
```

前提：Besu/Java/ethers/solc（`../besu-local/README.md`）、統合実験の公開receipt hash結果。
起動前memory/swapを確認する。RPC/P2Pに加えloopback proxy port 31400–31415のうち12portを使用する。
新しいowner-only `.cache/week23/private/besu-network-faults-v1` に鍵・raw tx・node DBを保存する。
既存なら上書きせず停止する。再実行はBASEを変更する。
終了/例外時はノードとTCPプロキシを停止する。

2対2/3対1分断、復旧、200 ms/TCP read遅延、raw tx replay、fresh nonce競合、実HTTP403入口拒否をassertする。
約2〜3分かかる。60秒の復旧receipt deadlineを設け、超えたら失敗として残す。
その限界はネットワーク復旧の普遍的上限ではない。
署名ダイジェスト契約のみをdeployし、ZKP/VK/proofはdeployしない。
公開結果 `../../logs/besu-network-faults.json`。[報告](../../09_BCなし4レプリカとBesu障害比較.md)。
