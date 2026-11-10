# Remote ID受信をどこまで高速化できるか

2026-11-10。対象：Pixel 8のKMPアプリ、将来の送信機はDJI Matrice 350 RTK。
**今回は資料・既存ログ・コードの調査。追加の無線実験、OS設定変更、購入、実装変更は行っていない。**

## 結論

- スマホ単体で確認済みなのは、開発用スキャン制限OFF・Piテスト送信での更新中央値1.51秒、最小1.37秒。
- これは最短限界の証明ではない。500ms・250ms要求や完了通知に合わせた要求方式は未評価であり、1秒未満の到達可否はまだ断定できない。
- Androidの標準Wi-Fiスキャンには、指定周期で新しい値を届ける保証がない。要求を細かくするだけでは、同じキャッシュを繰り返す可能性がある。
- RSSIを100ms級で高密度に観測したいなら、送信周期を確認し、固定チャネルでフレームを受信できる外付け受信系を比較する価値が高い。100msは条件付きの設計例で、M350や手元機材で達成した数値ではない。

## 3つの時間を分ける

| 項目 | 意味 | 今回確認できていること |
|---|---|---|
| スキャン要求間隔 | startScanを呼ぶ間隔 | 30秒・5秒・1秒を実装済み |
| 新しいスキャン観測の間隔 | ScanResult.timestampが更新される間隔 | 1秒要求で中央値1.51秒 |
| RID内容／申告位置の更新間隔 | 送信元が新しい内容を作る間隔 | M350は未測定。Pi試験の内容は固定 |

今回のPi試験は、同じcounter・同じVendor IE内容を繰り返す送信だった。
したがって1.51秒は、**RSSI等の新しいスキャン観測の更新間隔**であり、新しい機体位置がその周期で更新された証拠ではない。

