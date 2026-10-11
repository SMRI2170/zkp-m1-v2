# ローカルBesu QBFT機能・確定遅延の測定

Besu 26.9.0公式tar.gzと.sha256を `.cache/week23/besu-tools/` に取得し、checksum一致を確認して展開する。
取得URL/hashは `../../manifests/besu.json`。既存Homebrew OpenJDK 26.0.2を使用する。
Python標準ライブラリと `contracts/node_modules/ethers` を使う。

```sh
python3 week23/poc/besu-local/native_qbft.py
```

scriptは新しいowner-only `.cache/week23/private/besu-qbft-26.9.0-v2/` を作成し、genesis/4-validator鍵/転送用鍵をローカル生成する。
以前のdirectoryがあれば停止して保存する。再実行にはscriptのBASEを新しいdirectoryへ変える。
鍵・raw signed transaction・チェーンDB・ノードログはGitへ追加しない。
RPCは127.0.0.1:18545–18548、P2Pは127.0.0.1:30431–30434に限定し、discoveryを無効化する。
各JVMは最大384MiB heap/2 processors。起動時メモリと既存portの占有を確認して実行する。
終了/例外時に今回起動したvalidator processを停止し、dataを保存する。

測定は1 warmup＋20 EOA自己転送。2秒block period、receipt poll 50ms、gasPrice=0のローカルfixture。
4ノードの同一block receiptを確認し、1台停止時の3ブロック以上の進行、2台停止時の12秒間の停止を確認する。
これは1台のMac/単一運営者のQBFT機能PoCであり、独立運営者や悪意validator/検閲耐性の実証ではない。
使い捨てZKP VK/proofはデプロイせず、ZKP検証Gas/同等回路のオンチェーン比較は測定しない。
EOA transferの21000 GasをZKP verification Gasとして扱わない。

## #42 共同署名・競合・共通履歴

```sh
python3 week23/poc/besu-local/conflict_comparison.py
```

`ConflictHistory.sol` をsolc 0.8.26 / evmVersion parisでコンパイルし、新しい
`.cache/week23/private/besu-conflict-42-v1/` の4validatorへデプロイする。
署名鍵は合成fixture専用。Groth16 VK/proofをデプロイする実験ではない。
同じ2/3署名の競合候補2件、6否定ケース、warmup 1＋10成功ケースを検査する。
4ノードの同一receipt・状態・イベント履歴をassertし、公開結果を `../../logs/conflict-comparison.json` に書く。
既存directoryがあれば上書きせず停止する。再実行時はPythonの `network.BASE` を新しい名前へ変更する。
事前にmemory/swapとport占有を確認する。詳細とADRは [07](../../07_BCなし共同署名とBesu共通履歴の比較実験.md)。
