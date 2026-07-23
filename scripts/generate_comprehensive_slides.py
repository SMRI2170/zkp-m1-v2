import json
from pathlib import Path
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

OUTPUT_PATH = Path("project_comprehensive_presentation_75pages.pptx")

W = Inches(10)
H = Inches(7.5)
M = Inches(0.45)
IW = W - M * 2

C_WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
C_BG        = RGBColor(0xFF, 0xFF, 0xFF)
C_NAVY      = RGBColor(0x1A, 0x23, 0x7E)
C_BLUE      = RGBColor(0x19, 0x76, 0xD2)
C_TEAL      = RGBColor(0x00, 0x89, 0x7B)
C_TEXT      = RGBColor(0x21, 0x21, 0x21)
C_SUBTEXT   = RGBColor(0x61, 0x61, 0x61)
C_RULE      = RGBColor(0xBD, 0xC8, 0xE0)
C_CODE_BG   = RGBColor(0xF3, 0xF6, 0xFB)
C_TBLH_BG   = RGBColor(0x1A, 0x23, 0x7E)
C_TBLH_TEXT = RGBColor(0xFF, 0xFF, 0xFF)
C_TBL_ROW1  = RGBColor(0xFF, 0xFF, 0xFF)
C_TBL_ROW2  = RGBColor(0xEE, 0xF2, 0xFF)
C_TBL_TEXT  = RGBColor(0x21, 0x21, 0x21)

FONT = "Hiragino Sans"

def rect(slide, left, top, width, height, color, border=False):
    s = slide.shapes.add_shape(1, left, top, width, height)
    s.fill.solid()
    s.fill.fore_color.rgb = color
    if border:
        s.line.width = Pt(0.5)
        s.line.color.rgb = C_RULE
    else:
        s.line.fill.background()
    return s

def txb(slide, text, left, top, width, height, size=14, bold=False, color=C_TEXT, align=PP_ALIGN.LEFT, italic=False, wrap=True):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.color.rgb = color
    r.font.name = FONT
    return box

def render_bullets(slide, lines, left, top, width, height, size=13, color=C_TEXT):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run()
        r.text = line
        r.font.size = Pt(size)
        r.font.color.rgb = color
        r.font.name = FONT
        p.space_after = Pt(4)

def render_code(slide, text, left, top, width, height, size=10):
    rect(slide, left, top, width, height, C_CODE_BG, border=True)
    rect(slide, left, top, Inches(0.055), height, C_BLUE)
    box = slide.shapes.add_textbox(left + Inches(0.12), top + Inches(0.1), width - Inches(0.18), height - Inches(0.2))
    tf = box.text_frame
    tf.word_wrap = False
    for i, line in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run()
        r.text = line
        r.font.size = Pt(size)
        r.font.color.rgb = RGBColor(0x1A, 0x20, 0x2C)
        r.font.name = "Courier New"

def render_table(slide, headers, rows, left, top, width, font_size=11):
    nr = len(rows) + 1
    nc = len(headers)
    row_h = Inches(0.38)
    tbl = slide.shapes.add_table(nr, nc, left, top, width, row_h * nr).table
    tbl.first_row = True
    for col in tbl.columns:
        col.width = width // nc

    def cell_style(cell, text, header=False, even=False):
        cell.fill.solid()
        cell.fill.fore_color.rgb = C_TBLH_BG if header else (C_TBL_ROW2 if even else C_TBL_ROW1)
        tf = cell.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        r = p.add_run()
        r.text = text
        r.font.size = Pt(font_size)
        r.font.bold = header
        r.font.color.rgb = C_TBLH_TEXT if header else C_TBL_TEXT
        r.font.name = FONT

    for ci, h in enumerate(headers):
        cell_style(tbl.cell(0, ci), h, header=True)
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell_style(tbl.cell(ri + 1, ci), val, even=(ri % 2 == 1))

def apply_header(slide, title, sub=None, page=None):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = C_BG
    rect(slide, 0, 0, W, Inches(0.07), C_NAVY)
    rect(slide, 0, Inches(0.07), Inches(0.07), H - Inches(0.07), C_BLUE)
    txb(slide, title, M, Inches(0.12), IW, Inches(0.55), size=22, bold=True, color=C_NAVY)
    if sub:
        txb(slide, sub, M, Inches(0.65), IW, Inches(0.32), size=11, color=C_SUBTEXT)
    rect(slide, M, Inches(0.98), IW, Pt(1.2), C_RULE)
    if page:
        txb(slide, str(page), W - Inches(0.55), H - Inches(0.32), Inches(0.4), Inches(0.25), size=9, color=C_SUBTEXT, align=PP_ALIGN.RIGHT)

slides_data = []

