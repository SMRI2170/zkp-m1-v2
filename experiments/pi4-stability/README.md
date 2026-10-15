# Pi実験前の確認

`preflight.py`はPi上で実行し、再起動で消える保護設定が不足している場合も、例外で終了する代わりに不足項目をJSONへ記録する。
不足があると終了コード1になる。設定を自動変更したり、SSHを再起動したりはしない。

```sh
python3 preflight.py --out /home/pi/.cache/week24/preflight-NEW --samples 3 --interval-s 30
```

出力先は未使用のディレクトリを指定する。`health.jsonl`に各時点、`summary.json`に観測範囲を残す。
`ready`は親cgroupの上限、swap使用0、OS利用可能メモリ1GiB以上、watchdogの内容・所有者・配置、SSHのOOM優先度、現在の電源状態などがすべて合格したときだけtrue。
watchdogのSHA256は既存の固定版を使い、欠測を正常扱いしない。journalが取得できなければOOM件数はnull。
低電圧の過去履歴と現在発生中のbitを区別する。journal一致件数0は、再起動原因の不存在の証明ではない。

これは短時間の抜き取り検査であり、長期安定性やSSH切断防止の保証ではない。
3回の確認を重負荷の前提条件に使う場合は、このコマンドの終了コード0を確認してから次へ進む。
実験runnerも独立にcgroup・watchdog・SSH・reserve・現在の電源状態を確認し、実行中の異常で子process群を止める。

保護が消えている場合、まず既存のruntime設定が残っていないか確認する。
完全に消えている場合のみ、Piに配置済みの`install_memory_guard.py`と固定SHAの`memory_watchdog.py`で復旧する。
既存ファイルを上書きする復旧・永続OS変更は行わない。詳細は[元の実装](../pi4-zkp-bench/install_memory_guard.py)。

公開出力は時刻・uptime・資源量・保護状態・journalの件数だけで、IP・serial・boot ID・journal本文・鍵は収集しない。

```sh
python3 -m unittest discover -s experiments/pi4-stability -p 'test_*.py'
```

## 事前確認と署名付き観測の実行をつなぐ

`launch_workload.py`と`preflight.py`を同じディレクトリに配置する。
Piにある旧runnerと署名付きworkload binaryのSHA256を照合し、**3回のpreflightが終了コード0で完了した後にのみ**systemdの子unitを起動する。
run directoryやtmpfsを再利用せず、旧partialを保持する。

```sh
sudo -v
python3 launch_workload.py --run-id workload-n4-NEW --count 4
```

run-idは小文字英数字とハイフンのみ（上のNEWは実際には未使用の小文字IDへ置換）。
起動後はCPU25%、子High384/Max512MiB、swap0、timeout1500秒、unit上限1530秒。
元の回路は変更せず、setupの待ち時間を含めた上限だけを確保する。設定復旧は別工程で、launcherは不足時に停止する。
起動時点で別の重負荷がないことも確認し、複数launcherを同時起動しない。
`sudo -v`の有効期限が切れた場合は、`sudo -n`が失敗しproofは開始しない。
今回のn4-v2実測は従来runnerを手動起動したもの。このlauncherの実機E2E成功とは扱わない。

## 4観測の追加runと過去の1／2観測を集計

回収はrunnerが出す`benchmark.jsonl`、`memory.jsonl`、`resource.json`、`filesystem-audit.json`、`stderr.log`だけを対象にする。
作業ディレクトリや鍵・proofを丸ごと回収しない。`metadata.json`は既存の`workload_metadata.py`で作り、今回の順序・timeoutに修正する。
`memory.jsonl`は必要に応じてgzipでbyteを保持したまま圧縮できる。

```sh
python3 experiments/pi4-stability/collect_scaling.py \
 --new-run week24/logs/pi-stability/eval-workload-n4-v2 \
 --out week24/data/pi-observation-scaling-v2
python3 experiments/pi4-euclidean-evaluation/plot_workload.py \
 --data week24/data/pi-observation-scaling-v2 \
 --out week24/plots/pi-observation-scaling-v2
```

新datasetには過去のn1/n2とn4 partialも含める。rawは元の場所を保持し、集計のためだけにignoredな一時領域へ複製する。
実施日・boot・setup/keyは異なる別run。条件の共通性を注記した記述的比較であり、観測数だけを変えた統制実験や十分な独立反復ではない。
CSV/JSONLには失敗とwarmupを残し、図は完走runだけ。元のデータ・図・manifestは上書きしない。
