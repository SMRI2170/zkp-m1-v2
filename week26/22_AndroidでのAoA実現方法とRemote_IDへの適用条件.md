# AndroidでAoAを実現する方法とRemote IDへの適用条件

調査日：2026-11-02。公開一次資料に基づく調査。本資料作成時点では新規アプリ・実機試験を行っていなかった。**後続の専用アプリ実装とPixel 8実機記録は[報告23](23_Pixel8専用アプリの実装とWiFi_BLE実機確認.md)**。以下の未確認表現は文献調査時点を指す。外部RF機器の導入・購入は行っていない。

## 結論

**Androidアプリで方向を表示する構成は可能だが、Pixel 8の通常BLEスキャンだけで、任意のRemote ID送信のAoAを測定できる公開手段は今回確認できなかった。**

Bluetooth標準AoA、UWBの方位、RSSIとスマホの回転による方向推定、外部受信機の結果表示は異なる方式。Bluetoothのバージョン、Androidの更新、方位を格納するAPIの存在だけでAoA対応を判断しない。

今回の目的は、送信側を信用せずRemote IDの位置申告の矛盾を検査する研究PoC。対応タグの協力を必要とする方式と、既存RID信号を受動観測する方式を分ける。

## 1. 選択肢の比較

| 構成 | 方向を得る原理 | 送信側の条件 | Android側の位置づけ | 今回の判断 |
|---|---|---|---|---|
| 通常BLEスキャン | RSSI 1値 | 通常のBLE広告 | ScanResult.getRssi() | これだけでパケットのAoA／複数方向同時RSSIは得られない |
| スマホを回転してRSSI＋IMU | 端末の指向性と姿勢に伴うRSSIの変化 | 回転中に送信電力・位置・伝搬が比較可能である条件が必要 | スマホ単体で試作候補 | 任意のパケット別電力変更を除去する方式として採用できない |
| Bluetooth標準AoA | アンテナ間のI/Q位相差 | CTE付きの方向探知対応送信 | 専用受信配列が必要。Pixel 8の公開BLEアプリでの直接取得経路は未確認 | 対応タグとのPoC候補。一般RIDへそのまま適用不可 |
| 外部AoAロケータ＋Android | 専用機器側で方向を推定 | 標準BLEロケータならCTEが必要 | USB／ネットワークで結果を受信・記録 | スマホをUIとして使う候補。端末単体ではない |
| UWB対応Android＋UWB相手機器 | UWB測距と対応機種の方位計測 | 相手もUWB対応、セッション設定の交換 | Jetpack UWB／対応するRanging API | 方式として可能だが、既存BLE RIDの受動AoAとは別 |
| 外部の同期多チャネルSDR | 通常信号の同時I/Qから方向を推定する設計 | 既存信号を使える可能性。CTE専用方式とは別設計 | 初期はPC／Piで推定しAndroidへ結果転送する案 | 普通のRIDを受動観測する研究候補。今回未実装・性能未確認 |
| root・Wi-Fi CSI | 対応チップのCSIを利用 | 対応Wi-Fiフレーム。BLE信号は対象外 | 特定機種・ファームウェアに依存 | Pixel 8／BLE RIDへの解決として提示しない |

