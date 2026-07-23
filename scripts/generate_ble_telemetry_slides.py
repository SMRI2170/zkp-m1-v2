"""Raspberry Pi BLE テレメトリ + Flutter アプリ 詳細解説スライド

使い方:
  python3 scripts/generate_ble_telemetry_slides.py
"""

from pathlib import Path
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

OUTPUT_PATH = Path("ble_telemetry_opendroneid.pptx")

W = Inches(10)
H = Inches(7.5)
M = Inches(0.45)
IW = W - M * 2

C_BG      = RGBColor(0xFF, 0xFF, 0xFF)
C_BLACK   = RGBColor(0x00, 0x00, 0x00)
C_TEXT    = RGBColor(0x1A, 0x1A, 0x1A)
C_SUB     = RGBColor(0x55, 0x55, 0x55)
C_RULE    = RGBColor(0xCC, 0xCC, 0xCC)
C_LIGHT   = RGBColor(0xF0, 0xF0, 0xF0)
C_BOX     = RGBColor(0xF7, 0xF7, 0xF7)
C_TH_BG   = RGBColor(0x22, 0x22, 0x22)
C_TH_FG   = RGBColor(0xFF, 0xFF, 0xFF)
C_TR1     = RGBColor(0xFF, 0xFF, 0xFF)
C_TR2     = RGBColor(0xF2, 0xF2, 0xF2)

FONT = "Hiragino Sans"
MONO      = "Courier New"
TOTAL     = 14


def set_bg(slide):
    bg = slide.background
    bg.fill.solid()
    bg.fill.fore_color.rgb = C_BG


def rect(slide, l, t, w, h, color, border=False, bc=None):
    s = slide.shapes.add_shape(1, l, t, w, h)
    s.fill.solid()
    s.fill.fore_color.rgb = color
    if border:
        s.line.width = Pt(0.75)
        s.line.color.rgb = bc or C_RULE
    else:
        s.line.fill.background()
    return s