受信遅延も別指標である。一定間隔で観測できても、元の位置情報が古い可能性がある。
Androidのtimestampは、その結果が最後に観測された起動後マイクロ秒を表す。送信元が位置を生成した時刻とは異なる。[ScanResult公式仕様](https://developer.android.com/reference/android/net/wifi/ScanResult#timestamp)

## Android側の制約

[公式スキャン仕様](https://developer.android.com/develop/connectivity/wifi/wifi-scan)は、通常の前景アプリの要求を2分で4回に制限する。バースト可能なので「どの状況でも最短30秒」とは言えないが、継続的な高頻度取得の根拠にはならない。
開発者向けの制限OFFはローカル試験用の条件であり、通常運用と別に評価する。

[startScanのAPI](https://developer.android.com/reference/android/net/wifi/WifiManager#startScan())は要求後に非同期で結果を通知する。要求成功は、対象機の新しい観測が必ず得られたことを意味しない。
[getScanResultsの扱い](https://developer.android.com/develop/connectivity/wifi/wifi-scan)にも、以前の結果が返り得ることが明記される。

現在利用するstartScanには周波数・チャネルを指定する引数がない。
[AOSP ScanRequestProxy](https://android.googlesource.com/platform/packages/modules/Wifi/+/refs/heads/main/service/java/com/android/server/wifi/ScanRequestProxy.java)ではWIFI_BAND_ALLを指定し、通常アプリの6GHzについてPSCのみとする処理がある。
これはAOSPの実装であり、Pixel 8の特定ビルド・ドライバがすべて同じ動作をすることを実測したものではない。
チャネルを指定できるScanSettingsを持つ[WifiScanner](https://android.googlesource.com/platform/packages/modules/Wifi/+/refs/heads/main/framework/java/android/net/wifi/WifiScanner.java)はSystemApi・hideで、標準の一般アプリから自由に使える機能として扱わない。

以上から、広い帯域の探索やOS・ドライバの処理が制約になる可能性はあるが、**1.5秒の原因を全帯域スキャンだと断定することもできない**。

## 送信側も確認が必要

既存Piテスト送信コードはbeacon_int=100を設定する。
[hostapdの設定資料](https://android.googlesource.com/platform/external/wpa_supplicant_8/+/refs/heads/main/hostapd/hostapd.conf)の単位は1.024msで、設定上のBeacon間隔は102.4ms。
これは約102msの実送信をRF計測で確認した結果ではなく、すべてのフレームに同じRIDが届く保証でもない。
ただし、受信した中央値1.51秒と、送信設定上の周期が別物であることは明確である。

[OpenDroneIDの比較資料](https://github.com/opendroneid/opendroneid-core-c/blob/master/README.md)はLocationメッセージを1秒間隔、Basic ID/Systemを条件により3秒間隔と整理し、Wi-Fiチャネルによって5Hzの送信を求めるケースも説明する。
これは参照実装プロジェクトの整理であり、M350の実送信仕様・日本向け実機の適合性を証明する資料として使わない。日本欄には翻訳由来の注意書きもあるため、法令上の結論は出さない。

[DJIのM350公式マニュアル](https://dl.djicdn.com/downloads/matrice_350_rtk/20240814/Matrice_350_RTK_User_Manual_v1.2_en.pdf)のDirect Remote ID節はWi-Fi Beaconを記載するが、C3/EEAの文脈。
今回確認したDJI公式資料からは、手元M350の実際のBeacon周期・RID内容更新周期・送信チャネルを確定できなかった。
送信機のBluetooth仕様やO3映像リンクのフレームレートから、RIDの方式・周期は推定しない。

## さらに高速化する候補

| 候補 | 調べること | 現状 |
|---|---|---|
| Pixel 8：要求500ms／250ms | 実効間隔が縮むか、要求拒否・重複・CPUが増えるだけか | 未実装・未測定。達成速度は予告しない |
| Pixel 8：完了通知を基準に次の要求 | 空振り要求・待ち時間を減らせるか | 未実装。速度向上は仮説 |
| 受信・解析・保存・監査の時間計測 | API待ち、主スレッド、PSS計測、描画、書込みのどこに時間を使うか | 現状ログでは因果分解できない |
| 対応Wi-Fiアダプタ＋Pi/Linux | 固定チャネル・monitor modeで各フレームの時刻・RSSIを収集する | 手元の既存スキャン受信と別方式。実機互換性確認が必要 |
| 対応ESP系受信機 | promiscuous modeの管理フレームコールバックで受信する | 機種・帯域・チャネルの適合確認が必要。未導入 |

[Linux Wirelessのmonitor mode資料](https://wireless.docs.kernel.org/en/latest/en/users/documentation/modes.html)は、受信フレームをホストへ渡す動作と、ハードウェアによるbest effortの制約を説明する。
固定チャネル受信なら全帯域スキャン待ちを避ける構成にできるが、欠測ゼロや一定周期を保証するものではない。

[Espressif公式資料](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/wifi-driver/wifi-modes.html)にも管理フレームを受信するsniffer modeがある。
ただし[従来のESP32は2.4GHz](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/index.html)であり、ESP系全機種が同じ対応帯域ではない。M350の実際の帯域が不明なまま機材を選ばない。

例として、機体が同一チャネルで100msごとにフレームを出し、対応受信機が十分受け取れるなら、100ms級RSSI観測を狙う設計は考えられる。
**この100msは仮定からの設計上の推論であり、M350・Pixel 8・Piでの達成結果ではない。位置内容の更新周期が1秒なら、同じ内容を何回受信しても新しい位置は増えない。**

## 次に行う評価の順序

1. 既存1秒モードを60秒以上・独立3回で再評価し、順序・充電・画面状態・送信条件を記録する。
2. 500ms・250ms要求と通知駆動を、開発用条件として同じ送信源で比較する。現在のScanPolicyは1秒未満を拒否するため、単にOS設定だけを変えても実行できない。
3. 新規観測間隔の中央値・p95・最大空白、要求／拒否、重複、観測時刻と受取時刻、CPU/PSS/保存遅延を分けて記録する。要求と完了通知は必ずしも1対1ではない。
4. 内容も更新する制御送信源を使い、RSSI観測の鮮度とRID申告値の鮮度を別々に測る。
5. M350実機で送信方式・周期・内容更新・受信帯域を監査した後、スマホ方式と固定チャネル方式を比較する。

今回新たに実行したベンチマークはない。500ms取得、250ms取得、100ms取得、M350の1Hz更新を達成したとは報告しない。
