# 署名付き観測の追加切り分け

前回の[workload](../pi4-euclidean-evaluation/workload/)を変更せずMac ARM64にnative buildし、観測数4→1→2→4→4の順で直列実行。4観測は3process中2完走・1OS swap増分の保護停止。
各runはwarmup1＋同一入力repeat3を予定（停止runは測定2まで）。processごとにsetupとobserver keyが新しく、完全に同一Witnessのcold反復ではない、合成batch3件の1秒間隔キュー。MacのCPU quotaは設定なし、Go GOMAXPROCS=1。
Mac soft guardはRSS4GiB／OS全体swap増分512MiB／timeout600秒。Pi cgroup測定やCPU25%値と混ぜない。

```sh
cd experiments/pi4-euclidean-evaluation/workload
CGO_ENABLED=0 go build -trimpath -o ../../../.cache/week24/workload-n4-mac .
```

repo rootでhost guardを使い、未使用out directoryへ `workload-n4-mac --count 4 --arrival-ms 1000` を実行。count1／2も別run。
metadataにはhost条件・binary/source hashを保存する。setup/VK/proof/private keysはRAMだけ、bodyを保存・公開・deployしない。

```sh
python3 experiments/pi4-observation-followup/collect.py --runs week24/logs/observation-followup --out week24/data/observation-followup
python3 experiments/pi4-observation-followup/plot.py --data week24/data/observation-followup --out week24/plots/observation-followup-mac
python3 experiments/pi4-observation-followup/check_results.py
```

collectは標準library、plotのみmatplotlib。memoryはwhole-run sampled process-tree RSSであり、phase memoryはnull。
Piでは今回重い試験を開始する前にuptime1分・watchdog inactiveを確認。手動再起動か予期しない再起動かは未確認。
IPv6で接続し、既存のhost keyを検査してruntime guardを復旧。SSH再起動や永続OS設定変更は行わない。
再起動原因やPiでの4観測proof成功を主張しない。
