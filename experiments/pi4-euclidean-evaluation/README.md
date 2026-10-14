# Week24追加評価の収集

合成ユークリッド距離（CASES[1]＝3–4–5）の同一入力を、Kimchi／Binius64／Joltで
warmup1件＋測定3件、同じCPU25%／1 compute thread／CPU affinity0で実行する。
1process内の短い反復。独立cold trialや長期／大量反復の代わりにはならない。
元の回路・ZK設定・正常proofの改竄検査・負例検査を維持し、追加の観測点だけを挿入する。

`build.py`は前の[固定実装](../pi4-euclidean-next/)のhashを確認し、ignored directoryへinstrumented sourceを生成する。
別binary名を使い、過去のbinary／ログ／元sourceを書き換えない。既存の固定dependencyとlockを使う。
Kimchiはpublic fieldのserde Serialize実装がないため、公開入力サイズは固定幅LE field encoding（2×32B）を数える。
Binius64は2×64bit word（16B）、Joltはbincode1.3 tuple（d2/r/output/panic、18B）。共通ネットワーク形式ではない。
VKはKimchi rmp-serde index（生成SRSは別）、Binius64のserialized verifier seed/config（検証器を再構築）、Jolt bincode2 verifier preprocessing。
VKのbyte数だけ保存し、その実体をファイルへ出さない。SRS／protocol envelope全部込みの比較でもない。

```sh
python3 experiments/pi4-euclidean-evaluation/build.py kimchi --target aarch64-unknown-linux-musl
python3 experiments/pi4-euclidean-evaluation/build.py binius64 --target aarch64-unknown-linux-musl --portable-blake3
python3 experiments/pi4-euclidean-evaluation/build.py jolt --target aarch64-unknown-linux-musl
```

生成binaryはignored `.cache/week24/target-<framework>-next/aarch64-unknown-linux-musl/release/week24-euclidean-<framework>-evaluation`。
Joltは前回hash固定の公開guest ELFを`--elf <path> --quick`で読む。quickでも正常4件（warmup1＋測定3）・root low/highの不正2件を実行する。
Kimchi／Binius64は既存不正6件に加えて、構築／population後のprivate assignmentを壊して直接proverへ渡す。
結果は `prover_error`／`prover_panic`／`verifier_rejected` を区別する。生成できなかった場合をverifier拒否とは記述しない。

Piへのrunner配置とguardian設定確認後、1方式ずつ未使用run/unit名で実行する。

```sh
sudo systemd-run --unit=week24-eval-NEW --wait --pipe \
 -p User=pi -p Slice=week24.slice -p MemoryAccounting=yes \
 -p MemoryHigh=384M -p MemoryMax=512M -p MemorySwapMax=0 \
 -p OOMScoreAdjust=500 -p OOMPolicy=stop -p CPUWeight=10 \
 -p CPUQuota=25% -p RuntimeMaxSec=930 \
 python3 /home/pi/.cache/week24/run_guarded_evaluation.py \
 --out /home/pi/.cache/week24/runs/NEW --work-dir /dev/shm/week24-eval-NEW \
 --timeout-s 900 --memory-high-mib 384 --memory-max-mib 512 -- \
 env EVAL_CASE=1 EVAL_REPEAT=3 EVAL_WARMUP=1 /path/to/binary
```

KimchiはHigh192／Max256MiB。親High1200／Max1536MiB・swap0・available1GiB・外置きwatchdog・SSH -900は前回と同じ。
runnerが実cgroup `cpu.max` を読みCPU25%を確認する。telemetry例外・OOM・低電圧は成功扱いにしない。
fresh owner-only tmpfs work directoryの書込を監査し、空の場合だけ削除する。不明な生成ファイルは保持し、Gitへ回収しない。
全OSのファイルアクセスやside-channelを検査したとは主張しない。

## 後から集計・描画

各runの`benchmark.jsonl`・`memory.jsonl`・`resource.json`・`filesystem-audit.json`を回収し、以下でpublic-safe metadataを添える。

```sh
python3 experiments/pi4-euclidean-evaluation/metadata.py kimchi \
 --run-id NEW --out week24/logs/pi-euclidean-evaluation/NEW/metadata.json
python3 experiments/pi4-euclidean-evaluation/collect.py \
 --runs week24/logs/pi-euclidean-evaluation --out week24/data/euclidean-evaluation
python3 experiments/pi4-euclidean-evaluation/summarize.py --data week24/data/euclidean-evaluation
python3 experiments/pi4-euclidean-evaluation/plot.py \
 --data week24/data/euclidean-evaluation --out week24/plots/euclidean-evaluation
```

collectはPython標準libraryのみ。plot時だけmatplotlibを使う。
JSONLと同じ内容のCSVを出す。CSVの欠測は空欄、JSONはnull。失敗／partialとwarmupを残し、描画時に除外する。
`samples` は1proofのphase時間・サイズ・prove区間sampled memory、`trials` は初期化・whole-unit資源・artifact size、
`memory` はflattenした全時系列、`checks` は拒否結果、`queue_model_1hz` は測定service timeによるFIFOモデル。
`coverage.json`で実測／source確認／モデル／未測定を区別する。

phase markerとmemoryは同じPiのwall_time_nsで対応づけ、処理時間自体はInstant／monotonicで測る。
prove区間のpeakはsampled値（通常数十msの実sampling間隔）、whole-unit peakはkernel値。
区間平均は区間内sample間の観測spanを時間加重する。起動／verify／negative-testのmemoryをprove区間に混ぜない。
`proof_randomness_new` はRAM内の非暗号学的fingerprintによる非同一性diagnostic。digestやproof自体を保存せず、ZK安全性の証明とはしない。
初期化時間はinstrumented setupで、Binius／JoltはVK serializationも含む。cold executable loadやnetwork setupとは別。

hash／署名／session拘束・観測件数1／2／4の追加負荷は[gnark workload](workload/README.md)で別datasetへ収集する。有限3件の1batch/s synthetic queueも別に実測する。
RSSI、他方式への同等workload移植、長期1Hz／leak／side-channelは残件。
claimed RID／observer statement以外のDRIP trust chain、sensor honesty、observer hardware、航空機認証を評価しない。

`rendered/`は実際にbuildしたRust sourceの監査用snapshot（manifest／lockはdriverで生成する）。
`check_results.py`は保存evidenceの検査、`test_collect.py`はwarmup・失敗・欠測・phase区間の解釈を検査する。


署名workloadの再集計・描画：

```sh
python3 experiments/pi4-euclidean-evaluation/collect.py --runs week24/logs/pi-observation-workload --out week24/data/observation-workload
python3 experiments/pi4-euclidean-evaluation/summarize.py --data week24/data/observation-workload
python3 experiments/pi4-euclidean-evaluation/plot_workload.py --data week24/data/observation-workload --out week24/plots/observation-workload
python3 experiments/pi4-euclidean-evaluation/plot_memory.py --data week24/data/euclidean-evaluation --out week24/plots/euclidean-evaluation-memory
```

memory tableはrun_idでtrialsの条件metadataとjoinする。`queue_observed_1hz`と`queue_model_1hz`を混同しない。
workload metadataは`workload_metadata.py --count N --run-id NEW --out <path>`で生成する。

再起動でtruncatedとなった4観測のraw memoryはbyte単位で保持したgzip archive。collectはmemory.jsonl.gzにも対応し、parse anomalyをschemaへ明記する。
