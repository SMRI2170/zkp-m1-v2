# Pi実送信によるA/B/CとPixel 8のRID受信確認

2026-11-10。ユーザーの「ラズパイで配信し、それぞれのノードで取得できるか」に対する実機試験。途中の指示に従いASUS端末での評価を中止し、Pixel 8を更新・動作確認した後に受信役として使用した。

## 結果

**Pi Aから送信したテストRIDをB・C・Pixel 8が取得し、Pi Bから送信したテストRIDをA・C・Pixel 8が取得した。6つの送受信組合せすべてで、受信内容が送信側のVendor IE内容と一致し、Basic IDとLocationをデコードできた。**

| 送信役 | 受信役 | 送信内容と一致したスキャン観測数 | RSSI中央値（受信機表示dBm） |
|---|---|---:|---:|
| A | B | 6 | -25 |
| A | C | 6 | -37 |
| A | Pixel 8 | 6 | -51 |
| B | A | 7 | -26 |
| B | C | 5 | -56 |
| B | Pixel 8 | 4 | -39.5 |

件数は重複キャッシュを除いた**スキャン観測数**。独立した802.11物理パケット数ではない。真の総送信数・無線損失数は未計測のため、パケット受信率は計算しない。受信機間のRSSI絶対校正、実距離、配置・向き・送信電力の独立真値も未取得で、RSSI差を距離差や性能差に直接換算しない。

## 実測と合成の境界

- 電波送信と各機材のWi-Fi受信は実機で実施。OMNeT++や合成RSSIの結果ではない。
- Piに設定したRIDのID・位置・高度・counterは**試験用に合成した申告内容**。実ドローンの実位置・飛行・DJI実機を再現したと扱わない。
- 既存opendroneid-core-cを使ったエンコーダで、60bytesのVendor IE、25bytes×2メッセージのMessage Packを構築した。
- 周波数2452MHz（ch9）。A・Bは既存STA接続のチャネルを維持したまま別の仮想APを使用。Cは5GHzの既存接続を維持しながら2.4GHzをスキャンした。
- 同じ物理パケットの多局同時捕捉は未確認。位相差AoA、DRSSによる未知電力除去、位置偽装FPR/TPRは今回の成果ではない。

## 2段階の試験

1. Aを送信役、B・C・Pixel 8を受信役にした。counter204、送信の上限90秒、Pi受信60秒・3秒間隔。
2. Aの停止とAP撤去を確認した後、Bを送信役、A・C・Pixel 8を受信役にした。counter211、同じ送受信時間設定。

送信役は自身の受信成功として数えていない。物理Pi3台をすべて受信確認するため、送信役を交代した。BSSIDとテストRIDは役割間で再利用するため、これらだけで実機同一性を主張しない。

Piの常設プログラムはスキャンキャッシュを読むのみ。今回の実験では別の短時間systemd unitで、対象周波数の能動スキャンを8秒間隔で要求した。Androidも通常のアプリスキャンに加えADBの`cmd wifi start-scan`で更新を要求した。従って、今回の件数を「通常運用で必ず得られる更新頻度」としない。能動スキャン由来のProbe Response情報が混在する可能性があり、個々の取得をraw Beaconフレームだとは断定しない。

## 内容一致の確認

単に同じ名前のAPが見えただけでは成功にしなかった。

- 送信側の生成したVendor IE内容のSHA-256とcounterをprivate receiptに保存。
- 各受信ログのFA:0B:BC／0x0D＋counter＋ODID payloadを再構成してSHA-256を計算。
- 受信側が記録したhashと送信receiptのhashの両方が一致することを確認。
- Pythonの既存ASTMデコーダでBasic IDとLocationに展開できることを確認。

Pixelの端末内ログはframing_validであり、今回の内容照合・ASTMデコードは取得したログに対してホスト側でも実行した。Pixelの1つの記録にA送信6件とB送信4件が入り、counterと内容で各phaseに分けた。counterだけの一致、別phaseの行、RSSI欠損を正しい受信・ゼロdBmへ置き換えない回帰テストも追加した。

IDの真正性、DRIP trust chain、観測者ハードウェア、センサの正直さを認証した結果ではない。管理下の送信内容を管理下の受信機で照合した研究PoC。

## 初期3試行の失敗と修正

| 試行 | 主な設定・観察 | B/CのRID記録 | 判定 |
|---|---|---:|---|
| A1 | 一時AP ridtx0、WPA2、短時間の受動スキャン | 0 / 0 | 未達 |
| A2 | ap0へ変更、能動スキャン | 0 / 0 | 未達 |
| A3 | 旧構成に近い無線設定。daemonはAP-ENABLEDでも、実際のap0はmanagedだった | 0 / 0 | 未達 |
| A4 | NMの解放待ち後に、一時IFだけdown→AP型を再設定→up。kernelのtype APも確認 | 6 / 6 | 内容照合まで成功 |