# --- CHAPTER 1: Introduction ---
slides_data.append({"type": "title", "title": "UAV安全距離証明プロジェクト\n完全技術解説レポート", "sub": "OpenDroneID / ZKP / Flutter / ML 統合の全貌 (全70ページ超)\n2026年版 詳細資料"})
slides_data.append({"type": "section", "title": "第1章：プロジェクトの背景と目的"})
slides_data.append({"type": "bullets", "title": "1.1 ドローン普及の光と影", "bullets": ["■ 物流、点検、空撮などドローンの産業利用が急速に拡大している", "■ 一方で、許可のない飛行やプライバシー侵害、衝突リスクが社会問題化", "■ 目視外飛行（Level 4）の解禁に伴い、空の安全管理が急務となっている"]})
slides_data.append({"type": "bullets", "title": "1.2 リモートIDの法制化", "bullets": ["■ 日本では2022年6月の航空法改正により、100g以上の機体にリモートID搭載が義務化", "■ 米国（FAA）や欧州（EASA）でも同様の機体識別規格が導入されている", "■ これにより、ドローンは飛行中に常に自機の位置と識別情報を発信する必要がある"]})
slides_data.append({"type": "bullets", "title": "1.3 位置情報公開のジレンマ", "bullets": ["■ 誰もがドローンの位置を受信できることは、監視と安全の観点で有益", "■ しかし、運用者にとっては「飛行ルート」や「業務の現在地」が常に筒抜けになる", "■ セキュリティやプライバシー保護の観点から、生データの無条件公開には懸念がある"]})
slides_data.append({"type": "bullets", "title": "1.4 ゼロ知識証明 (ZKP) による解決", "bullets": ["■ 「生の位置情報を公開せず」に「安全であることだけ」を証明する", "■ ゼロ知識証明(ZKP)を用いて、ドローンと第三者の端末間で距離計算を行う", "■ ZK回路は「30m以内かつ5秒以内の接近があったか」というTrue/Falseのみを出力する"]})
slides_data.append({"type": "bullets", "title": "1.5 プロジェクトが目指す姿", "bullets": ["■ 特別なインフラやサーバーを介さず、ドローンと市販スマホの直接通信で完結する", "■ オンデバイスでの証明生成と検証により、ネットワーク途絶時でも動作", "■ 動画AI検知を組み合わせることで、電波の証明だけでなく視覚的な事実も担保する"]})
slides_data.append({"type": "table", "title": "1.6 全体アーキテクチャ構成", "headers": ["役割", "ハードウェア", "主要ソフトウェア/規格"], "rows": [["送信側(UAV)", "Raspberry Pi", "Python, OpenDroneID, BLE"], ["受信・証明(ユーザー)", "Androidスマホ", "Flutter, rapidsnark, ML Kit"], ["証明ロジック", "Circomコンパイラ", "Groth16, Poseidon Hash"], ["視覚検知", "スマホカメラ", "YOLOv11, TFLite, VisDrone"]]})
slides_data.append({"type": "bullets", "title": "1.7 アプリケーションの想定ワークフロー", "bullets": ["① ユーザーがアプリを起動し、BLEスキャンとGPS取得を開始", "② UAVからのOpenDroneID電波を受信", "③ アプリがカメラを起動し、AIがUAVを画面内で検知", "④ 受信ログと撮影ログを統合し、ZKPの入力データ(JSON)を生成", "⑤ 端末内で ZK Proof を計算し、安全証明を完了"]})
slides_data.append({"type": "bullets", "title": "1.8 本資料の構成", "bullets": ["■ 第2章：OpenDroneID準拠とBLEブロードキャスト", "■ 第3章：実機センサー統合 (GPS & BME280)", "■ 第4章：Flutter アプリケーション統合", "■ 第5章：AI検知と動画証拠の統合", "■ 第6章：ZKP 回路設計", "■ 第7章：回路最適化と制約解析", "■ 第8章：結論と今後の展望"]})

