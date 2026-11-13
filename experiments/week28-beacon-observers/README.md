# PiのRSSI付きRemote ID観測

研究用PoC。通常のWi-Fiスキャンキャッシュを読む方式であり、生フレーム受信・機体認証・位置の真正性・多局同一送信の証明ではない。
受信したODID候補のRSSI（dBm）、周波数、キャッシュ時刻、申告位置、元のVendor内容を、各Piのowner-privateな`captures/`へJSONL保存する。欠測RSSIは`null`と理由を保持する。Pi側はSQLiteではない。

## 通常の起動

各Piへ必要なコードを`~/zkp-beacon-observer/releases/<version>/`に転送し、その一般ユーザーでインストールする。

```sh
python3 ~/zkp-beacon-observer/releases/<version>/experiments/week28-beacon-observers/install_node.py --node-id observer-a
~/zkp-beacon-observer/run --check
~/zkp-beacon-observer/run --self-test
~/zkp-beacon-observer/run --duration 60
```

観測IDはA〜Fで変更する。既存の設定が違う場合は上書きせず停止する。旧releaseと収録は保持する。
通常の読み出し間隔は1秒。これだけでは能動スキャンを要求しないため、新規RSSIが1秒で更新する保証はない。

## 短い間隔での更新要求

A/B/Cに導入済みの簡易起動コマンド（明示的に起動した期間だけ収録）：

```sh
~/zkp-beacon-observer/fast --duration 60
# 受信で確認済みの周波数だけへ絞る場合
~/zkp-beacon-observer/fast --duration 60 --frequency 2452
```

0.25秒要求・0.1秒キャッシュ読取り。必要なら`--scan-interval 1`等へ緩められる。一般ユーザーとして実行すると、既存sudo権限を使って期間限定サービスを開始する。必要なノードでは端末でsudoパスワードを入力する。Bにも追加導入済み。全チャネルと単一周波数では実効間隔が異なり、0.25秒のRSSI更新を保証しない。


```sh
# パスワード不要のsudoが既に使えるノードのみ。権限を新規設定するコマンドではない。
~/zkp-beacon-observer/run --duration 60 --interval 0.1 --active-scan --scan-interval 1
```

`--frequency`を省略すると、ドライバの対応チャネル全体へスキャン要求する。対象周波数が実測で確認できた場合だけ、例として`--frequency 2452`のように絞る。M350の機種名だけから周波数を固定しない。

Aのようにsudoにパスワードが必要な場合、実験の間だけ一般ユーザーのサービスへCAP_NET_ADMINを付ける。sudoersの変更・root常駐・自動起動は行わない。

```sh
sudo systemd-run --wait --pipe --collect \
  --unit="zkp-scan-$(date +%s)" --uid="$(id -un)" \
  --property=RuntimeMaxSec=90 --property=MemoryMax=128M \
  --property=AmbientCapabilities=CAP_NET_ADMIN \
  --property=CapabilityBoundingSet=CAP_NET_ADMIN \
  "$HOME/zkp-beacon-observer/run" --duration 60 --interval 0.1 \
  --active-scan --scan-interval 1
```

スキャン中は一時的にオフチャネルになる場合がある。既存Wi-Fiの切断やmonitor切替え・接続チャネルの固定変更はしないが、通信への影響がないことを保証するものではない。期間とメモリを制限して段階評価する。

- キャッシュ読出し最小0.1秒、要求間隔最小0.25秒。最短値を安定性能の実測と解釈しない。
- 直前の要求が返った時刻から指定秒数待つ。コマンド時間も加わる。
- 拒否・busy・タイムアウト時は最大5秒まで待機を増やし、5連続失敗か権限拒否で停止。
- `events.jsonl`へ要求成否・待機・停止理由を記録。新しい観測行は逐次flushする。電源断直前の永続性を保証しない。
- 既定60秒・最大3600秒、プロセス128MiB／1ファイル20MiB、重複キー上限10万。終了コード0は新鮮ODIDあり、3はなし、2は失敗。
- 通常のrun／fastコマンドは手動・期間限定。起動時収録は後述の明示導入サービスだけで有効になる。