`AP-ENABLED`だけでは実際の受信を保証しなかった。NetworkManager／supplicantの非同期な解放処理との競合が疑われるが、個々の機構まで確定した原因分離実験ではない。修正後にkernel type APの維持と実受信が確認できたことを報告する。

初期daemonのreceiptがSTOPPED_AFTER_BOUNDED_TESTでも、受信0件の試行を受信成功として数えない。失敗した試行のreceipt・hostapdログ・受信空ログはprivateに保全し、公開側には件数集計を残した。

旧スクリプトのパスワード直書きや`pkill hostapd`は使っていない。新スクリプトは試験用のAPだけを作成・撤去し、他のhostapdがあれば開始を拒否する。既存STAのチャネルは変更しない。Beacon専用互換設定では空のMAC accept-listを指定して端末の接続を拒否し、通常のネットワーク接続用途には使用しない。この接続拒否自体の攻撃試験は未実施。

## Pixel 8の更新・動作確認

- Pixel 8、Android17/API37をADBで確認。既存アプリへ更新インストールし、firstInstallTimeが維持されたことを確認。
- Wi-Fiスキャンに必要な位置権限を付与。API30以降の公開IE APIで取得できた。
- WiFi Rawの記録開始・停止、端末内JSONL、Piの実送信内容の取得まで確認した。
- 既存ネイティブライブラリの16KB／RELRO互換警告が表示された。OKで閉じて無線機能を検証し、「次回から表示しない」やOSの互換制御変更はしていない。実測ページサイズは4096bytes。16KB実機への完全対応やZKP／画像処理の実動作は今回確認していない。
- ASD-STAN識別子が一致するWi-Fi Beacon形式の受信系を確認したものであり、DJI全機種・全FWへの一般的保証ではない。

## 終了時の確認

- A/Bのテスト送信は時間上限で終了し、一時APは撤去済み。
- A/B/Cにhostapdプロセスや実行中のzkp-beacon実験unitが残っていないことを確認。
- A/Bは既存ch9、Cは既存ch44のmanaged接続を維持。全台SSHで終了確認できた。
- Pixelの記録は停止し、画面に記録開始ボタンが戻ったことを確認。
- 生データ・UI画像・原始スキャン・送信receiptはignored captures配下、ディレクトリ0700・ファイル0600。公開するのは匿名化した集計のみ。

## 再現方法

受信ノードで以下を実行する。

```sh
~/zkp-beacon-observer/run --duration 60 --interval 3
# 実験としてスキャン更新を要求する場合（受信キャッシュの読み出しとは別）
sudo /usr/sbin/iw dev wlan0 scan trigger freq 2452
```

送信側は `experiments/week28-beacon-observers/safe_beacon_tx.py` をPiへ配置し、管理下の試験用値をprivateに設定する。空いているap0、既存2.4GHz STA、hostapd／nmcli／旧ODIDエンコーダが必要。実験ごとに新しいrun-idとunit名を使う。

```sh
RUN_ID="manual-test-$(date +%s)"
sudo systemd-run --unit="zkp-beacon-$RUN_ID" \
  --property=RuntimeMaxSec=120 --property=MemoryMax=128M \
  --property=TimeoutStopSec=20 \
  /usr/bin/python3 ~/zkp-beacon-observer/safe_beacon_tx.py \
  --encoder ~/odid_ie --ap ap0 --beacon-only-compat \
  --run-id "$RUN_ID" --counter 204 \
  --lat "$TEST_LAT" --lon "$TEST_LON" --alt "$TEST_ALT" --duration 90
```

Bのエンコーダとスクリプトは `~/zkp-beacon-observer/tx-tools/`に配置した。Cは今回送信役として試していない。受信プログラムの上限128MiB、スキャン要求unitは64MiB。受信子プロセスの最大RSSは約21〜24MiBだった。

privateな受信ログ・receiptから公開集計を再生成する。

```sh
python3 experiments/week28-beacon-observers/analyze_rf_smoke.py \
  --private-dir captures/beacon-e2e-20261110-a \
  --out week28/results/NEW_RF_ANALYSIS
python3 -m unittest discover -s experiments/week28-beacon-observers -p 'test_*.py' -v
```

結果は `results/rf-beacon-e2e-20261110-c/summary.json` と `reception.csv`。7件の送信ガード／集計テスト、既存Python77件、Go、contracts48件は成功。既存成果や旧送信コードは上書きせず保全した。

次は、同地点での受信機差・時計精度・更新頻度・受信欠落を測定し、実ドローンや位置偽装評価へ段階的に進む。今回だけで距離判定や安全性が検証できたとは結論しない。