# --- CHAPTER 2: OpenDroneID ---
slides_data.append({"type": "section", "title": "第2章：OpenDroneID準拠とBLEブロードキャスト"})
slides_data.append({"type": "bullets", "title": "2.1 OpenDroneID (ASTM F3411-22a) とは", "bullets": ["■ ドローンが周囲に機体情報・位置・速度などを直接発信するための国際規格", "■ Bluetooth (Legacy 4.x / 5 Long Range) および Wi-Fi (NaN / Beacon) に対応", "■ 従来の通信網（LTE等）に依存しないため、山間部でも機能する"]})
slides_data.append({"type": "bullets", "title": "2.2 Bluetooth Legacy Advertising の制約", "bullets": ["■ 標準のBLE 4.xアドバタイズのペイロードは最大 31 バイト", "■ Flags や Service UUID のオーバーヘッドを除くと、実質25バイトしか使えない", "■ OpenDroneID はこの「25バイト」の固定長メッセージを巧みに利用している"]})
slides_data.append({"type": "code", "title": "2.3 独自仕様からの脱却", "code": "// 開発初期の独自フォーマット (17バイト)\nAD type: 0xFF, Company ID: 0x02E5\n[MAGIC][VER][lat 4B][lon 4B][alt 2B][time 4B][seq 1B]\n\n// 課題: 既存のスキャナアプリ(DroneScanner等)で受信できない\n// 対応: ASTM F3411-22a (Service Data UUID 0xFFFA) へ完全移行"})
slides_data.append({"type": "code", "title": "2.4 BLE Service Data フォーマット", "code": "オクテット: [0]      [1]    [2]   [3]    [4 .. 28]\n内容:       length   0x16   0xFA  0xFF   25 バイトメッセージ\n            (= 28)   AD type  UUID (LE)\n\n- AD type 0x16: Service Data – 16-bit UUID\n- UUID 0xFFFA: OpenDroneID 専用"})
slides_data.append({"type": "table", "title": "2.5 OpenDroneID のメッセージタイプ", "headers": ["Type", "名称", "内容", "送信頻度"], "rows": [["0x0", "BasicID", "機体のシリアル番号等", "1〜3秒に1回"], ["0x1", "Location", "緯度, 経度, 高度, 速度, 時刻", "毎秒1回以上(必須)"], ["0x2", "Auth", "電子署名, 証明書", "任意"], ["0x3", "SelfID", "運用者の目的・詳細", "任意"]]})
slides_data.append({"type": "code", "title": "2.6 BasicID メッセージ詳細 (25B)", "code": "Byte 0    : Header = (Type=0 << 4) | ProtoVer\nByte 1    : IDType[7:4] | UAType[3:0]  (※修正後)\nBytes 2-21: UAS_ID (20B ASCII, null padding)\nBytes 22-24: Reserved (0x00)\n\n例: UAS_ID = 'UAV-ZKP-M1-DEMO00'"})
slides_data.append({"type": "code", "title": "2.7 Location メッセージ詳細 (25B)", "code": "Byte 0    : Header = (Type=1 << 4) | ProtoVer\nByte 1    : Status | HeightType | EWDir | SpeedMult\nBytes 5-8 : Latitude (int32 LE, 1e-7度)\nBytes 9-12: Longitude (int32 LE, 1e-7度)\nBytes 13-14: AltitudeBaro (uint16 LE, (alt+1000)*2)\nBytes 15-16: AltitudeGeo (uint16 LE, (alt+1000)*2)\nBytes 21-22: Timestamp (uint16 LE, 時間内秒 * 10)"})
slides_data.append({"type": "bullets", "title": "2.8 opendroneid-core-c との互換性修正 (1)", "bullets": ["■ C言語の公式リファレンス実装 (opendroneid-core-c) との突き合わせを実施", "■ 誤り: Byte 1 の Status が下位ニブルに配置されていた", "■ 修正: Status は上位4ビット (bits 7:4) に配置し、下位ビットは進行方向等のフラグへ"]})
slides_data.append({"type": "bullets", "title": "2.9 opendroneid-core-c との互換性修正 (2)", "bullets": ["■ 誤り: AIRBORNE（飛行中）ステータスを '1' と定義", "■ 修正: GROUND=1, AIRBORNE=2, EMERGENCY=3。'2' へ変更", "■ 誤り: BasicID の Byte1 ニブル順が逆", "■ 修正: IDTypeを上位、UATypeを下位ニブルへ修正"]})
slides_data.append({"type": "code", "title": "2.10 Raspberry Pi の HCI コマンド直接制御", "code": "# hcitool を用いてカーネルのBluetoothスタックを直接叩く\n# ADV_NONCONN_IND (非接続型ブロードキャスト) に設定\nhcitool cmd 0x08 0x0006 A0 00 A0 00 03 00 00 00 00 00 00 00 00 07 00\n\n# ペイロード設定\nhcitool cmd 0x08 0x0008 1D 1C 16 FA FF [25B Payload] 00 00\n\n# 広告開始\nhcitool cmd 0x08 0x000A 01"})
slides_data.append({"type": "bullets", "title": "2.11 hciconfig UP エラーの解消", "bullets": ["■ Raspberry Pi起動時に `hciconfig hci0 up` を自動実行する際のエラー", "■ アダプタがすでに `UP RUNNING` 状態だとコマンドが終了コード1を返す", "■ Python側の `subprocess.run(check=True)` を外し、すでに起動済みでも例外を出さずに続行するよう修正"]})
slides_data.append({"type": "bullets", "title": "2.12 送信タイミングの多重化", "bullets": ["■ 1つのBLEアドバタイズスロットでは、1種類のメッセージしか送信できない", "■ Location (毎秒必須) と BasicID (数秒に1回) を送る必要がある", "■ remote_id.py にて、1秒ごとにLocationとBasicIDのペイロードを切り替えるローテーション送信を実装"]})

