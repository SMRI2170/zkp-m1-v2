# Pi4 gnark Groth16最小スモーク・計測runner

対象はtoy `0 <= x < 256; y=x^3+x+5`。xはprivate変数、yはpublic。
公開yから小さいxを復元できるtoyであり、観測秘匿の実証ではない。
RSSI/session/資格/IVC/オンチェーン検証は含めない。実キャプチャを使用しない。

`gnark-tiny/`はgnark 0.16.3／gnark-crypto 0.21.0とgo.mod/go.sumを固定。
Goのcgoを使わず、ホスト実行ファイルとLinux ARM64実行ファイルを構築する。
source digestを両binaryへ埋め込み、fixtureのsource/全artifact hashと現在再構築したCSのhashを照合する。
private fixtureはdirectory 0700/files 0600を要求し、不完全・不一致のものを削除/再利用しない。

```sh
python3 experiments/pi4-zkp-bench/build_tiny.py
# 以下はMac ARM64の例。既存fixtureは上書きせず、再実行は新しい名前を使う。
.cache/week24/gnark-tiny-darwin-arm64 setup .cache/week24/private/gnark-tiny-v2
GOMAXPROCS=1 .cache/week24/gnark-tiny-darwin-arm64 bench .cache/week24/private/gnark-tiny-v2
```

setupはホスト側のcompile/key generationで、Pi測定ではない。
benchは受信fixtureを検査し、再構築compile、key load、witness生成、prove、verifyを分離する。
warmup 1＋20回。正常検証と、公開y変更、proof改変、不正なyのassignment、8bit範囲外のxを拒否する。
proof改変はdecode拒否かverify拒否かを別に出力する。
private assignmentと生成proof/publicはRAM内だけで、キャッシュ/出力しない。
使い捨てVK・proof・PK・CSはGit公開・チェーンdeployしない。native local-only test fixtureとして扱う。

Piへの転送前に受信fixtureのpathが存在しないことを確認し、owner-only directoryを作る。
binary hash、fixture manifest hashと各artifact hash、modeを確認する。
接続先・パスワードはスクリプト・Gitに含めない。SSHの短期ControlMasterで接続した後、公開ファイルとlocal-only fixtureのみ転送する。

Piでは最初に`python3 inventory.py`で機種・OS・RAM・cgroup・温度・power flagsを収集。
memory cgroupが無効な場合、systemdのMemoryMax指定だけでは上限を保証できない。
runnerはcgroupの実際の`memory.max/high/swap.max`を読み、期待値でなければproofを開始しない。
OSのmemory cgroupはbackup付きで有効化し、再起動後のcontrollerを確認済み。
`enable_memory_cgroup.py`は元のboot config hashを照合し、owner-only backupを作る。reboot自体は別操作。
boot configの変更を勝手に繰り返さず、既存設定とbackupを確認する。

以下は有効化後のPi上での実行例。root transient unitからUser=piでproveを実行する。
`install_memory_guard.py --watchdog-sha256 SHA256`でruntime-only guardを設置する。
script sourceを確認してからsudoで実行し、SHA256は転送元の`memory_watchdog.py`と照合する。
このguardは実験全体のweek24.sliceを1.5GiB／Swap禁止に制限し、SSHのOOMScoreAdjust=-900を設定する。
root所有の`/run/week24/memory_watchdog.py`を別unitで動かし、OS available<1GiBなら実験sliceだけを停止する。
watchdogの上限は64MiB、pollは100ms。SSHをrestartしない。
guardは再起動で消えるため、次回測定前に再設置・検査する。既存guardがある場合は上書きせず確認する。
`--harden-existing`は初期配置の移行用で、通常の再インストールには使わない。

```sh
sudo systemd-run --unit=week24-gnark-tiny-NEW-RUN --wait --pipe \
  -p User=pi -p Slice=week24.slice -p MemoryAccounting=yes \
  -p MemoryHigh=192M -p MemoryMax=256M -p MemorySwapMax=0 \
  -p OOMScoreAdjust=500 -p OOMPolicy=stop -p CPUWeight=10 -p RuntimeMaxSec=210 \
  python3 "$PWD/.cache/week24/run_tiny.py" \
  --binary "$PWD/.cache/week24/gnark-tiny-linux-arm64" \
  --fixture "$PWD/.cache/week24/private/gnark-tiny-v2" \
  --out "$PWD/.cache/week24/runs/gnark-tiny-NEW-RUN"
python3 .cache/week24/analyze_memory.py .cache/week24/runs/gnark-tiny-NEW-RUN
```

Go processのみを最初の利用可能CPUへtasksetで固定し、GOMAXPROCS=1、runtime.NumCPU=1を結果で検査する。
runnerは別CPUで動ける。gnarkの内部goroutine数／OS thread数が厳密に1という意味ではない。
10msでcgroup current/swap、Go RSS/PSS/HWM、system available/swapを記録し、250msでpower/throttle flagsを観測。
observerも同じmemory cgroupに含む。上限／親slice／SSH保護／独立watchdogが未成立なら実行しない。
最初のtoyは256MiBで測定。より大きい回路は別runとして予算を明示し、親1.5GiBを超えない。
`memory.peak`はPython・Go・observerを含むunit全体のpeak、GoのGetrusage peak RSSとは別。
timeout 180秒、外側unit lifetime 210秒。OOM/timeout/current power flags異常/verify失敗は失敗としてログを保存。
途中failureでsummaryがない場合も、空のrun directoryを削除せず保存する。
thermal/powerのsamplingは瞬間イベントの完全な捕捉を保証しない。過去のsticky flagも報告へ残す。

`analyze_memory.py`は平均・母標準偏差・p50/p95/p99・time-weighted分布・OLS傾向を出す。
分位点は線形補間、時間重みは前sampleを次sampleまで保持する定義。
startupを含む短い自己相関系列なので、OLSの正の傾きからリークや長期の増加量を推定しない。
実測logからの図は`plot_memory.py`で再生成できる（matplotlib必要）。

`build_tiny.py`のmanifest内`pi_proof_executed=false`はビルド段階の状態であり、将来のPi成功は別の実行logで判定する。
