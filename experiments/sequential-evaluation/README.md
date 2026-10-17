# 順次評価ジョブ：チャットで待たずに実行・記録する

`run.py start`は別processで順次ジョブを開始して直ちに戻る。
ビルド、CLI driver生成、Pi準備確認、配置、8構成とCircomの2 prover構成の21件測定、回収、集計、図、CIログ確認を順番に実行する。
途中失敗してもCSV/JSONを更新し、依存しない工程と収集処理は進める。
未知の研究実装をAIが自動作成するプログラムではない。実装済み8構成とCircomの2 prover構成を測定対象とし、Noirはsource adapterを生成する。残る8構成は未実装／前提不足の理由を記録する。

## 起動

```sh
python3 experiments/sequential-evaluation/run.py start \
 --tag seq-NEW --out .cache/week24/sequential-jobs/seq-NEW
```

tagは小文字英数字とハイフン、20文字以下。NEWは実際の小文字の未使用名へ置き換える。
同じjob/build/run directoryを上書きしない。workerはMac/Linuxのローカルprocessであり、端末の終了から独立するが、ホストの終了・再起動・スリープを超えて動く保証はない。
プログラムのsource hashを記録し、実行中に変更された場合は後続工程を止める。

SSHは既存の認証環境を使用する。必要な場合、起動環境に以下を設定する（passwordをplanやコマンド引数へ入れない）：

- `EVAL_SSH_TARGET`：接続先。既定は `pi@raspberrypi.local`。配置先は既存Pi環境の `/home/pi/.cache/week24`。
- `EVAL_KNOWN_HOSTS`：検証済みknown_hosts。既定はignoredな `.cache/week24/private/known_hosts`。
- `EVAL_HOST_KEY_ALIAS`：既存known_hostsのaliasが必要な場合。
- `EVAL_SSH_IPV6=1`：IPv6を指定する場合。
- `EVAL_SSH_PASSWORD`：必要な場合のみ。SSH_ASKPASSへ環境経由で渡し、Gitやplan・CSV/JSONへ保存しない。
- `EVAL_SUDO_PASSWORD`：必要な場合のみ。未指定時はSSH passwordを利用。sudo stdinへ渡す。

新しいsudo権限や永続設定を追加せず、メモリ保護設定を自動的に緩めない。known-host検証を無効化しない。

## 保存される結果

|ファイル|内容|
|---|---|
|`status.json`|job全体と各工程の状態・開始／終了・終了コード・理由|
|`results.csv`|各工程の状態と実行時間。測定値がない欄は空欄|
|`events.jsonl`|各工程の状態遷移|
|`pi-readiness.json`|実際に取得した準備状態、または接続失敗理由|
|`data/samples.csv` / `.jsonl`|回収できた実測sample。未測定ならheaderのみ／空ファイル|
|`data/summary.json`|実測の統計。未測定なら空配列|
|`measurement-status.json`|回収run数・完走数・取得状況|
|`plots/`|完走cohortがある場合だけ生成するPNG/SVG|
|`*-capability.json`|未対応方式の理由。proof未実行を明記|
|`ci-results.csv` / `.json`|対象commitのCI状態とURL|
|`private/*.log`|コマンド／CIの詳細ログ。owner-only、公開前の確認が必要|

`completed`はその工程の終了であり、buildやprepareの完了はproof成功ではない。
`blocked`は前提未成立、`unsupported`はこのprogramの未対応、`failed`は実行失敗、`timed_out`は時間制限、`interrupted`は中断。
未対応工程を含むjob全体は`partial`となる。実測0件を0秒／0byteの成功に変換しない。

状態を読む場合も、その場で完了待ちをしない：

```sh
python3 experiments/sequential-evaluation/run.py status --job .cache/week24/sequential-jobs/seq-new
```

## 保護と失敗時

Piのprobeがready=falseなら配置・測定へ進まない。guard復旧・SSH再起動・OS変更をこのjobで自動実施しない。
各測定は既存launcherの3 snapshot preflight・CPU25%・子High192/Max256MiB・Swap0・親slice・watchdog・SSH保護を使用する。
測定は1方式ずつで、失敗／接続断後に次の測定を自動開始しない。通信断の場合はPi側unitが実行中の可能性があり、自動再送しない。
Pi側は既存runtime上限で停止する。再実行前に残存unit・private tmpfs・partialを確認する。

1process/key内で7入力warmup＋7入力×3回を測る。独立cold21runではない。
Noirはsource adapter生成まで。CircomはsnarkjsとRapidSnarkの2構成をcircom/へ保存し、共通native verifierで測定する。IVCの別系列、その他backendの対応は #61/#55 の残件。
実capture・実座標・private key・使い捨てsetup/VK/proof実体をGitへ追加・公開・deployしない。
研究PoCでありDRIP trust chain、sensor honesty、observer hardware／航空機認証は保証しない。

## 既存の一時保護設定を復旧して再開する

ユーザーが復旧を指示した場合は、`start`に`--restore-guards`を付け、新しいtag/outで起動する。
この指定時だけ、Piの既存installer/watchdogの固定hashとruntime配置を調べ、完全に未配置の場合に既存installerを1回実行する。
部分配置・hash不一致・接続断は`guard-restoration.json`へ保存して停止し、自動再送・上書きはしない。
SSH再起動や永続OS変更はしない。復旧後もready probeと各launcherの事前検査を必須とする。
過去のjobやpartial測定は保持する。

## 既存試験の回収だけを再実行する

終了済みjobの`deployment.json`とtagを照合して配置済み状態を参照し、collect/plotだけの新planを使う。
`reuse-deployment`工程は参照確認だけで、新しい配置やproof実行を行わない。
SSHの終了255等を保存先なしと見なさず、`fetch-status.json`にtransport errorを記録する。
remote directoryを1つも確認できなければ成功にしない。回収失敗後も、既に取得した完走cohortがあれば図化できる。