# --- CHAPTER 3: Sensor Integration ---
slides_data.append({"type": "section", "title": "第3章：実機センサー統合 (GPS & BME280)"})
slides_data.append({"type": "bullets", "title": "3.1 静的座標からリアルタイム座標へ", "bullets": ["■ 初期フェーズ: 開発を優先し、緯度・経度・高度を固定値（CLI引数）で送信", "■ 実機統合フェーズ: Raspberry Pi に USB GPSモジュールと I2C BME280(気圧) を接続", "■ ドローンの実際の動きをリアルタイムにBLEブロードキャストする"]})
slides_data.append({"type": "bullets", "title": "3.2 Raspberry Pi のハードウェア構成", "bullets": ["■ GPSモジュール: u-blox製。USB CDCで `/dev/ttyACM0` または `ttyUSB0` として認識", "■ NMEA 0183フォーマットを `pynmea2` で解析 ($GNGGA, $GNRMC)", "■ 気圧センサー: BME280。I2Cでアドレス `0x76` に接続。`smbus2` を用いてアクセス"]})
slides_data.append({"type": "bullets", "title": "3.3 スレッドによる非同期処理", "bullets": ["■ BLE送信（1秒ごと）がセンサー待ちで遅延してはならない", "■ GPS受信を `daemon=True` の別スレッドに分離", "■ シリアル通信を常時監視し、最新の座標をスレッドセーフな変数に保持", "■ メインスレッドは送信タイミングで即座に最新値を読み出す"]})
slides_data.append({"type": "bullets", "title": "3.4 高度比較の根本的な問題", "bullets": ["■ ZKP回路で「スマホとドローンが30m以内か」を判定するためには、両者の高度基準が一致している必要がある", "■ GPS高度(WGS84楕円体高)は垂直誤差が大きく（±10〜30m）、スマホ側との比較に適さない", "■ 標準気圧(1013.25hPa)基準では、天候や気圧配置により1日に数十メートルのブレが生じる"]})
slides_data.append({"type": "bullets", "title": "3.5 QFE (Height Above Takeoff) の導入", "bullets": ["■ 航空業界で用いられるQFE方式を採用", "■ Pi側: スクリプト起動時の気圧を P₀（地上高0m）として記録", "■ スマホ側: アプリ起動時の気圧を P₀（地上高0m）として記録", "■ 双方とも、その後の気圧変化を P₀ からの相対高度(m)に変換する"]})
slides_data.append({"type": "code", "title": "3.6 気圧から相対高度への変換式", "code": "# Pi 側 (Python) / スマホ側 (Dart) 共通\n# 44330 * (1 - (P_now / P0) ^ (1/5.255))\n\nalt_m = 44330.0 * (1.0 - (current_hpa / p0_hpa) ** (1.0 / 5.255))\n\n# OpenDroneID の AltitudeBaro フィールド(0.5m単位, オフセット-1000m)へ変換\nalt_baro_encoded = int((alt_m + 1000.0) * 2)"})
slides_data.append({"type": "bullets", "title": "3.7 QFE方式の効果", "bullets": ["■ ドローンとスマホが同じ場所で起動すれば、それぞれの P₀ が（センサーの個体差はあれど）物理的な「地上」を意味する", "■ 天候変化の影響を P₀ と P_now が同じように受けるため相殺される", "■ 相対高度を用いた距離計算がミリメートル単位で安定するようになった"]})
slides_data.append({"type": "bullets", "title": "3.8 No Fix 対応", "bullets": ["■ GPS衛星の捕捉(Fix)までには起動から数十秒〜数分かかる", "■ Fixしていない間は座標が (0, 0) となる", "■ remote_id.py に No Fix 判定を追加し、捕捉されるまではログに `[NO FIX]` を出力、BLEパケット上も無効値(0)を送出する"]})
slides_data.append({"type": "table", "title": "3.9 使用したPythonライブラリ", "headers": ["ライブラリ", "用途", "インストール方法"], "rows": [["pyserial", "GPSモジュールのシリアル通信", "pip install pyserial"], ["pynmea2", "NMEA文のパース ($GNGGA等)", "pip install pynmea2"], ["smbus2", "I2Cバスの制御", "pip install smbus2"], ["RPi.bme280", "BME280の気圧・温度読み取り", "pip install RPi.bme280"]]})