## 順次比較・CSV/JSON

同じ権限付きの期間限定サービス内で、`run`の代わりに次を実行する。出力先は新しい`captures/`配下にする。上のRuntimeMaxSecは合計期間＋余裕へ変更する。

```sh
python3 ~/zkp-beacon-observer/current/experiments/week28-beacon-observers/benchmark_scan.py \
  --config ~/zkp-beacon-observer/config/node.json \
  --output-dir ~/zkp-beacon-observer/current/captures/benchmark-new-run \
  --duration 20 --profiles 2,1,0.5,0.25
```

各条件20秒を順次実行し、`profiles.jsonl`と`profiles.csv`を生成。個別の生観測とイベントも保存する。固定順序・短時間の探索比較なので、最適性や長時間の安定性の証明ではない。

比較するのは、同じBSSID・周波数の**実行開始後のカーネルキャッシュ時刻を持つRSSI更新**の中央値／p95／最大間隔。古いキャッシュ・時刻不明・RSSI欠測を更新間隔へ混ぜない。複数Vendor IEが同一時刻でも複数の時間更新として数えない。
パケット数、RID位置フィールドの更新頻度、全送信に対する受信率は計算しない。

生データ・位置・送信機識別子・鍵をGitに追加しない。0700のディレクトリ、0600のファイルを維持する。共有時は匿名集計だけを明示的に選ぶ。

## 3ノードの実RF反復実験

`run_rf_matrix.py`は、認証済みSSH control socketでA/Bを交互に送信役にし、残る2台を受信役にするローカル実行用プログラム。接続・送信エンコーダ・受信環境が既に用意されていることが前提で、ネットワーク構築・既存収録の停止は行わない。

1. 全台で他の収録・送信が動いていないことを確認する。
2. owner-privateな`captures/<session>/`を作り、その中に認証済みSSH control socketと0600の`nodes.json`を用意する。socketの引数は104bytes未満の短い相対パスを使う。
3. A/Bの`transmitter_script`は監査済み`safe_beacon_tx.py`、`encoder`は以前から使用する`odid_ie`の絶対パスを指定する。Cは今回の送信役にしない。
4. 次を起動し、既存sudoのパスワードを端末で一度入力する。パスワードは保存せず、sudoの標準入力にだけ渡す。core dumpも無効にする。

設定形の例（実接続情報をGitに追加しない）：

```json
{
  "nodes": {
    "a": {"host": "pi@observer-a.local", "socket": "captures/session/ssh-a", "transmitter_script": "/home/pi/zkp-beacon-observer/safe_beacon_tx.py", "encoder": "/home/pi/odid_ie"},
    "b": {"host": "pi@observer-b.local", "socket": "captures/session/ssh-b", "transmitter_script": "/home/pi/zkp-beacon-observer/tx-tools/safe_beacon_tx.py", "encoder": "/home/pi/zkp-beacon-observer/tx-tools/odid_ie"},
    "c": {"host": "pi@observer-c.local", "socket": "captures/session/ssh-c"}
  }
}
```

```sh
python3 experiments/week28-beacon-observers/run_rf_matrix.py \
  --config captures/session/nodes.json --output-dir captures/session/matrix \
  --repetitions 3 --duration 15 --sustain 90
```

対象周波数は、送信時に確認した既存STAの周波数を利用する。元の送信コードの2.4GHz制限・最大120秒を維持し、申告ID・位置は試験用の合成値。実ドローンの再現とはしない。