def txb(slide, text, l, t, w, h, size=12, bold=False, color=C_TEXT,
        align=PP_ALIGN.LEFT, italic=False, mono=False):
    box = slide.shapes.add_textbox(l, t, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.color.rgb = color
    r.font.name = MONO if mono else FONT
    return box


def paras(slide, lines, l, t, w, h, size=11, color=C_TEXT, gap=3):
    box = slide.shapes.add_textbox(l, t, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    first = True
    for line in lines:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        r = p.add_run()
        r.text = line
        r.font.size = Pt(size)
        r.font.color.rgb = color
        r.font.name = FONT
        p.space_after = Pt(gap)


def codebox(slide, lines, l, t, w, h, size=9):
    rect(slide, l, t, w, h, C_BOX, border=True)
    paras(slide, lines,
          l + Inches(0.1), t + Inches(0.07),
          w - Inches(0.2), h - Inches(0.14),
          size=size, color=C_TEXT)


def tbl(slide, headers, rows, l, t, w, cw=None, fs=10):
    nr = len(rows) + 1
    nc = len(headers)
    rh = Inches(0.40)
    tb = slide.shapes.add_table(nr, nc, l, t, w, rh * nr).table
    tb.first_row = True
    if cw:
        for i, v in enumerate(cw):
            tb.columns[i].width = v
    else:
        for col in tb.columns:
            col.width = w // nc

    def cs(cell, text, header=False, even=False):
        cell.fill.solid()
        cell.fill.fore_color.rgb = C_TH_BG if header else (C_TR2 if even else C_TR1)
        tf = cell.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        r = p.add_run()
        r.text = text
        r.font.size = Pt(fs)
        r.font.bold = header
        r.font.color.rgb = C_TH_FG if header else C_TEXT
        r.font.name = FONT

    for ci, h in enumerate(headers):
        cs(tb.cell(0, ci), h, header=True)
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cs(tb.cell(ri + 1, ci), val, even=(ri % 2 == 1))


def header(slide, title, sub=None):
    set_bg(slide)
    rect(slide, 0, 0, W, Inches(0.08), C_BLACK)
    rect(slide, 0, Inches(0.08), Inches(0.06), H - Inches(0.08), C_BLACK)
    txb(slide, title, M, Inches(0.13), IW, Inches(0.55), size=22, bold=True, color=C_BLACK)
    if sub:
        txb(slide, sub, M, Inches(0.68), IW, Inches(0.28), size=11, color=C_SUB)
    rect(slide, M, Inches(1.00), IW, Pt(1), C_RULE)


def pnum(slide, n):
    txb(slide, f"{n} / {TOTAL}", W - Inches(0.75), H - Inches(0.32),
        Inches(0.65), Inches(0.25), size=9, color=C_SUB, align=PP_ALIGN.RIGHT)


def sec(slide, text, l, t, w=None):
    if w is None:
        w = IW
    txb(slide, text, l, t, w, Inches(0.35), size=13, bold=True, color=C_BLACK)
    rect(slide, l, t + Inches(0.35), w, Pt(1), C_RULE)


# ─────────────────────────────────────────────────────────────────────────────

def build():
    prs = Presentation()
    prs.slide_width  = W
    prs.slide_height = H
    blank = prs.slide_layouts[6]

    # ── 1. 表紙 ───────────────────────────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    set_bg(sl)
    rect(sl, 0, 0, W, Inches(0.12), C_BLACK)
    rect(sl, 0, H - Inches(0.12), W, Inches(0.12), C_BLACK)

    txb(sl, "ドローン近接証明アプリ", M, Inches(1.0), IW, Inches(0.9),
        size=36, bold=True, color=C_BLACK, align=PP_ALIGN.CENTER)
    txb(sl, "Flutter × OpenDroneID × ZK 証明 実装詳細",
        M, Inches(2.0), IW, Inches(0.5),
        size=18, color=C_SUB, align=PP_ALIGN.CENTER)
    rect(sl, Inches(2.0), Inches(2.65), Inches(6.0), Pt(1.5), C_BLACK)

    paras(sl, [
        "Raspberry Pi（GPS + BME280 + BLE）",
        "Flutter Android アプリ（BLE 受信 / YOLO 検知 / ZK 証明）",
        "Circom 回路（Groth16 証明）",
    ], Inches(2.8), Inches(2.8), Inches(4.4), Inches(1.5), size=13, color=C_TEXT, gap=5)

    txb(sl, "rapidsnark_app/lib/  |  uav/remote_id.py  |  circuits/",
        M, H - Inches(0.45), IW, Inches(0.3), size=9, color=C_SUB, align=PP_ALIGN.CENTER)
    pnum(sl, 1)

    # ── 2. Flutter アプリ全体アーキテクチャ ───────────────────────────────────
    sl = prs.slides.add_slide(blank)
    header(sl, "Flutter アプリ全体アーキテクチャ", "5 つの機能レイヤーが連携する")
    pnum(sl, 2)

    layers = [
        ("UI レイヤー",
         "Material 3 テーマ\nタブ UI（収集 / 証明 / ログ）\nカメラプレビュー・検知オーバーレイ"),
        ("センサーレイヤー",
         "GPS（geolocator）\n気圧（sensors_plus）\nカメラ（camera）"),
        ("通信レイヤー",
         "BLE スキャン（flutter_blue_plus）\nOpenDroneID パース\n22 秒ごと自動再スキャン"),
        ("AI 推論レイヤー",
         "TFLite YOLO（tflite_flutter）\nML Kit フォールバック\n動画フレーム解析"),
        ("ZK 証明レイヤー",
         "circom_witnesscalc\nflutter_rapidsnark\n5 種類の回路プロファイル"),
    ]

    for i, (title, body) in enumerate(layers):
        x = M + Inches(1.82) * i
        rect(sl, x, Inches(1.18), Inches(1.72), Inches(4.2), C_LIGHT, border=True)
        txb(sl, title, x + Inches(0.08), Inches(1.25), Inches(1.56), Inches(0.38),
            size=11, bold=True, color=C_BLACK)
        txb(sl, body, x + Inches(0.08), Inches(1.68), Inches(1.56), Inches(3.5),
            size=10, color=C_TEXT)

    # データフロー矢印
    rect(sl, M, Inches(5.55), IW, Pt(1.5), C_RULE)
    txb(sl, "データフロー（起動時に全レイヤーが同時に初期化される）",
        M, Inches(5.65), IW, Inches(0.3), size=10, color=C_SUB)

    paras(sl, [
        "initState() で並列起動: _startBarometerStream() | _initializeDetectionPipeline()"
        " | _startLocationStream() | _initCameraAndRecord() | _startContinuousBleScan()",
    ], M, Inches(6.00), IW, Inches(0.5), size=10, color=C_TEXT)

    tbl(sl,
        ["メインウィジェット", "役割", "状態管理"],
        [
            ["RapidsnarkApp",       "MaterialApp ルート・Material 3 テーマ適用",      "StatelessWidget"],
            ["SafetyUseCasePage",   "全機能を束ねるメイン画面（タブ / BLE / ZK）",    "StatefulWidget"],
            ["UavLiveDetectionPage","YOLO リアルタイム検知専用ページ",                 "StatefulWidget"],
            ["DroneCameraPageEntry","カメラ + 検知 のエントリーポイント",              "StatelessWidget"],
        ],
        M, Inches(6.52), IW,
        cw=[Inches(2.5), Inches(4.8), Inches(1.6)], fs=10)

    # ── 3. 使用ライブラリ一覧 ─────────────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    header(sl, "使用ライブラリ一覧（pubspec.yaml）", "12 パッケージ + ZK 専用 2 パッケージ")
    pnum(sl, 3)

    tbl(sl,
        ["パッケージ", "バージョン", "カテゴリ", "役割・特記事項"],
        [
            ["flutter_blue_plus",        "^1.35.5",         "BLE",        "BLE スキャン。withServices フィルターを使わず全広告を受信（UUID リストなし問題の回避）"],
            ["geolocator",               "^14.0.2",         "センサー",    "GPS。Android は AndroidSettings で 1 秒ごと強制更新（distanceFilter=0）"],
            ["sensors_plus",             "^7.0.0",          "センサー",    "気圧計（BarometerEvent）。起動時の P₀ を QFE 基準として記録"],
            ["camera",                   "^0.11.2+1",       "カメラ",      "プレビュー・動画録画・YUV420 フレームストリーム取得"],
            ["tflite_flutter",           "^0.11.0",         "AI",         "YOLO TFLite 推論。IsolateInterpreter で UI スレッドをブロックしない"],
            ["google_mlkit_image_labeling","^0.14.2",       "AI",         "YOLO 未配置時のフォールバックラベリング"],
            ["google_mlkit_object_detection","^0.15.1",     "AI",         "物体検知 API（ML Kit 系）"],
            ["image",                    "^4.5.4",          "画像処理",    "YUV420→RGB 変換・リサイズ。YOLO 入力テンソル生成に使用"],
            ["image_picker",             "^1.2.0",          "メディア",    "ギャラリーからの動画選択"],
            ["video_thumbnail",          "^0.5.6",          "メディア",    "動画フレームをサムネイル化してフレーム解析に使用"],
            ["path_provider",            "^2.1.5",          "ファイル",    "zkey / wcd アセットを一時ディレクトリにコピー（ZK 証明に必要）"],
            ["circom_witnesscalc",       "^0.0.1-alpha.1",  "ZK",         "wcd ファイルから witness を計算（Rust バインディング）"],
            ["flutter_rapidsnark",       "git (iden3)",      "ZK",         "Groth16 証明生成・検証（native lib 経由）"],
            ["flutter_riverpod",         "^3.3.1",          "状態管理",    "将来の状態管理拡張用（現在は StatefulWidget 中心）"],
        ],
        M, Inches(1.12), IW,
        cw=[Inches(2.55), Inches(1.25), Inches(1.05), Inches(4.05)], fs=9)

    # ── 4. UI / UX 画面構成 ───────────────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    header(sl, "UI / UX 画面構成", "3 タブ構成 + ライブ検知ページ")
    pnum(sl, 4)

    # タブ 3 つ
    for i, (tab, desc, items) in enumerate([
        ("収集タブ",
         "データを集める画面",
         ["カメラプレビュー（自動録画中）",
          "ドローン入力モード切替（手入力 / BLE）",
          "BLE 受信ボタン + RSSI 表示",
          "端末 GPS / 気圧 自動入力",
          "録画経過タイマー（200ms 更新）",
          "動画解析結果サマリー"]),
        ("証明タブ",
         "ZK 証明を生成・検証する画面",
         ["回路プロファイル選択（5 種類）",
          "証明実行ボタン + 経過タイマー",
          "Public Signals 表示",
          "within30 / distance_ok / time_ok",
          "プライバシー説明文",
          "証明 JSON 展開表示"]),
        ("ログタブ",
         "処理ログをリアルタイム表示",
         ["タイムスタンプ付きログ行",
          "最大 200 件まで保持",
          "最新行に自動スクロール",
          "BLE シーケンス番号",
          "RSSI 値表示",
          "エラー詳細出力"]),
    ]):
        x = M + Inches(3.05) * i
        rect(sl, x, Inches(1.12), Inches(2.90), Inches(5.2), C_LIGHT, border=True)
        txb(sl, tab, x + Inches(0.12), Inches(1.18), Inches(2.66), Inches(0.38),
            size=13, bold=True, color=C_BLACK)
        txb(sl, desc, x + Inches(0.12), Inches(1.58), Inches(2.66), Inches(0.28),
            size=10, italic=True, color=C_SUB)
        rect(sl, x + Inches(0.12), Inches(1.88), Inches(2.66), Pt(0.8), C_RULE)
        paras(sl, [f"・{it}" for it in items],
              x + Inches(0.12), Inches(1.95), Inches(2.66), Inches(4.0),
              size=10, color=C_TEXT, gap=4)

    sec(sl, "テーマ・デザイン", M, Inches(6.45))
    paras(sl, [
        "Material 3 / ColorScheme.fromSeed(seedColor: 0xFF0B6E69)  ← ティール系グリーン",
        "scaffoldBackgroundColor: 0xFFF3F2EA（オフホワイト）。ダーク不使用・明るく清潔感のある配色。",
    ], M, Inches(6.85), IW, Inches(0.55), size=11, color=C_TEXT)

    # ── 5. BLE 受信の詳細実装 ─────────────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    header(sl, "BLE 受信の詳細実装", "flutter_blue_plus × OpenDroneID UUID 0xFFFA")
    pnum(sl, 5)

    sec(sl, "連続スキャン設計（_startContinuousBleScan）", M, Inches(1.12))
    tbl(sl,
        ["動作", "実装"],
        [
            ["起動時に即スキャン開始",   "_restartBleScan() を initState から unawaited で非同期起動"],
            ["22 秒ごとに自動再スキャン", "Timer.periodic(22s) で _restartBleScan() を定期呼び出し"],
            ["スキャン時間",             "FlutterBluePlus.startScan(timeout: 20s)"],
            ["withServices フィルター不使用",
             "remote_id.py は UUID リスト（AD type 0x03）を含まないため、\nAndroid の withServices フィルターだと捨てられてしまう → 全広告を受信"],
        ],
        M, Inches(1.55), IW, cw=[Inches(2.6), Inches(6.3)], fs=10)

    sec(sl, "パケット処理フロー", M, Inches(3.52))
    codebox(sl, [
        "scanResults.listen((results) {",
        "  for (final result in results) {",
        "    final odidBytes = UavTelemetryPacket.extractFromServiceData(",
        "      result.advertisementData.serviceData,   // Map<Guid, List<int>>",
        "    );",
        "    if (odidBytes == null) continue;           // UUID 0xFFFA が無ければスキップ",
        "",
        "    // BasicID（偶数 seq）→ UAS_ID を保持してログ表示",
        "    final uasId = UavTelemetryPacket.tryParseUasId(odidBytes);",
        "    if (uasId != null) { _log('[BLE BasicID] $uasId  rssi=${result.rssi}dBm'); continue; }",
        "",
        "    // Location（奇数 seq）→ フォームに即時反映",
        "    final packet = UavTelemetryPacket.tryParseLocation(odidBytes, _scanSeq++);",
        "    if (packet != null) setState(() => _applyDroneTelemetry(packet));",
        "  }",
        "});",
    ], M, Inches(3.95), IW, Inches(3.35), size=9)

    sec(sl, "UUID 検索の工夫", M, Inches(7.38))
    txb(sl,
        "flutter_blue_plus は serviceData のキーを 128-bit GUID 文字列で返す。"
        "プラットフォームによって大文字/小文字が異なるため key.toString().toLowerCase().contains('fffa') で検索する。",
        M, Inches(7.72), IW, Inches(0.55), size=11, color=C_TEXT)

    # ── 6. GPS + 気圧センサー ─────────────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    header(sl, "GPS + 気圧センサー", "geolocator + sensors_plus で QFE 高度を取得")
    pnum(sl, 6)

    sec(sl, "GPS ストリーム（geolocator）", M, Inches(1.12))
    tbl(sl,
        ["設定項目", "値", "理由"],
        [
            ["accuracy",         "LocationAccuracy.best",        "最高精度モード（GNSS + Wi-Fi 補正）"],
            ["distanceFilter",   "0",                            "移動がなくても毎回コールバックを受け取る"],
            ["intervalDuration", "Duration(seconds: 1)  ※Android のみ", "Android では距離フィルターだけでは不十分。毎秒強制更新で ZK 証明の時刻精度を確保"],
        ],
        M, Inches(1.55), IW, cw=[Inches(1.8), Inches(3.2), Inches(3.9)], fs=10)

    txb(sl,
        "取得した position.latitude / longitude は TextEditingController に直接セット → フォームの値がリアルタイム更新される",
        M, Inches(2.76), IW, Inches(0.4), size=11, color=C_TEXT)

    sec(sl, "気圧センサー（sensors_plus / BarometerEvent）", M, Inches(3.28))
    codebox(sl, [
        "// _startBarometerStream() ── initState から呼び出す",
        "barometer.events.listen((BarometerEvent event) {",
        "  _groundPressureHpa ??= event.pressure;   // 起動時の最初の値を P₀ として固定",
        "  _currentPressureHpa = event.pressure;",
        "  _currentAltitudeMeters = _baroToRelativeAlt(event.pressure);",
        "});",
        "",
        "double _baroToRelativeAlt(double pressureHpa) {",
        "  final p0 = _groundPressureHpa;",
        "  if (p0 == null || p0 <= 0) return 0.0;",
        "  return 44330.0 * (1.0 - math.pow(pressureHpa / p0, 1.0 / 5.255));",
        "}",
    ], M, Inches(3.68), IW, Inches(3.20), size=9)

    sec(sl, "2 種類の高度を ZK 回路に渡す", M, Inches(7.02))
    tbl(sl,
        ["高度の種類", "取得元", "ZK 回路への変換", "用途"],
        [
            ["GPS 高度 (WGS84)",   "position.altitude",        "× 100 → cm 整数", "drone_alt_cm（粗い絶対高度）"],
            ["QFE 高度（相対）",   "BME280 気圧 → 計算式",     "× 100 → cm 整数", "target_alt_cm（精密な相対高度）"],
        ],
        M, Inches(7.42), IW, cw=[Inches(1.8), Inches(2.2), Inches(2.0), Inches(2.9)], fs=10)

    # ── 7. カメラ・録画 ───────────────────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    header(sl, "カメラ・録画の実装", "camera パッケージで自動録画 + フレーム解析")
    pnum(sl, 7)

    sec(sl, "自動録画フロー", M, Inches(1.12))
    paras(sl, [
        "initState → _initCameraAndRecord() → カメラ初期化 → 500ms 待機（バッファ確保）→ 自動録画開始",
        "録画中は 200ms ごとにタイマーで経過時間を更新して UI に表示",
        "同時に _locationHistory と _droneHistory に最大 20 件ずつ位置データを蓄積する",
    ], M, Inches(1.55), IW, Inches(0.85), size=11, color=C_TEXT, gap=4)

    sec(sl, "録画設定", M, Inches(2.52))
    tbl(sl,
        ["設定", "値", "理由"],
        [
            ["ResolutionPreset", "medium",          "YOLO 推論に十分な解像度で録画容量を抑える"],
            ["enableAudio",      "false",            "証拠映像として音声は不要。容量節約"],
            ["imageFormatGroup", "yuv420（ライブ検知時）", "TFLite 入力に必要な YUV420 で取得。動画録画時は省略（一部 Android で競合するため）"],
        ],
        M, Inches(2.95), IW, cw=[Inches(1.6), Inches(2.3), Inches(5.0)], fs=10)

    sec(sl, "録画停止後の処理（_stopRecordingAndPrepare）", M, Inches(4.18))
    codebox(sl, [
        "1. ctrl.stopVideoRecording()  → XFile を取得",
        "2. VideoEvidence オブジェクトに path / 開始時刻 / 終了時刻 を記録",
        "3. _selectBestDataPair()  ← 録画中に蓄積したデータから最適ペアを選ぶ",
        "   録画中に取得した _droneHistory（BLE）× _locationHistory（GPS）の全組み合わせを総当たり",
        "   → 時刻差が最小のペアを自動選択してフォームに反映",
        "4. _analyzeVideoEvidence()  ← 動画フレームを YOLO / ML Kit で解析（非同期）",
    ], M, Inches(4.60), IW, Inches(2.30), size=9)

    sec(sl, "ライブ検知用フレームストリーム", M, Inches(7.05))
    paras(sl, [
        "controller.startImageStream(_onCameraImage)  → 毎フレーム YUV420 をコールバックで受け取る",
        "350ms のクールダウンで推論頻度を制限（UI スレッド負荷を下げる）",
        "YUV420 → RGB 変換は _cameraImageToRgb() で手動実装（YUV 数式変換）",
    ], M, Inches(7.42), IW, Inches(0.85), size=11, color=C_TEXT, gap=4)

    # ── 8. YOLO ドローン検知 ─────────────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    header(sl, "YOLO ドローン検知", "tflite_flutter × IsolateInterpreter × NMS")
    pnum(sl, 8)

    sec(sl, "モデル優先度（候補を上から順に試す）", M, Inches(1.12))
    tbl(sl,
        ["優先", "config アセット", "モデル説明"],
        [
            ["1 位", "uav_visdrone_finetuned_config.json", "VisDrone で事前学習 → UAV データでファインチューニング（最優先）"],
            ["2 位", "uav_roboflow_drone_config.json",     "Roboflow UAV 専用データセットで学習したモデル"],
            ["3 位", "uav_yolo_config.json",               "デフォルト YOLO モデル（汎用）"],
            ["なし", "（フォールバック）",                 "YOLO が使えない場合は google_mlkit_image_labeling で軽量ラベリング"],
        ],
        M, Inches(1.55), IW, cw=[Inches(0.65), Inches(3.15), Inches(5.1)], fs=10)

    sec(sl, "推論パイプライン（UavYoloDetector）", M, Inches(3.00))
    codebox(sl, [
        "detectImage(img.Image image)",
        "  ↓ copyResize() でモデル入力サイズにリサイズ（NHWC / NCHW 自動判定）",
        "  ↓ _buildInputTensor()  → Float32List に正規化（÷255）",
        "  ↓ isolateInterpreter.run()  ← 別 Isolate で推論（UI スレッドをブロックしない）",
        "  ↓ _parseDetections()  → 出力テンソルを [N, 5+classes] に変換",
        "       usesObjectness=true なら row[4]=objectness × row[5..]=クラス確率",
        "       usesObjectness=false なら row[4..]=クラス確率（YOLOv8 デフォルト）",
        "  ↓ _nonMaximumSuppression()  IoU 閾値でボックス重複除去",
        "  ↓ スコア降順ソート → 上位 6 件を UI に表示",
    ], M, Inches(3.43), IW, Inches(2.65), size=9)

    sec(sl, "検知オーバーレイ（CustomPainter）", M, Inches(6.22))
    tbl(sl,
        ["要素", "実装"],
        [
            ["バウンディングボックス", "Canvas.drawRect  赤線（strokeWidth=2）"],
            ["ラベル＋スコア",         "TextPainter → 黒背景矩形の上に白テキストを描画"],
            ["座標変換",               "imageSize → 画面 Size にスケーリング（scaleX / scaleY）"],
            ["再描画タイミング",       "shouldRepaint: detections リストが変わったときだけ再描画"],
        ],
        M, Inches(6.62), IW, cw=[Inches(2.2), Inches(6.7)], fs=10)

    # ── 9. 動画解析フロー ─────────────────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    header(sl, "動画解析フロー", "video_thumbnail でフレームを抽出 → YOLO / ML Kit で判定")
    pnum(sl, 9)

    sec(sl, "解析ステップ", M, Inches(1.12))
    codebox(sl, [
        "_analyzeVideoEvidence()  ── 録画停止後に自動実行",
        "",
        "Step 1: video_thumbnail.ThumbnailUtils.thumbnailFile()",
        "        動画の代表フレームを JPEG で抽出（timeMs を変えて複数枚）",
        "",
        "Step 2: _yoloDetector が有効なら detectImageFile(framePath)",
        "        → UavYoloDetection のリスト（label / score / bounding box）",
        "",
        "Step 3: YOLO 無効または補完として ML Kit を実行",
        "        ImageLabeler.processImage() → EntityAnnotation のリスト",
        "",
        "Step 4: _looksLikeUavLabel() でラベルを UAV 系かどうか判定",
        "        'drone', 'uav', 'aerial', 'aircraft' 等のキーワードに一致すれば陽性",
        "",
        "Step 5: _uavDetectedInVideo = true なら ZK 証明の実行をアンロック",
    ], M, Inches(1.55), IW, Inches(3.85), size=9)

    sec(sl, "検知スコアの ZK 入力変換", M, Inches(5.55))
    paras(sl, [
        "_estimateDetectionScoreBps() → 検知信頼度を bps（ベーシスポイント）単位の整数に変換",
        "例: confidence=0.87  →  (0.87 × 10000).round() = 8700  → ZK 回路の detection_score_bps に入力",
        "ZK 回路は整数演算のみのため、float を使わずスケーリングして整数化する",
    ], M, Inches(5.92), IW, Inches(0.95), size=11, color=C_TEXT, gap=4)

    sec(sl, "VideoDetectionDetail（フレームごとの記録）", M, Inches(7.02))
    tbl(sl,
        ["フィールド", "内容"],
        [
            ["timeMs",      "動画内の時刻（ミリ秒）"],
            ["backend",     "使用したバックエンド名（'YOLO TFLite' / 'ML Kit'）"],
            ["labels",      "検知ラベル一覧（'drone:0.87' 形式の文字列リスト）"],
            ["previewPath", "サムネイル画像のパス"],
            ["regions",     "YOLO のバウンディングボックスリスト（VideoDetectedRegion）"],
        ],
        M, Inches(7.42), IW, cw=[Inches(1.5), Inches(7.4)], fs=10)

    # ── 10. ZK 証明パイプライン ───────────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    header(sl, "ZK 証明パイプライン", "circom_witnesscalc + flutter_rapidsnark で端末内完結")
    pnum(sl, 10)

    sec(sl, "証明の流れ（全処理がスマホ内で完結）", M, Inches(1.12))
    steps = [
        ("① アセット展開",
         "zkey / wcd をバンドルアセットから\n一時ディレクトリにコピー\n（path_provider）"),
        ("② witness 計算",
         "circom_witnesscalc で\n入力 JSON → witness バイナリ生成\n（Rust バインディング）"),
        ("③ Groth16 証明",
         "flutter_rapidsnark で\nwitness + zkey → proof JSON\n（native lib）"),
        ("④ 検証",
         "verification_key.json + public signals\n→ verify() で真偽を確認\n結果を UI に表示"),
    ]
    for i, (title, body) in enumerate(steps):
        x = M + Inches(2.28) * i
        rect(sl, x, Inches(1.55), Inches(2.12), Inches(1.75), C_LIGHT, border=True)
        txb(sl, title, x + Inches(0.1), Inches(1.62), Inches(1.92), Inches(0.38),
            size=11, bold=True, color=C_BLACK)
        txb(sl, body, x + Inches(0.1), Inches(2.02), Inches(1.92), Inches(1.22),
            size=10, color=C_TEXT)
        if i < 3:
            txb(sl, "→", x + Inches(2.12), Inches(2.1), Inches(0.18), Inches(0.5),
                size=16, bold=True, color=C_SUB, align=PP_ALIGN.CENTER)

    sec(sl, "入力値の変換（座標の正規化）", M, Inches(3.45))
    codebox(sl, [
        "// 緯度を正値の整数に: -90°〜+90° → 0〜1,800,000,000",
        "int _normalizeLatitude(String v)  => ((double.parse(v) + 90.0) * 1e7).round();",
        "",
        "// 経度を正値の整数に: -180°〜+180° → 0〜3,600,000,000",
        "int _normalizeLongitude(String v) => ((double.parse(v) + 180.0) * 1e7).round();",
        "",
        "// 高度をセンチメートル整数に",
        "int _metersToCentimeters(String v) => (double.parse(v) * 100).round();",
        "",
        "// → ZK 回路は整数演算のみ。float をそのまま渡せないため全値を整数化する",
    ], M, Inches(3.88), IW, Inches(2.90), size=9)

    sec(sl, "証明実行中のタイマー表示", M, Inches(6.92))
    paras(sl, [
        "証明開始時に _proofStartedAt を記録し、Timer.periodic(1s) でカウントアップ表示",
        "Groth16 証明生成は数秒〜十数秒かかるため、ユーザーに待機中であることを明示する UX 上の工夫",
        "証明完了後は _proofElapsed に経過時間を保持してログに記録",
    ], M, Inches(7.30), IW, Inches(0.95), size=11, color=C_TEXT, gap=4)

    # ── 11. 5 種類の回路プロファイル ─────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    header(sl, "5 種類の ZK 回路プロファイル", "用途に応じて証明の強度・内容を選択できる")
    pnum(sl, 11)

    tbl(sl,
        ["プロファイル", "label", "証明内容", "動画必要", "追加入力"],
        [
            ["Base",
             "distance30",
             "距離（30 m 以内）と時刻（5 秒以内）だけを証明する最小構成",
             "不要", "なし"],
            ["Detection Flag",
             "distance30_detection_flag",
             "距離・時刻 + UAV 検知フラグ・スコア・クラスを追加",
             "必要", "detection_flag, detection_score_bps, class_id"],
            ["Commitment",
             "distance30_detection_commitment",
             "座標を Poseidon ハッシュでコミットメント化。\n座標非公開でも接近と検知を証明",
             "不要", "Poseidon hash commitment"],
            ["Feature Classifier",
             "distance30_feature_classifier",
             "外部抽出した特徴量を小さな分類器で評価する拡張案",
             "必要", "feature vector"],
            ["Time Series (20点)",
             "distance30_time_series",
             "録画中に収集した最大 20 ペアの時系列データを使用。\n1 点でも接近していれば接近を証明",
             "不要", "20 ペアの lat/lon/alt/time"],
        ],
        M, Inches(1.12), IW,
        cw=[Inches(2.0), Inches(2.2), Inches(3.4), Inches(0.8), Inches(0.5)], fs=9)

    sec(sl, "Time Series プロファイルの入力構築", M, Inches(4.62))
    codebox(sl, [
        "_buildTimeSeriesInputPayload()",
        "  ↓ _droneHistory（最大 20 件の BLE 受信履歴）× _locationHistory（GPS 履歴）",
        "  ↓ 時刻差が最小のペアを 20 組選択",
        "  ↓ 各ペアを [drone_lat_0, drone_lon_0, ... drone_lat_19, drone_lon_19]",
        "      [user_lat_0,  user_lon_0,  ... user_lat_19,  user_lon_19] にシリアライズ",
        "  ↓ 20 組のうち 1 組でも within30=1 なら回路全体の出力 within30=1",
    ], M, Inches(5.05), IW, Inches(2.10), size=9)

    sec(sl, "回路アセットの構成", M, Inches(7.28))
    tbl(sl,
        ["ファイル", "用途"],
        [
            ["*.zkey",              "Groth16 証明鍵（rapidsnark が使用）。起動時に一時 Dir にコピー"],
            ["*.wcd",               "witness 計算バイナリ（circom_witnesscalc が使用）。同様にコピー"],
            ["*_verification_key.json", "検証鍵（verify 時に使用）。アセットから直接 JSON ロード"],
        ],
        M, Inches(7.68), IW, cw=[Inches(2.5), Inches(6.4)], fs=10)

    # ── 12. データ蓄積と最適ペア選択 ─────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    header(sl, "データ蓄積と最適ペア自動選択", "録画中に蓄積した履歴から最も信頼性の高いペアを選ぶ")
    pnum(sl, 12)

    sec(sl, "録画中のデータ蓄積", M, Inches(1.12))
    tbl(sl,
        ["データ", "クラス", "蓄積条件", "最大件数"],
        [
            ["ドローン位置履歴", "_droneHistory: List<UavTelemetryPacket>",
             "BLE Location パケット受信のたびに追加（録画中のみ）", "20 件"],
            ["ユーザー位置履歴", "_locationHistory: List<PositionSnapshot>",
             "GPS コールバック（1秒ごと）で追加（録画中のみ）",  "20 件"],
        ],
        M, Inches(1.55), IW, cw=[Inches(1.7), Inches(3.3), Inches(3.1), Inches(0.8)], fs=10)

    sec(sl, "最適ペア選択アルゴリズム（_selectBestDataPair）", M, Inches(2.95))
    codebox(sl, [
        "// 全組み合わせを総当たりして時刻差が最小のペアを選ぶ O(n²)",
        "for (final drone in _droneHistory) {        // 最大 20 件",
        "  for (final loc in _locationHistory) {     // 最大 20 件",
        "    final diff = (drone.unixTimeSec - loc.unixTimeSec).abs();",
        "    if (diff < minDiff) {",
        "      minDiff = diff;",
        "      bestDrone = drone;",
        "      bestLocation = loc;",
        "    }",
        "  }",
        "}",
        "// → 選ばれたペアを自動的にフォームに反映",
        "// → ログに「時刻差 Ns」を出力",
    ], M, Inches(3.38), IW, Inches(3.00), size=9)

    sec(sl, "なぜ「時刻差最小」か", M, Inches(6.52))
    paras(sl, [
        "ZK 回路の time_ok は「ドローンとユーザーの時刻差が 5 秒以内か」を判定する。",
        "録画開始〜停止の間に BLE と GPS の受信タイミングがずれるため、",
        "最も近い時刻のペアを使うことで time_ok=1（成立）になる確率を最大化する。",
        "同時に distance_ok の判定精度も上がる（時刻が近いほど「同じ瞬間の位置」に近いため）。",
    ], M, Inches(6.88), IW, Inches(1.30), size=11, color=C_TEXT, gap=4)

    # ── 13. Raspberry Pi 側との連携まとめ ────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    header(sl, "Raspberry Pi 側との連携まとめ", "送信側（Pi）と受信側（Flutter）の対称設計")
    pnum(sl, 13)

    tbl(sl,
        ["処理", "Raspberry Pi 側", "Flutter アプリ側"],
        [
            ["位置取得",
             "GPS シリアル NMEA → pyserial / pynmea2",
             "Geolocator.getPositionStream（毎秒更新）"],
            ["高度取得",
             "BME280 気圧 → smbus2 → QFE 高度",
             "BarometerEvent → QFE 高度（同じ式）"],
            ["高度基準",
             "起動時 P₀ を記録（_ground_pressure_hpa）",
             "起動時 P₀ を記録（_groundPressureHpa??=）"],
            ["高度計算式",
             "44330 × (1 − (P/P₀)^0.19)",
             "44330.0 × (1.0 − pow(P/P₀, 1/5.255))"],
            ["BLE 送信",
             "hcitool HCI コマンド → ADV_NONCONN_IND",
             "（受信側）flutter_blue_plus.startScan"],
            ["パケット形式",
             "OpenDroneID 25 byte（BasicID / Location 交互）",
             "UUID 0xFFFA → tryParseLocation / tryParseUasId"],
            ["タイムスタンプ",
             "(unix_sec % 3600) × 10 → uint16 LE",
             "tsRaw ÷ 10 + hourStart → Unix 秒に再構築"],
            ["緯度・経度エンコード",
             "float × 1e7 → int32 LE",
             "int32 ÷ 1e7 → float"],
        ],
        M, Inches(1.12), IW,
        cw=[Inches(1.7), Inches(3.5), Inches(3.7)], fs=10)

    sec(sl, "依存ライブラリ対照", M, Inches(5.82))
    tbl(sl,
        ["機能", "Pi 側（Python）", "Flutter 側（Dart）"],
        [
            ["GPS",      "pyserial + pynmea2",        "geolocator"],
            ["気圧",     "smbus2 + RPi.bme280",       "sensors_plus（BarometerEvent）"],
            ["BLE 送信", "subprocess + hcitool",      "flutter_blue_plus（受信側）"],
            ["ZK",       "snarkjs / rapidsnark (CLI)", "circom_witnesscalc + flutter_rapidsnark"],
        ],
        M, Inches(6.22), IW,
        cw=[Inches(1.4), Inches(3.4), Inches(4.1)], fs=10)

    # ── 14. まとめ ────────────────────────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    header(sl, "まとめ", "7 つの技術が 1 つのアプリで連携する")
    pnum(sl, 14)

    items = [
        ("BLE 受信（flutter_blue_plus）",
         "UUID 0xFFFA を目印に OpenDroneID パケットを受信。withServices フィルター非使用で全広告を拾う。22 秒ごとに自動再スキャン。"),
        ("GPS + 気圧（geolocator + sensors_plus）",
         "GPS を毎秒強制更新。BME280 と同じ QFE 式でスマホの気圧計から相対高度を計算し Pi 側と基準を統一。"),
        ("カメラ・録画（camera）",
         "起動直後に自動録画開始。録画中は BLE × GPS の履歴を最大 20 件ずつ蓄積。停止後に最適ペアを自動選択。"),
        ("YOLO 検知（tflite_flutter）",
         "IsolateInterpreter で別 Isolate 推論（UI ブロックなし）。NMS で重複除去。検知できなければ ML Kit にフォールバック。"),
        ("動画解析（video_thumbnail + ML Kit）",
         "録画後に自動でフレーム抽出 → YOLO / ML Kit でドローン検知 → 検知スコアを bps 整数に変換して ZK 回路に渡す。"),
        ("ZK 証明（circom_witnesscalc + flutter_rapidsnark）",
         "witness 計算 → Groth16 証明 → 検証まで端末内で完結。5 種類のプロファイルから用途に応じた回路を選択できる。"),
        ("UI / UX",
         "Material 3 ティール系テーマ。3 タブ構成（収集 / 証明 / ログ）。証明中タイマー・RSSI 表示・検知オーバーレイなどリアルタイム性を重視。"),
    ]

    for i, (title, body) in enumerate(items):
        y = Inches(1.12) + Inches(0.87) * i
        rect(sl, M, y, Inches(0.42), Inches(0.78), C_BLACK)
        txb(sl, str(i + 1), M + Inches(0.04), y + Inches(0.16),
            Inches(0.34), Inches(0.42),
            size=20, bold=True, color=C_BG, align=PP_ALIGN.CENTER)
        txb(sl, title, M + Inches(0.52), y + Inches(0.04),
            IW - Inches(0.52), Inches(0.32),
            size=12, bold=True, color=C_BLACK)
        txb(sl, body, M + Inches(0.52), y + Inches(0.36),
            IW - Inches(0.52), Inches(0.45),
            size=10, color=C_TEXT)

    rect(sl, M, H - Inches(0.42), IW, Pt(1), C_RULE)
    txb(sl, "rapidsnark_app/lib/  ×  uav/remote_id.py  ×  circuits/distance_30m_time*.circom",
        M, H - Inches(0.36), IW, Inches(0.28), size=9, color=C_SUB, align=PP_ALIGN.CENTER)

    prs.save(str(OUTPUT_PATH))
    print(f"保存完了: {OUTPUT_PATH}  ({TOTAL} スライド)")


if __name__ == "__main__":
    build()