# --- CHAPTER 4: Flutter App ---
slides_data.append({"type": "section", "title": "第4章：Flutter アプリケーション統合"})
slides_data.append({"type": "bullets", "title": "4.1 アプリの全体構成", "bullets": ["■ ZKP-M1プロジェクトのクライアント側 UI", "■ Flutterフレームワークを採用し、Android (Pixel 8) 実機で動作", "■ 主な機能: BLEスキャン、自身のGPS取得、動画撮影、オンデバイスZK証明", "■ プラットフォームチャネル (FFI) を介して C/C++ / Rust のライブラリと通信"]})
slides_data.append({"type": "bullets", "title": "4.2 flutter_blue_plus によるBLE受信", "bullets": ["■ `FlutterBluePlus.startScan` を用いて周囲のデバイスを25秒間スキャン", "■ Advertisement Packet の `serviceData` から UUID `0xFFFA` を検索", "■ 見つかったペイロード(25B)を `UavTelemetryPacket` クラスに渡してパース"]})
slides_data.append({"type": "code", "title": "4.3 タイムスタンプの復元ロジック", "code": "// OpenDroneIDのTimestampは「時間内の0.1秒単位」(0〜36000)\n// 絶対時刻(Unix Epoch)に戻す必要がある\n\nfinal tsRaw = data.getUint16(21, Endian.little);\nfinal secs = tsRaw ~/ 10;\nfinal nowSec = DateTime.now().millisecondsSinceEpoch ~/ 1000;\nfinal base = nowSec - (nowSec % 3600); // 現在の0分0秒\n\nreturn base + secs;"})
slides_data.append({"type": "bullets", "title": "4.4 位置情報更新頻度のチューニング", "bullets": ["■ `geolocator` パッケージによる自身のGPS取得", "■ 初期実装では `distanceFilter: 0` としていたため、スマホが静止していると位置情報イベントが発火しなかった", "■ 改善: `AndroidSettings(intervalDuration: Duration(seconds: 1))` を指定し、静止中でも毎秒強制的に座標を取得するよう変更"]})
slides_data.append({"type": "bullets", "title": "4.5 動画撮影の安定化", "bullets": ["■ `camera` パッケージを使用", "■ エラー回避: `imageFormatGroup: ImageFormatGroup.jpeg` を削除。Android端末での動画録画との競合を解消", "■ エラーハンドリング: `catch (_)` で握り潰していたエラーを画面に表示し、デバッグを容易にした", "■ 無音録画の明示: `enableAudio: false` を指定"]})
slides_data.append({"type": "bullets", "title": "4.6 コンソールログUIの実装", "bullets": ["■ 背景: BLEの受信状況やZK証明の進行度が画面から分かりにくい", "■ 解決: アプリ内にターミナル風のログビュータブを実装", "■ `_logs.add('[$ts] $msg')` でスタックし、上限200件で古いものから削除", "■ `ScrollController.jumpTo(maxExtent)` で自動スクロール"]})
slides_data.append({"type": "bullets", "title": "4.7 ZK証明ライブラリ: rapidsnark", "bullets": ["■ iden3/rapidsnark の Flutter ラッパー `flutter_rapidsnark` を利用", "■ Groth16アルゴリズムに特化した超高速な証明生成器", "■ スマホのARM CPU上で直接 C++ のロジックが実行される", "■ `.zkey` ファイル（約5MB〜数MB）をアプリのAssetからテンポラリディレクトリへコピーして使用"]})
slides_data.append({"type": "code", "title": "4.8 Witness 計算: circom_witnesscalc", "code": "// Circomが吐き出した .wcd ファイルとJSON入力からWitnessを計算\nfinal inputsJson = jsonEncode({\n  'uav_lat': droneLat,\n  'target_lat': myLat,\n  // ...\n});\n\n// オンデバイスでWitness(中間信号群)を生成\nfinal witness = await witnesscalc.calculateWitness(\n  wcdBytes, inputsJson\n);"})
slides_data.append({"type": "bullets", "title": "4.9 証明生成の実行と検証", "bullets": ["■ 計算した Witness と Asset の `distance30_groth16.zkey` を rapidsnark に渡す", "■ `groth16.prove` で `proof` (証明本体) と `publicSignals` (フラグやハッシュ) が得られる", "■ 同じ端末内で `verification_key.json` を使って検証(`groth16.verify`)を行い、結果を表示"]})
slides_data.append({"type": "table", "title": "4.10 Flutter アプリ依存パッケージ", "headers": ["パッケージ", "用途", "特記事項"], "rows": [["flutter_rapidsnark", "Groth16 証明生成・検証", "iden3製、C++ FFI"], ["circom_witnesscalc", "Witness (.wcd) 計算", "Rust / FFI"], ["flutter_blue_plus", "BLEスキャン", "OpenDroneID受信"], ["geolocator", "GPS取得", "毎秒更新"], ["google_mlkit_*", "AI画像解析", "後述"]]})