- 24比較試験：A/B送信 × 単一周波数／全チャネル × 0.25／1秒要求 × 3反復。反復2では条件と送信役の順を反転する。
- 続けてA/B送信の90秒収録を各1回。`--mode sustain-only --sustain-scope all`なら全チャネル90秒の2試験だけを追加できる。
- 各試験で受信側cgroupのMemoryCurrent／MemoryPeak・CPU時間、ホストMemAvailable、SSH照会時間を数秒おきに収集する。PSSやパケット損失率ではない。カーネル／systemdが返さないcgroup値は未取得のまま保持し、0や適用済み上限と読み替えない。受信PythonのRLIMIT_ASとサービスのMemoryMax要求は別の制限。
- 各試験の詳細JSONと進捗JSONLを逐次保存。自身が作ったunitだけを停止し、送信receiptのAP撤去確認ができない場合は次へ進まない。
- 正常終了したtransient unitが既にunloadされていても、`ActiveState=inactive`なら停止済みと確認する。不明な状態を成功扱いにしない。
- SSH切断・controller停止でもremote unitの時間／メモリ上限は残る。ただし、その瞬間のローカル監査情報まで保持できる保証はない。原始受信はPi側のrelease/capturesに残る。

実験後、各Piの対象releaseの`captures/`を、ローカル`captures/session/snapshots/{a,b,c}/captures/`へowner-privateで回収する。その上で匿名集計する：

```sh
python3 experiments/week28-beacon-observers/analyze_rf_matrix.py \
  --matrix captures/session/matrix --snapshots captures/session/snapshots \
  --output-dir week28/results/new-run
```

matplotlib入り環境なら`--plot`も付ける。出力はrun別・条件別・メモリ統計・資源推移・5秒RSSI中央値のCSVとsummary JSON。生行・座標・送信機識別子・内容ハッシュを出力に含めない。
送信receiptと内容・counterが一致した観測だけを選び、実行開始BOOTTIME以降のRSSI更新間隔を再計算する。開始時刻メタデータのない旧版は、無理に推定せず解析エラーとして残す。

## ドローンと搭載Piの別記録・文字列保存

今回の追加版はJSONLと同じ観測を、各収録ディレクトリの`observations.txt`にも1行ずつ保存する。時刻・BSSID・ローカル分類・申告ID・RSSI・周波数・解析状態・Vendor IE全体のHEXを含む。デコードに失敗しても、対象ODID Vendor IEの元データを残す。一般のWi-Fiデータ通信・未知の全Vendor形式・BLE/NANをすべて取得する機能ではない。

搭載Piは公式RIDの代替ではなく、別の研究用送信機として扱う。`safe_beacon_tx.py`へ以下の明示引数を追加した。

- `--uas-id PI-RID-<個体別文字列>`：最大20byteのASCII。試験用Specific Session ID。実機の製造番号をコピーしない。
- `--tx-mac <個体別LAA>`：個別のlocally administered unicast BSSID。同時送信する試験用Pi間で重複させない。
- `--diagnostic-invalid`：未対応メッセージ版を意図的に送る負のテスト。通常の送信では使わない。

旧引数の動作と120秒上限は維持。実飛行での長時間送信・GPS連携は今回実装していない。テスト用申告位置を機体真位置や公式RIDと扱わない。

明示的なローカル登録を使う場合、owner-privateなJSONリストを作る。実際のRID・MACをGitに追加しない。

```json
[
  {"role":"onboard_pi","label":"搭載Pi（登録）","uas_id":"PI-RID-EXAMPLE","bssid":"02:00:00:00:00:50"},
  {"role":"drone","label":"ドローン（登録）","uas_id":"EXAMPLE-CLAIMED-ID"}
]
```

```sh
~/zkp-beacon-observer/fast --duration 60 --frequency 2452 \
  --source-registry /home/pi/zkp-beacon-observer/config/source-labels.json
# 2452は試験の例。実機で確認できた周波数だけ指定する。
```

登録は最大32件、ID／BSSIDのどちらか必須、両方ある規則は両方一致が必要。より具体的な規則を優先し、同順位で分類が競合したら不明にする。`PI-RID-`は未検証の申告マーカーとしてだけ表示する。その他の未知送信元を自動でドローンと断定しない。

`source_annotation`の分類は利用者の登録・マーカーによるラベルで、`identity_verified=false`。BSSIDとIDの両方を偽装された場合、この方式だけで物理送信機を識別できない。カウンタやRSSIだけでドローン／Piを分類しない。

### 位置なしの搭載Piマーカー

A/Bの現在の2.4GHz環境で地上テストするための短い起動コマンド：