通常BLEスキャンの仕様はAndroid [ScanResult.getRssi()](https://developer.android.com/reference/android/bluetooth/le/ScanResult#getRssi())を参照。取得値はdBmのintで、方向別の値やI/Q試料ではない。これは全ベンダー独自機能の不存在を証明したという意味ではない。

## 2. Bluetooth標準AoAに必要なもの

Bluetooth Direction FindingのAoAでは、送信側がCTE（Constant Tone Extension）付きの信号を送り、受信側がアンテナ配列でI/Q（信号の振幅と位相を表す複素試料）を取得する。配列内の位相差から到来方向を計算する。AoDでは配列を送信側に置くため、受信側だけを変更するAoAと混同しない。[Bluetooth SIG概要](https://www.bluetooth.com/learn-about-bluetooth/feature-enhancements/direction-finding/)、[技術解説](https://www.bluetooth.com/wp-content/uploads/Files/developer/RDF_Technical_Overview.pdf)。

単にBluetooth 5.1以降へ対応していることと、必要な任意機能、配列、ファームウェア、アプリ向けアクセスが揃うことは別。CTEのI/Q取得から角度推定までには配列校正と推定処理も必要。

### Remote IDへの制約

- OpenDroneIDにはBluetooth Legacy Advertising、Bluetooth Long Range、Wi-Fi等の送受信実装がある。RIDが受信できることを、CTE付き信号が得られることと扱わない。[OpenDroneID実装の説明](https://github.com/opendroneid/opendroneid-core-c)
- 対象の実パケットがCTEを含むか、どのPHYかを先に確認する。Bluetooth標準の方向探知はLE 1M／2M PHYに対応し、LE Coded PHYで同じ機能を使えると仮定しない。[Bluetooth SIG技術解説 §5.3](https://www.bluetooth.com/wp-content/uploads/Files/developer/RDF_Technical_Overview.pdf)
- CTEタグをドローンへ新たに取り付ければ評価できる可能性があるが、機体側に追加機能を要求する別条件になる。悪意ある送信者がCTEを送らない場合も扱う必要がある。
- 対応タグの方向が測れたことから、タグとRID送信機と機体の物理的対応付けや機体の真正性まで保証しない。

## 3. Androidの方位APIとPixel 8

### Android 16のRanging API

Android 16（API 36）には `RangingManager` があり、対応技術・利用可能性を確認して相手機器との測距セッションを行える。対応技術にはUWB、Bluetooth Channel Sounding、Wi-Fi NAN RTT、Bluetooth RSSIがある。単なる周辺広告の受信ではなく、相手機器との設定交換等が関係する。[公式ガイド](https://developer.android.com/develop/connectivity/ranging)

`RangingData.getAzimuth()`／`getElevation()` は方位・仰角の取得口だが、得られない場合はnullとなる。存在だけで全技術・全機種のAoA対応を意味しない。[RangingData](https://developer.android.com/reference/android/ranging/RangingData)

UWBには `isAzimuthalAngleSupported()`／`isElevationAngleSupported()` の能力照会がある。ハードの能力と利用可能性を照会し、実際に角度のあるレポートが届くかを確認する必要がある。[UwbRangingCapabilities](https://developer.android.com/reference/android/ranging/uwb/UwbRangingCapabilities)、[Jetpack UWBの能力API](https://developer.android.com/reference/androidx/core/uwb/RangingCapabilities)

Channel Soundingは位相・時間に基づく距離測定の方式。Bluetooth 5.1のCTEによるAoAと同一ではなく、Channel Sounding対応から角度出力を推定しない。[Bluetooth SIG](https://www.bluetooth.com/learn-about-bluetooth/feature-enhancements/channel-sounding/)

### Pixel 8とPixel 8 Pro

Googleの公式無線仕様表では、**Pixel 8のUWBはN/A、Pixel 8 ProにはUWBの記載がある**。通常のPixel 8へアプリやOS更新だけでUWBを追加できると説明しない。[Google公式仕様](https://support.google.com/pixelphone/answer/13662136?hl=en)

Pixel 8 Proでも、利用するOS・API・地域設定・相手機器の組合せで角度計測を確認する必要がある。UWBは対応する相手機器とのセッションを行うため、UWB搭載だけでBLE RID送信の方向を受動計測できるわけではない。[Android UWBガイド](https://developer.android.com/develop/connectivity/uwb)

今回、実端末のモデル・OS・能力レポートは取得していない。Pixel 8で利用可能な独自BLE I/Q APIやCTE受信経路も確認できていない。

## 4. 外部機器を使う場合の具体的候補

### 対応タグを使うBluetooth標準AoAのPoC

1. CTE送信タグ。
2. アンテナ配列とAoA対応無線、I/Q取得ファームウェア。
3. 配列校正と方向推定。
4. Androidアプリへ角度・品質・観測時刻を転送。

NordicのDirection FindingサンプルにはCTE受信とI/Q取得の実装がある。AoAモードでは外付けのアンテナ配列が必要であり、通常のDKボードだけで完成と扱わない。connectionless版もPeriodic AdvertisingのCTEを使う。[Nordic RXサンプル](https://github.com/nrfconnect/sdk-nrf/tree/main/samples/bluetooth/direction_finding_connectionless_rx)、[配列要件](https://raw.githubusercontent.com/nrfconnect/sdk-nrf/main/samples/bluetooth/direction_finding_central/README.rst)

Silicon LabsにはBRD4191A（BG22、4×4配列）の評価用ボードと公式手順がある。必要なメイン基板、CTEタグ、SDK、推定処理、Androidとの通信実装を含めて構成確認する。購入推奨や完成品の互換保証ではない。[公式製品ページ](https://www.silabs.com/development-tools/wireless/bluetooth/bg22-rb4191a-bg22-bluetooth-dual-polarized-antenna-array-radio-board)

AndroidはUSB Host APIで外部機器と通信できるが、ドライバ・プロトコル・給電・対応端末の確認は別。基板をUSB接続するだけでBluetooth AoAがAndroid標準APIへ現れるとは限らない。[Android USB Host](https://developer.android.com/develop/connectivity/usb/host)

### 送信側を変更せず、通常RIDを観測する研究案

複数アンテナで同じRF送信を観測する外部受信部を用意し、初期はPC／Piへ渡して推定し、Androidへ結果だけを送る構成を候補とする。外部RF部によっては別途クロック・位相同期、周波数追従、チャネル校正が必要。

標準CTEロケータを、そのままCTEなしの任意RIDパケットに使えるとは仮定しない。BLE波形からの推定、短いパケットでの試料数、複数送信機・反射の区別を検証する新規研究が必要。現時点で対応SDRの選定、ドライバ、BLE復調、AoA推定まで動作確認した構成はない。

## 5. 外部ハードなしの候補：回転RSSI＋端末姿勢

Kandula, Chidurala, Cao, Li, **Localization of a BLE Device Based on Single-Device RSSI and DOA Measurements**, Network 4, 196–216, 2024. [DOI:10.3390/network4020010](https://doi.org/10.3390/network4020010)、[本文](https://www.mdpi.com/2673-8732/4/2/10)、[NSF掲載](https://par.nsf.gov/servlets/purl/10574078)。

スマホを同じ位置で回転し、BLE RSSIと端末方位を組み合わせる方法。専用配列の位相差AoAと区別する。公開要旨では30°範囲の方向提示を報告するが、Pixel 8や飛行中の敵対的RIDへの精度仕様ではない。今回確認できた要旨・本文検索表示の範囲では、Pixel 8実機での再現条件は未確認。本文直取得は429／502で失敗したため、詳細数値を採用しない。

この方式を今回の攻撃条件へ当てはめると、回転中の別パケットの比較は

\[
R(t_1)-R(t_2)=P(t_1)-P(t_2)-[L(t_1)-L(t_2)]+[G(\theta_1)-G(\theta_2)]+\Delta\varepsilon
\]

となる。送信ごとに自由なP(t)を許せば電力差が残る。これは今回のモデルとの比較に基づく判断であり、論文がその攻撃を検証したという意味ではない。一定／緩やかに変わる電力の下での方向推定候補として試す価値はあるが、自由電力への対策として置き換えない。

## 6. Wi-Fi CSI・root化は別経路

Nexmon CSIは特定Broadcomチップ・ファームウェア上でWi-FiフレームのCSIを取り出す研究実装。公開対応表にはNexus 5、Nexus 6P、特定Pi等がある。Pixel 8で動作すること、BLE I/Qを取得できること、CSIだけでAoAが完成することは確認できない。[開発元の対応表](https://github.com/seemoo-lab/nexmon_csi)

root化はアンテナ配列や未搭載RF機能を増やさない。CSIを取得できても空間的な位相情報、アンテナ構成、校正、推定手法を別に確認する。

## 7. 今回のM1シミュレーションとの対応

| 今回のM1 | Bluetooth標準AoA |
|---|---|
| 同一局で同じ送信の方向別RSSIを比較 | 配列のI/Q位相差を利用 |
| 仮定した方向別利得を使う | 実配列・無線・CTE取得と校正が必要 |
| 送信ごとの共通電力を除く | 位相モデル等に基づいて方向を推定 |
| Android機能や実機RFを未実装 | Android／外部機器の取得経路が別に必要 |

したがって、M1の「4方向で横100mの警報率53%」をAndroid AoAの期待検知率にしない。どちらも方向だけでは同じ方向の近距離・遠距離の偽装を一般に区別できず、反射・中継等への別評価も必要。

Han/Jang 2025の切替アンテナ・OFDM映像信号の研究も、Bluetooth CTEやPixel単体の実証ではない。[論文](https://pmc.ncbi.nlm.nih.gov/articles/PMC12031410/)

## 8. 次に実装する場合の判断順序

1. 対象をBLE RID／Wi-Fi RID／協力UWBタグ／CTEタグのどれにするか固定する。異なる電波を同じAoA方式で扱わない。
2. Pixel 8か8 Proか、Android版、公開APIが報告する能力・利用可能性を取得する。機能名だけで対応扱いにしない。
3. 外部ハードなしなら、まずRSSI・端末姿勢・観測時刻の収集を試す。これは回転RSSI法の実現性評価で、M1同時受信や自由電力への対策とは別。
4. CTEタグが許されるなら、公式AoAロケータでI/Qと角度を確認してからAndroid表示を接続する。
5. 送信側を変更できないRIDが対象なら、標準CTE方式を即採用せず、実パケットと外部受信方式の成立確認を優先する。

実データを取得する段階では生の観測・位置・識別情報はignoredのcaptures内、所有者専用権限で保存する。署名やZKPは計算・記録の検証であり、センサの正直さや機体の真正性の保証を追加するものではない。