# --- CHAPTER 5: AI & Video Evidence ---
slides_data.append({"type": "section", "title": "第5章：AI検知と動画証拠の統合"})
slides_data.append({"type": "bullets", "title": "5.1 ZKPだけでは足りない理由", "bullets": ["■ ZKPは「入力されたGPS座標の距離計算」が正しいことを暗号学的に証明する", "■ しかし「入力されたGPS座標自体が偽装(スプーフィング)されていないか」は証明できない", "■ 対策: 「実際にその時刻・その場所にドローンが飛んでいた」という視覚的証拠(動画)を併用する"]})
slides_data.append({"type": "bullets", "title": "5.2 動画とログの同期", "bullets": ["■ BLEでLocationメッセージを受信した直後に、スマホカメラでの動画録画を自動開始", "■ 録画中の動画フレーム（撮影時刻）と、毎秒取得されるGPS/BLEログを関連付ける", "■ ZKPのPrivate Inputに「動画の撮影開始時刻」を含め、証明結果と映像のリンクを担保する"]})
slides_data.append({"type": "bullets", "title": "5.3 Google ML Kit の限界", "bullets": ["■ 当初、Flutterで容易に組み込める Google ML Kit Object Detection を利用", "■ 汎用的な物体検知モデルであり、「車」「人」などは検知できるが、空中の小さな「ドローン」の検知精度が著しく低かった", "■ 専用のカスタムモデル(YOLO)への移行を決断"]})
slides_data.append({"type": "bullets", "title": "5.4 VisDrone2019 Dataset", "bullets": ["■ ドローン空撮視点および地上からドローンを撮影した大規模データセット", "■ 小物体（Small Objects）の検知に特化している", "■ クラス構成: pedestrian, person, bicycle, car, van, truck, bus, motor等", "■ 注意: 公式のVisDroneには「drone」自体のクラスは含まれていない"]})
slides_data.append({"type": "bullets", "title": "5.5 転移学習 (Transfer Learning) のアプローチ", "bullets": ["■ ステップ1: まず VisDrone2019 全体で YOLOv11 モデルを事前学習(Pre-train)させる", "■ 目的: 小さな物体や複雑な背景から特徴を抽出する「目」をネットワークに獲得させる", "■ ステップ2: 学習済みの重みをベースに、別途用意した「Drone」単一クラスのデータセットで Fine-tuning を行う"]})
slides_data.append({"type": "code", "title": "5.6 DET から YOLO 形式への変換", "code": "# VisDroneのラベル形式をYOLO形式(txt)へ変換するスクリプト\n# scripts/convert_visdrone_det_to_yolo.py\n\ndef convert_box(size, box):\n    dw = 1. / size[0]\n    dh = 1. / size[1]\n    x = (box[0] + box[2]/2.0) * dw\n    y = (box[1] + box[3]/2.0) * dh\n    w = box[2] * dw\n    h = box[3] * dh\n    return (x, y, w, h)"})
slides_data.append({"type": "bullets", "title": "5.7 単一クラス (drone) への Fine-tuning", "bullets": ["■ `uav_drone_single_class.yaml` を定義", "■ `nc: 1` (クラス数1), `names: ['drone']`", "■ YOLOコマンドによる学習実行", "■ `yolo train model=visdrone_pretrained.pt data=uav_drone_single_class.yaml epochs=50`"]})
slides_data.append({"type": "bullets", "title": "5.8 TFLite へのエクスポート", "bullets": ["■ モバイルアプリ(Flutter)で推論を行うため、学習済みPyTorchモデル(.pt)をTensorFlow Lite(.tflite)へ変換する", "■ `scripts/export_visdrone_tflite.sh`", "■ `yolo export model=best.pt format=tflite int8`", "■ INT8量子化を適用し、モデルサイズを縮小して推論速度を向上"]})
slides_data.append({"type": "table", "title": "5.9 Flutter での推論実装", "headers": ["コンポーネント", "役割", "使用パッケージ"], "rows": [["カメラ入力", "動画フレームの取得", "camera"], ["前処理", "画像のRGB変換、リサイズ(640x640)", "image"], ["推論エンジン", "TFLiteモデルの実行", "tflite_flutter"], ["後処理", "NMS(非最大値抑制), Bounding Box描画", "カスタムDartコード"]]})
slides_data.append({"type": "bullets", "title": "5.10 AIパイプラインのまとめ", "bullets": ["■ ML Kitの限界を VisDrone + YOLOv11 + TFLite で克服", "■ 撮影された映像からリアルタイムでドローンを検知", "■ 検知結果（座標、信頼度スコア）をUI上にオーバーレイ表示", "■ この視覚証拠とZKPを統合することで、より強固なシステムが完成する"]})