```sh
# 搭載するPi側（一般ユーザーで起動、必要ならsudoパスワード）
~/zkp-beacon-observer/transmit-marker --show-config
~/zkp-beacon-observer/transmit-marker --duration 60
# 別の受信Pi側。2452は地上試験で実際に確認した周波数の例。
~/zkp-beacon-observer/fast --duration 60 --frequency 2452
```

初回導入時に各Piへ個別の`PI-RID-*`とLAAを生成し、0600の`config/marker.json`へ保持する。再導入でも既存値を変えない。これは秘密鍵・製造番号・機体認証IDではなく、観測を分ける研究用マーカー。
送信はBasic IDだけでLocationを含まない。GPSなしで送れる代わりに、実位置を送れたとは主張しない。バイナリエンコーダも不要。

最大120秒・手動起動・自動停止を維持。既存STAが2.4GHzに接続している場合に限定し、接続先・チャネルを勝手に変えない。Cの5GHz接続で送信できる保証、飛行中の接続維持、長時間送信、GPS連携は未評価。公式RIDの代替として使わない。


## 電源投入時の自動受信（明示的に導入する場合）

今回の依頼により、受信専用の `zkp-rid-observer.service` を追加。通常のinstall_nodeだけでは有効にならず、版管理されたreleaseで次を明示実行する。

```sh
sudo python3 ~/zkp-beacon-observer/current/experiments/week28-beacon-observers/install_boot.py --enable
systemctl is-enabled zkp-rid-observer.service
systemctl status zkp-rid-observer.service
cat ~/zkp-beacon-observer/current/captures/boot-status.json
```

電源投入→ネットワーク／wlan0のupを待機→60秒単位の受信を繰り返す。1秒間隔で全対応チャネルへスキャン要求、キャッシュ読出し0.25秒。送信機やhostapd・monitor切替え・sudoers変更は含まない。ネットワークがない場合は15秒ごとに待ち直す。実効RSSI更新間隔・同一物理送信の対応は保証しない。

時刻・RSSI・元のVendor内容は `current/captures/observer-X/<run>/observations.jsonl` と `observations.txt`、収録メタデータはevents.jsonl／summary.jsonに保存。release更新後も旧releaseとそのcapturesを削除しない。アーカイブを自動削除しないため、定期的な回収が必要。

- 一般ユーザーpi、CAP_NET_ADMINのみ。書込みは当該releaseのcapturesに限定。ディレクトリ0700・ファイル0600。
- 受信子プロセスの仮想アドレス空間128MiB、各ファイル20MiB。サービス全体MemoryMax160MiBを要求する。カーネルのmemory controllerが無い機材ではcgroup上限の実効性は別途確認が必要。
- ホスト空きRAM192MiB未満、ディスク空き512MiB未満、次区間の予約64MiBを含め収録予算256MiB超、ファイル1万個で停止。上限停止は自動再起動しない。状態JSONを確認して回収・空き容量確保後に手動restartする。
- エラー3区間連続で終了。systemdは30秒待って再起動し、5分に3回まで。無制限の高速再起動をしない。
- 正常停止は現在の60秒区間終了を待つため最大約95秒かかる場合がある。稼働中にfast/runの能動受信を重複開始しない。

```sh
# 一時停止（次の電源投入では再び起動）
sudo systemctl stop zkp-rid-observer.service
# 自動起動を取り消す
sudo systemctl disable --now zkp-rid-observer.service
# 容量・状態を確認した上で再開
sudo systemctl restart zkp-rid-observer.service
```

JSONLは逐次flushするが、突然の電源断直前の行や終了メタデータの永続性は保証しない。通常はOSをシャットダウンしてから電源を外す。これは研究用受信PoCであり、実機ドローン受信や機体認証を自動起動設定から主張しない。


### Observer Dの追加

2026-11-13、D（Pi 4）にもA/B/Cと同じ版の受信専用サービスを導入。接続先や認証情報はGitへ保存しない。OS再起動・起動状態・保存先の確認結果は[Observer Dの報告](../../week28/24_Observer_D追加と自動受信の起動確認.md)。E/Fは名前の対応のみで、機材への導入は未実施。
