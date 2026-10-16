# Issue #58：均等反復の距離回路ベンチ

既存n=20／n=7の結果を変更せず、同じ合成7入力を各3回測定する新ドライバ。
対象は現時点でgnark Groth16/PLONK、arkworks、Halo2 IPA/KZG、Spartan、Bulletproofs、Plonky3の8構成。
元の回路・否定テスト・ZK設定は保持し、hash照合した旧sourceをignored build directoryへ複製してloopと計測metadataだけを変更する。
未対応の方式を測定済みにはしない。Kimchi/Binius64/Jolt・CLI系の対応、IVC系列評価、未完了backendは残件。

## 条件

- protocol: `distance-u16-balanced-v1`。
- 7入力それぞれ1回warmup、その後case0..6を3巡。合計28proof、集計21proof。
- これは1process・同じsetup/keyでのwarm反復。独立cold run21回ではない。
- sample IDは0..27、case IDはsample ID % 7、測定repeat IDは0..2。
- Pi：CPUQuota25%、1CPU affinity、GOMAXPROCS/RAYON/OMP各1。
- 各unit High192/Max256MiB、Swap0、親High1200/Max1536MiB、OS reserve1GiB、外置きwatchdog・SSH -900。
- 全体メモリには起動・setup/load・warmup・負例も含む。平均フローはログのwitness（分離時）+prove+verify。
- arkworks/Bulletproofs/Halo2はwitness処理がprove内。gnark/Spartan/Plonky3はwitness分離。
- compile/setup/loadは別。gnarkのsetupはMacで実施し、Piのrunはcompile/load後に測定。RustはPi内setupを別phaseで記録。
- 証明形式、curve、security設定、setup条件は方式ごとに異なり、nを揃えても完全同一条件とはしない。

## ビルドとローカル正当性確認

```sh
python3 experiments/unified-distance-bench/build.py gnark --build-id host-new
python3 experiments/unified-distance-bench/build.py arkworks --build-id host-new
python3 experiments/unified-distance-bench/build.py halo2-ipa --build-id pi-new --target aarch64-unknown-linux-musl
```

build-idは未使用名。同名directoryは拒否する。元source/dependency manifestのhash不一致時も停止する。
Goは既存107入力の回路検査を実行。生成バイナリと依存lockは`.cache/week24/unified-build/`内。
Rustは既存target cacheを再利用し、新ソースをビルドする。実行用binaryは新directoryへコピーする。
ビルド成功とPiでのproof成功は別。Mac実行もPi性能値として扱わない。

新gnark binaryは既存fixtureのsource digestと一致しないため、新しい使い捨てsetupを生成する。
`unified-gnark setup groth16 PRIVATE_NEW_DIR`、次に`unified-gnark bench groth16 PRIVATE_NEW_DIR`。
PLONKも同様。親をignored・owner-onlyにする。proof保存はなく、setupはローカル限定。fixtureは意図的に保持し、削除・再利用を自動化しない。

## Pi実行

既存`run_guarded_evaluation.py`と`preflight.py`を使う。launcherは両helperとbinaryのSHA256を検証し、
3 snapshot/60秒のpreflightが全合格した場合だけ起動する。不足設定を自動変更しない。
新launcherはファイルlockで直列化し、旧runnerを含む実行中week24 unitがあれば開始しない。
Piに以下を配置する：新binary・build.json、`launch.py`。gnarkの場合は新private fixtureもowner-onlyで配置。
元helperは`experiments/pi4-euclidean-evaluation/run_guarded.py`（Pi名`run_guarded_evaluation.py`）、
`experiments/pi4-stability/preflight.py`。hashの合う既存配置を優先し、黙って上書きしない。

```sh
sudo -v
python3 launch.py --run-id balanced-arkworks-new \
 --binary /path/to/unified-arkworks --build-metadata /path/to/build.json
# gnarkでは追加で --backend groth16 --fixture /path/to/private-new-fixture
```

runtime上限1200秒、unit1230秒。Pi4GBで安全に終わらなければpartialを残す。保護条件を緩めない。
回収対象は`benchmark.jsonl`、`memory.jsonl`、`resource.json`、`filesystem-audit.json`、`metadata.json`のみ。
private fixtureやtmpfsを丸ごとGitへ回収しない。

## 集計と図

```sh
python3 experiments/unified-distance-bench/collect.py --runs week24/logs/unified-distance --out week24/data/unified-distance-new
python3 experiments/unified-distance-bench/plot.py --data week24/data/unified-distance-new --out week24/plots/unified-distance-new
python3 -m unittest discover -s experiments/unified-distance-bench -p 'test_*.py'
```

CSV/JSONLに全sampleとwarmupを保持。旧n=7/20は新protocolへ取り込まない。
21件の件数だけでなく、入力別3件・順序・成功summary・正常resourceを照合する。
欠測はnull／空欄、停止・truncatedはpartial。完走cohortがなければ性能図を生成しない。
平均・中央値・標本SD・入力別統計を保存。図は点＋平均±SD・中央値、メモリ平均/peak・proofサイズを表示。
SDは1process内の異なる入力と反復を含む記述統計で、信頼区間ではない。新集計では少数標本のp95/p99を出さない。旧Go形式のraw summaryに含まれるpercentile値を比較の根拠には使わない。

研究PoCの合成距離計算であり、DRIP trust chain・観測の真実性・hardware/航空機認証を保証しない。
実capture、実座標、private key、setup/VK/proof実体は公開しない。

Spartanのwitness時間には`is_sat`のsanity checkが含まれる。各方式のfield変換・oracle・public witness抽出にはtimer外の区間がある。`phase_notes`で差分を保持し、完全に同じ工程の時間と断定しない。