# --- CHAPTER 6: ZKP Circuits ---
slides_data.append({"type": "section", "title": "第6章：ZKP 回路設計 (Circom)"})
slides_data.append({"type": "bullets", "title": "6.1 Circom と Groth16", "bullets": ["■ Circom: ZK回路を記述するためのDSL(ドメイン固有言語)とコンパイラ", "■ 算術回路（R1CS: Rank-1 Constraint System）を生成する", "■ Groth16: 非常に小さな証明サイズ(数100バイト)と高速な検証を特徴とする証明システム", "■ 制約: Trusted Setup（Trustedな初期設定）が必要"]})
slides_data.append({"type": "bullets", "title": "6.2 基本回路: Distance30mTimeCore", "bullets": ["■ `circuits/lib_uav_safety.circom` に定義されたコアロジック", "■ ドローン座標とターゲット(スマホ)座標を受け取り、距離と時刻差を計算", "■ 座標は 1e-7度単位 の整数として入力される (浮動小数点はZKで扱えないため)"]})
slides_data.append({"type": "code", "title": "6.3 座標から cm スケールへの変換", "code": "// 緯度 1e-7 度 = 約 1.11 cm\n// 経度 1e-7 度 = 約 0.91 cm (日本周辺の概算)\n// 整数演算のみで近似計算を行う\n\nvar LAT_SCALE = 111;\nvar LON_SCALE = 91;\nvar ALT_SCALE = 100; // 0.1m -> cm\n\nsignal lat_diff_scaled <== lat_diff * LAT_SCALE;\nsignal lon_diff_scaled <== lon_diff * LON_SCALE;"})
slides_data.append({"type": "code", "title": "6.4 ピタゴラスの定理と閾値判定", "code": "// ZK内では平方根(ルート)の計算が非常にコストが高いため、\n// 両辺を2乗した状態で比較する\n\nsignal lat_sq <== lat_diff_scaled * lat_diff_scaled;\nsignal lon_sq <== lon_diff_scaled * lon_diff_scaled;\nsignal alt_sq <== alt_diff_scaled * alt_diff_scaled;\nsignal distance_sq <== lat_sq + lon_sq + alt_sq;\n\n// 30m = 3000cm。その2乗 = 9000000\ncomponent comp = LessEqThan(128);\ncomp.in[0] <== distance_sq;\ncomp.in[1] <== 9000000;"})
slides_data.append({"type": "bullets", "title": "6.5 バリアント1: Detection Flag", "bullets": ["■ `distance_30m_time_detection_flag.circom`", "■ 出力は `within30` というブール値(0 or 1)のフラグのみ", "■ ユースケース: 単純に「近づいたかどうか」だけを知りたい場合", "■ 回路サイズが最小で、モバイルでの証明生成が最も速い"]})
slides_data.append({"type": "bullets", "title": "6.6 バリアント2: Detection Commitment", "bullets": ["■ `distance_30m_time_detection_commitment.circom`", "■ フラグに加えて、ドローンとターゲットの入力座標に対する `Poseidon Hash` (コミットメント)を出力", "■ ユースケース: ブロックチェーン上のスマートコントラクトで検証しつつ、後で裁判等で元の座標データを開示(Proof of Knowledge)する必要がある場合"]})
slides_data.append({"type": "bullets", "title": "6.7 Poseidon Hash の選択理由", "bullets": ["■ SHA-256 や Keccak などはビット演算（XOR, AND等）を多用するため、ZK回路で実装すると数万〜数10万以上のConstraintsが発生する", "■ Poseidon は ZK(特にプライムフィールド上の算術演算)に特化して設計されたハッシュ関数", "■ Circomで実装した場合、わずか数百Constraintsで済み、圧倒的に低コスト"]})
slides_data.append({"type": "bullets", "title": "6.8 バリアント3: Feature Classifier", "bullets": ["■ `distance_30m_time_feature_classifier.circom`", "■ 距離の判定だけでなく、速度や高度帯（低空/高空）などの特徴を分類してPublicに出力", "■ ユースケース: 接近の「危険度（Risk Level）」を評価したい場合", "■ 応用例: 30m以内だが相対速度が遅い場合は「注意」、高速な場合は「警告」"]})
slides_data.append({"type": "bullets", "title": "6.9 バリアント4: Time Series (N=20)", "bullets": ["■ `distance_30m_time_series.circom`", "■ 20時点分の座標と時刻を配列として一括で受け取る", "■ 回路内部でループを回して20回分の距離判定を行い、最後に `OR` を取る", "■ 出力: `any_within30` (20点のうち1点でも30m以内に入ったか)"]})
slides_data.append({"type": "bullets", "title": "6.10 Time Series 回路の意義", "bullets": ["■ 実際の通信では、BLEの遅延や欠損、スマホ側の処理落ちでデータポイントの時刻が数秒ズレることがある", "■ 1点ずつの証明では、「映像には映っているのに、その瞬間のログが欠損していて証明できない」事態が起こる", "■ 動画の録画時間(約20秒)の全ログをまとめて証明することで、通信のラグや欠損に強い堅牢な証明が可能になる"]})

# --- CHAPTER 7: ZKP Optimization ---
slides_data.append({"type": "section", "title": "第7章：回路最適化と制約解析"})
slides_data.append({"type": "bullets", "title": "7.1 最適化レベルの比較実験", "bullets": ["■ Circom コンパイラには `--O0`, `--O1`, `--O2` の最適化フラグがある", "■ `scripts/compare_circom_optimizations.sh` を用いて、生成されるConstraints（制約数）やファイルサイズを分析した", "■ 対象回路: `distance_30m_time.circom`"]})
slides_data.append({"type": "table", "title": "7.2 最適化結果サマリー", "headers": ["Level", "Constraints", "Wires", "Substitutions", "R1CS Bytes"], "rows": [["O0 (なし)", "609", "608", "0", "95,444"], ["O1 (標準)", "574 (-5%)", "573", "35", "92,152"], ["O2 (積極)", "534 (-12%)", "533", "75", "106,472"]]})
slides_data.append({"type": "bullets", "title": "7.3 Constraints (制約数) の重要性", "bullets": ["■ ZKPにおいて、Constraints数は証明生成時間(Proving Time)とメモリ消費量に直結する最も重要な指標", "■ O0 -> O2 で制約数が 609 から 534 へ約12%削減された", "■ Wires (中間信号の数) も同様に減少しており、回路の構造が簡略化されていることがわかる"]})
slides_data.append({"type": "bullets", "title": "7.4 線形制約 vs 非線形制約", "bullets": ["■ O0ビルドログ: 534 non-linear, 75 linear constraints", "■ O2ビルドログ: 534 non-linear, 0 linear constraints", "■ 驚くべき事実: 最適化によって消滅したのは「線形制約 (加算や定数乗算)」のみである", "■ 乗算や比較などの「非線形制約」は534個のまま一切減っていない"]})
slides_data.append({"type": "bullets", "title": "7.5 コストの真の要因: 比較演算", "bullets": ["■ 回路のコストの大半を占めているのは `lat_scaled` や `distance_sq` の計算ではない", "■ 真のコストは `LessThan(n)` や `Num2Bits(n)` などの比較・ビット分解テンプレートである", "■ 値の大小比較を行うには、入力値を内部で2進数ビット配列に分解し、各ビットが0か1であること(Booleanity)を制約する必要があるため、ビット幅に比例した膨大な制約が発生する"]})
slides_data.append({"type": "bullets", "title": "7.6 R1CSサイズ増加のパラドックス", "bullets": ["■ O2最適化を適用すると、Constraintsは減るのに `.r1cs` ファイルのサイズが O0 よりも大きくなった(95KB -> 106KB)", "■ 理由: O2では中間変数を削減するために数式を展開(インライン化)するため、1つの制約式に含まれる項(変数)の数が増え、行列の非ゼロ要素が増加するため", "■ 結論: R1CSのファイルサイズは、回路の重さ(証明コスト)の直接的な指標にはならない"]})
slides_data.append({"type": "bullets", "title": "7.7 今後の最適化の方向性", "bullets": ["■ `--O2` は線形オーバーヘッドを消すために必須だが、それ以上の魔法はない", "■ さらなる軽量化には「回路設計自体の見直し」が必要", "■ 具体策1: `LessThan` の呼び出し回数を減らす（不要な境界チェックの削除）", "■ 具体策2: ビット幅 `n` を安全な範囲で小さくする。たとえば `LessEqThan(128)` が本当に128bit必要か検討する"]})

