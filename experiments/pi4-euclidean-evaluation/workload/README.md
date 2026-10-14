# 合成観測数・hash・署名・session拘束の追加負荷

gnark0.16.3／gnark-crypto0.21.0、Groth16 BN254。
観測数1／2／4で別の回路をcompileし、1warmup＋3repeat、単一proofへまとめる。
すべてRAM-onlyの使い捨てlocal setup。setup鍵・observer秘密鍵・VK・proof実体は保存／Git公開／deployしない。

各観測は同じ合成座標3–4–5だが、batch count・Session・Policy・claimed RID・観測index・座標・d2/rをdomain付きMiMCで束縛し、
RAM内に生成するtest EdDSA鍵で署名する。回路で距離・整数範囲・各署名と集合digestを検査する。
publicはSession／Policy／claimed RID／集合digest／署名者public key。署名者keyは検証者が期待するpublic statementの一部。
PolicyはIDの署名拘束であり、資格・期限・失効規則の実装ではない。資格レジストリ、鍵失効、DRIP trust chain、sensor honesty、hardware／航空機認証の実装ではない。
低entropyな座標のpublic digestについて辞書推測耐性を主張しない。

session／policy／座標／署名の改変、およびindexの違う観測のコピー（count>=2）をconstraint solverが拒否する。
同じproofのsession／digest改変は実verifierで拒否する。破損proofはdecoderまたはverifierで拒否する。
無効assignmentを強制してproof生成した検査ではない。

```sh
cd experiments/pi4-euclidean-evaluation/workload
go test ./...
CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -trimpath -o ../../../.cache/week24/week24-observation-workload .
```

Piではcollection runnerの同じguard／CPU25%条件で `week24-observation-workload --count 1 --arrival-ms 1000`（2／4も別run）を実行する。
個別distance circuit3方式とは別datasetに保存する。署名の生成はsetup後1回で、witness測定はassignment→gnark witness変換。
署名生成時間・実capture・BLE受信・ネットワーク包絡はフローに含めていない。
処理時間やconstraint数の観測数scalingを測るための合成追加負荷であり、研究PoC全体のend-to-end性能とは別。

追加live queueは3件の合成batchを1秒間隔で投入する。到着jitter・dequeue時のwait／queue depthを実測し、capacity3で有限に保つ。
count2／4では1batch内に2／4観測があり、1観測/sと混同しない。長期1Hz安定性やBLEセンサーの実負荷試験ではない。