# --- CHAPTER 8: Conclusion ---
slides_data.append({"type": "section", "title": "第8章：結論と今後の展望"})
slides_data.append({"type": "bullets", "title": "8.1 達成された成果 (1/2)", "bullets": ["■ OpenDroneID 準拠: 独自規格を脱却し、ASTM F3411-22a 互換のBLE送信基盤をRaspberry Pi上に構築完了", "■ センサー統合とQFE: GPSとBME280気圧センサーを統合し、QFE方式による高精度な相対高度アライメントを実現"]})
slides_data.append({"type": "bullets", "title": "8.2 達成された成果 (2/2)", "bullets": ["■ オンデバイスZKP: Flutter + rapidsnark により、スマホ単体・オフラインで動作する証明生成・検証フローを確立", "■ AI映像証拠: VisDroneで事前学習したYOLOモデルにより、位置ログだけでなく視覚的な接近証拠を統合"]})
slides_data.append({"type": "bullets", "title": "8.3 今後のロードマップ: 通信拡張", "bullets": ["■ 現状のBLE Legacy Advertising は到達距離が数十m〜100m程度と短い", "■ Bluetooth 5 Extended Advertising (Long Range) への対応", "■ Wi-Fi NaN (Neighbor Awareness Networking) への対応により、数100m〜1kmクラスの通信距離を実現する"]})
slides_data.append({"type": "bullets", "title": "8.4 今後のロードマップ: セキュリティ強化", "bullets": ["■ OpenDroneID の Auth メッセージ (Type=0x2) を受信し、機体の電子署名を検証する", "■ スマホ側でのスプーフィング対策として、OSレベルのLocation Mocking検知機能をアプリに追加する"]})
slides_data.append({"type": "bullets", "title": "8.5 今後のロードマップ: Merkle Proof の統合", "bullets": ["■ 飛行ログのハッシュ木 (Merkle Tree) を構築し、そのルートハッシュをブロックチェーンやIPFSに記録", "■ ZK回路内に Merkle Proof の検証ロジックを追加し、「提供されたログが飛行全体のログの一部であり、改ざんされていないこと」を証明するアーキテクチャへの発展"]})

def build_presentation():
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H
    blank_layout = prs.slide_layouts[6]

    page_num_counter = 1

    for slide_spec in slides_data:
        s = prs.slides.add_slide(blank_layout)
        stype = slide_spec["type"]

        if stype == "title":
            s.background.fill.solid()
            s.background.fill.fore_color.rgb = C_NAVY
            txb(s, slide_spec["title"], M, Inches(2.0), IW, Inches(1.5), size=36, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
            if "sub" in slide_spec:
                txb(s, slide_spec["sub"], M, Inches(4.0), IW, Inches(1.0), size=18, color=RGBColor(200, 220, 255), align=PP_ALIGN.CENTER)
        
        elif stype == "section":
            s.background.fill.solid()
            s.background.fill.fore_color.rgb = C_BLUE
            txb(s, slide_spec["title"], M, Inches(3.0), IW, Inches(1.0), size=32, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)

        elif stype == "bullets":
            apply_header(s, slide_spec["title"], page=page_num_counter)
            render_bullets(s, slide_spec["bullets"], M, Inches(1.5), IW, Inches(5.0), size=14)
            page_num_counter += 1

        elif stype == "code":
            apply_header(s, slide_spec["title"], page=page_num_counter)
            render_code(s, slide_spec["code"], M, Inches(1.5), IW, Inches(5.0), size=12)
            page_num_counter += 1

        elif stype == "table":
            apply_header(s, slide_spec["title"], page=page_num_counter)
            render_table(s, slide_spec["headers"], slide_spec["rows"], M, Inches(1.5), IW)
            page_num_counter += 1

    prs.save(OUTPUT_PATH)
    print(f"✅ Saved: {OUTPUT_PATH} ({len(prs.slides)} slides)")

if __name__ == "__main__":
    build_presentation()
