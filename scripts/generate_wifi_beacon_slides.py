#!/usr/bin/env python3
"""WiFi Beacon / NAN (OpenDroneID) 受信対応のまとめスライドを生成する。

デザイン方針:
  - 白背景 / 黒文字
  - 重要な部分のみ青文字（インディゴブルー）
  - 4:3 (10 x 7.5 inch)
  - 和文 Yu Gothic / 等幅 Courier New
構成方針:
  - 目次 + 章扉で章立て / 図解を多めに
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# ── 配色 ─────────────────────────────────────────────
BLACK = RGBColor(0x1A, 0x1A, 0x1A)
BLUE = RGBColor(0x1E, 0x40, 0xAF)   # インディゴブルー（対応・強調）
ISSUE = RGBColor(0xB1, 0x5A, 0x00)  # アンバー（課題）
GREEN = RGBColor(0x2E, 0x7D, 0x32)  # 対応済み
GRAY = RGBColor(0x70, 0x70, 0x70)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LINE = RGBColor(0xD9, 0xD9, 0xD9)
CODEBG = RGBColor(0xF2, 0xF4, 0xF8)

JP_FONT = "Yu Gothic"
MONO_FONT = "Courier New"

prs = Presentation()
prs.slide_width = Inches(10)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


def add_slide():
    slide = prs.slides.add_slide(BLANK)
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = WHITE
    return slide


def textbox(slide, left, top, width, height):
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame
    tf.word_wrap = True
    return tf


def set_run(run, text, size, color=BLACK, bold=False, mono=False):
    run.text = text
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold
    run.font.name = MONO_FONT if mono else JP_FONT


def header(slide, title, kicker=None):
    """各スライド共通の見出し（青の細い下線つき）。"""
    if kicker:
        tf = textbox(slide, 0.6, 0.42, 9.0, 0.4)
        p = tf.paragraphs[0]
        set_run(p.add_run(), kicker, 13, GRAY, bold=True)
    tf = textbox(slide, 0.6, 0.74, 9.0, 0.9)
    p = tf.paragraphs[0]
    set_run(p.add_run(), title, 27, BLACK, bold=True)
    ln = slide.shapes.add_shape(1, Inches(0.62), Inches(1.56), Inches(2.4), Pt(3))
    ln.fill.solid()
    ln.fill.fore_color.rgb = BLUE
    ln.line.fill.background()
    ln.shadow.inherit = False


def bullet(tf, segments, size=15, space_before=8, level=0):
    """segments: [(text, is_blue, is_mono), ...] を 1 行として追加。"""
    p = tf.add_paragraph()
    p.space_before = Pt(space_before)
    p.space_after = Pt(0)
    indent = "    " * level
    marker = "・" if level == 0 else "– "
    set_run(p.add_run(), indent + marker, size, BLACK)
    for text, is_blue, is_mono in segments:
        set_run(p.add_run(), text, size, BLUE if is_blue else BLACK, bold=is_blue, mono=is_mono)


def section(tf, text, space_before=14):
    p = tf.add_paragraph()
    p.space_before = Pt(space_before)
    set_run(p.add_run(), text, 16, BLACK, bold=True)


def pa(tf, problem, action_segments, size=14, space_before=14):
    """「課題 → 対応」の 2 行ブロックを追加する。
    action_segments: [(text, is_blue, is_mono), ...]"""
    p = tf.add_paragraph()
    p.space_before = Pt(space_before)
    set_run(p.add_run(), "課題  ", size - 1, ISSUE, bold=True)
    set_run(p.add_run(), problem, size, BLACK)
    p2 = tf.add_paragraph()
    p2.space_before = Pt(2)
    set_run(p2.add_run(), "→ 対応  ", size - 1, BLUE, bold=True)
    for text, is_blue, is_mono in action_segments:
        set_run(p2.add_run(), text, size, BLUE if is_blue else BLACK,
                bold=is_blue, mono=is_mono)


def codebox(slide, left, top, width, height, lines):
    """等幅のコード/データ表示ボックス。lines: [(text, is_blue), ...]"""
    box = slide.shapes.add_shape(1, Inches(left), Inches(top), Inches(width), Inches(height))
    box.fill.solid()
    box.fill.fore_color.rgb = CODEBG
    box.line.color.rgb = LINE
    box.line.width = Pt(1.0)
    box.shadow.inherit = False
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Pt(10)
    tf.margin_right = Pt(10)
    tf.margin_top = Pt(8)
    tf.margin_bottom = Pt(8)
    for i, (text, is_blue) in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_before = Pt(0)
        p.space_after = Pt(0)
        set_run(p.add_run(), text, 11.5, BLUE if is_blue else BLACK, mono=True)
    return box


def rounded(slide, left, top, width, height, edge, weight=1.4, fill=WHITE):
    box = slide.shapes.add_shape(5, Inches(left), Inches(top), Inches(width), Inches(height))
    box.fill.solid()
    box.fill.fore_color.rgb = fill
    box.line.color.rgb = edge
    box.line.width = Pt(weight)
    box.shadow.inherit = False
    return box


def center_label(slide, left, top, width, text, size, color, bold=True):
    tf = textbox(slide, left, top, width, 0.5)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    set_run(p.add_run(), text, size, color, bold=bold)
    return tf


def divider(num, title, subtitle):
    """章扉スライド。"""
    s = add_slide()
    tf = textbox(s, 0.92, 2.05, 8.2, 1.3)
    set_run(tf.paragraphs[0].add_run(), num, 52, BLUE, bold=True)
    bar = s.shapes.add_shape(1, Inches(0.97), Inches(3.42), Inches(2.6), Pt(3))
    bar.fill.solid(); bar.fill.fore_color.rgb = BLUE
    bar.line.fill.background(); bar.shadow.inherit = False
    tf = textbox(s, 0.94, 3.58, 8.4, 0.9)
    set_run(tf.paragraphs[0].add_run(), title, 30, BLACK, bold=True)
    tf = textbox(s, 0.96, 4.5, 8.2, 0.6)
    set_run(tf.paragraphs[0].add_run(), subtitle, 14, GRAY)
    return s


# ════════════════════════════════════════════════════
# Slide — タイトル
# ════════════════════════════════════════════════════
s = add_slide()
bar = s.shapes.add_shape(1, Inches(0.85), Inches(2.35), Inches(0.12), Inches(1.05))
bar.fill.solid(); bar.fill.fore_color.rgb = BLUE
bar.line.fill.background(); bar.shadow.inherit = False

tf = textbox(s, 1.05, 2.5, 8.4, 1.2)
p = tf.paragraphs[0]
set_run(p.add_run(), "アプリを ", 34, BLACK, bold=True)
set_run(p.add_run(), "WiFi", 34, BLUE, bold=True)
set_run(p.add_run(), " 受信に対応", 34, BLACK, bold=True)

tf = textbox(s, 1.07, 3.7, 8.2, 0.6)
set_run(tf.paragraphs[0].add_run(),
        "DJI 等の Remote ID (OpenDroneID) を WiFi 経由で検知できるようにした", 16, GRAY)

tf = textbox(s, 1.07, 6.5, 8.0, 0.5)
set_run(tf.paragraphs[0].add_run(),
        "rapidsnark_app  /  Flutter + Android ネイティブ (Kotlin)", 12, GRAY, mono=True)

# ════════════════════════════════════════════════════
# Slide — 目次
# ════════════════════════════════════════════════════
chapters = [
    ("01", "背景と仕組み", "なぜ WiFi 検知が必要か / Beacon の中身"),
    ("02", "実装", "ネイティブ + Dart で受信〜証明へ合流"),
    ("03", "画面 (UI)", "受信経路の可視化 / WiFi Raw タブ"),
    ("04", "受信の網羅と設計", "Beacon + NAN / スキャン1本化 / 重複防止"),
    ("05", "評価と考察", "BLE 比較 / セキュリティ / 今後"),
    ("06", "品質と検証", "見つかった課題と対応 / テスト・ビルド"),
]
s = add_slide()
header(s, "目次", "Agenda")
tf = textbox(s, 0.75, 1.95, 8.6, 5.2)
for num, title, desc in chapters:
    p = tf.add_paragraph()
    p.space_before = Pt(14)
    set_run(p.add_run(), num + "   ", 18, BLUE, bold=True)
    set_run(p.add_run(), title, 17, BLACK, bold=True)
    p2 = tf.add_paragraph()
    p2.space_before = Pt(1)
    set_run(p2.add_run(), "        " + desc, 12, GRAY)

# ════════════════════════════════════════════════════
# 章 01 — 背景と仕組み
# ════════════════════════════════════════════════════
divider("01", "背景と仕組み", "なぜ WiFi 検知が必要か / Beacon の中身")

# 背景・課題
s = add_slide()
header(s, "なぜ対応したか", "背景・課題")
tf = textbox(s, 0.65, 1.9, 8.8, 5.2)
bullet(tf, [("これまでドローンの Remote ID は ", False, False),
            ("BLE のみ", True, False), (" で受信していた", False, False)], 16)
bullet(tf, [("BLE スキャンで OpenDroneID の Service Data / Manufacturer Data を解析", False, False)],
       14, level=1)
bullet(tf, [("しかし ", False, False), ("DJI など市販ドローンの多くは ", False, False),
            ("WiFi Beacon", True, False), (" で送信", False, False)], 16, space_before=12)
bullet(tf, [("→ ", False, False), ("従来の BLE スキャンでは DJI を全く捕捉できない", True, False)],
       16, level=1)
bullet(tf, [("Remote ID の送信方式（ASTM F3411）は複数ある", False, False)], 16, space_before=12)
bullet(tf, [("Bluetooth Legacy(BT4) / Long Range(BT5)", False, True),
            ("  … 本アプリは BLE で対応済み", False, False)], 14, level=1)
bullet(tf, [("WiFi Beacon / WiFi NAN", False, True),
            ("  … ", False, False),
            ("DJI の主流。Beacon を中心に対応（NAN も追加）", True, False)], 14, level=1)
bullet(tf, [("目標: ", False, False),
            ("WiFi の Remote ID を受信し、既存の ZK 証明フローにそのまま合流させる", True, False)],
       16, space_before=14)

# WiFi Beacon フォーマット（詳細）
s = add_slide()
header(s, "WiFi Beacon の中身", "仕組み① フォーマット")
tf = textbox(s, 0.65, 1.85, 8.8, 1.5)
bullet(tf, [("ビーコンフレーム内の ", False, False),
            ("ベンダ固有 Information Element (IE)", True, False),
            (" に埋め込む", False, False)], 15)
bullet(tf, [("element id = ", False, False), ("221 (0xDD)", False, True),
            (" / ASTM の OUI = ", False, False), ("FA 0B BC", False, True)], 15)

codebox(s, 0.85, 3.35, 8.3, 2.05, [
    ("IE content (vendor specific)", False),
    ("┌──────────┬────┬─────────┬──────────────┐", False),
    ("│ FA 0B BC │ 0D │ counter │ message pack │", True),
    ("└──────────┴────┴─────────┴──────────────┘", False),
    ("  OUI(3)    type  1 byte    0xFn 始まり", False),
    ("  ← この 5 バイトを除いた残りが OpenDroneID 本体 →", True),
])

tf = textbox(s, 0.65, 5.6, 8.8, 1.6)
bullet(tf, [("message pack は ", False, False), ("0xFn", False, True),
            (" で始まり、25バイトのメッセージ列を内包", False, False)], 14)
bullet(tf, [("type=1 Location", False, True), ("（緯度経度高度時刻）, ", False, False),
            ("type=0 BasicID", False, True), (", ", False, False),
            ("type=4 System", False, True)], 14)
bullet(tf, [("→ ", False, False),
            ("BLE と全く同じメッセージ構造なので、既存パーサを再利用できる", True, False)], 14)

# 図解: 対応する送信方式の俯瞰
s = add_slide()
header(s, "対応する Remote ID 送信方式", "仕組み③ 全体像")
center_label(s, 0.6, 1.75, 8.8, "ドローンが Remote ID を送信", 14, GRAY)
center_label(s, 0.6, 2.12, 8.8, "▼", 12, GRAY)

cards = [
    ("Bluetooth", "Legacy (BT4)", "対応済み", GREEN),
    ("Bluetooth", "Long Range (BT5)", "今後", GRAY),
    ("WiFi", "Beacon", "対応 ◎ 主流", BLUE),
    ("WiFi", "NAN (Aware)", "対応（端末依存）", GREEN),
]
n = len(cards)
cw, gap, x0, ytop, ch = 1.95, 0.333, 0.6, 2.55, 2.0
for i, (name, sub, status, color) in enumerate(cards):
    x = x0 + i * (cw + gap)
    box = rounded(s, x, ytop, cw, ch, color, weight=1.6)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Pt(4); tf.margin_right = Pt(4)
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    set_run(p.add_run(), name, 13, BLACK, bold=True)
    p1 = tf.add_paragraph(); p1.alignment = PP_ALIGN.CENTER
    set_run(p1.add_run(), sub, 11, GRAY)
    p2 = tf.add_paragraph(); p2.alignment = PP_ALIGN.CENTER; p2.space_before = Pt(14)
    set_run(p2.add_run(), status, 12, color, bold=True)

center_label(s, 0.6, 4.78, 8.8, "▼", 12, GRAY)
band = rounded(s, 1.6, 5.15, 6.8, 0.7, BLUE, weight=1.4, fill=CODEBG)
tfb = band.text_frame
pb = tfb.paragraphs[0]; pb.alignment = PP_ALIGN.CENTER
set_run(pb.add_run(), "アプリが受信 → 同じ ZK 証明フローへ合流", 14, BLACK, bold=True)

tf = textbox(s, 0.65, 6.15, 8.8, 0.9)
bullet(tf, [("本アプリは ", False, False),
            ("BLE + WiFi(Beacon/NAN)", True, False), (" を受信", False, False)], 13)
bullet(tf, [("一般的傾向: ", False, False),
            ("Bluetooth ≒ Beacon ≫ NAN", True, False),
            ("（BLE+Beacon で大半をカバー）", False, False)], 12)

# ════════════════════════════════════════════════════
# 章 02 — 実装
# ════════════════════════════════════════════════════
divider("02", "実装", "ネイティブ + Dart で受信〜証明へ合流")

# やったこと（全体像）
s = add_slide()
header(s, "やったこと（全体像）", "サマリ")
tf = textbox(s, 0.65, 1.9, 8.8, 5.2)
bullet(tf, [("① Android ネイティブに ", False, False),
            ("WiFi スキャナを新規実装", True, False)], 16)
bullet(tf, [("WifiOdidScanner.kt", False, True),
            (" — ビーコンを走査し OpenDroneID IE を抽出", False, False)], 14, level=1)
bullet(tf, [("② ネイティブ → Flutter を ", False, False),
            ("EventChannel", True, False), (" でつなぐ", False, False)], 16, space_before=12)
bullet(tf, [("uav/wifi_odid", False, True),
            (" で {bssid, ssid, rssi, payload} をストリーム配信", False, False)], 14, level=1)
bullet(tf, [("③ Dart 側で受信し、", False, False),
            ("BLE と同じパース処理を再利用", True, False)], 16, space_before=12)
bullet(tf, [("extractFromWifiBeacon() を追加し、合流先 ", False, False),
            ("_applyDroneTelemetry", False, True), (" は変更なし", False, False)], 14, level=1)
bullet(tf, [("④ Manifest に WiFi 権限を追加 / README・ドキュメントを更新", False, False)],
       16, space_before=12)
bullet(tf, [("⑤ ", False, False), ("BLE と並行して常時自動受信", True, False),
            ("（UI 操作不要）", False, False)], 16, space_before=12)

# データの流れ
s = add_slide()
header(s, "データの流れ", "仕組み② フロー")
steps = [
    ("DJI ドローン", "WiFi Beacon を送信", False),
    ("Android WifiManager", "ビーコンをスキャン", False),
    ("WifiOdidScanner.kt", "ベンダ固有 IE を抽出 (Kotlin)", True),
    ("EventChannel", "message pack を Flutter へ", True),
    ("UavTelemetryPacket", "既存パーサで解析（再利用）", True),
    ("_applyDroneTelemetry", "ドローン位置として反映", False),
    ("ZK 証明フロー", "30m/5秒以内を証明（変更なし）", False),
]
top = 1.8
for i, (title, desc, hot) in enumerate(steps):
    box = s.shapes.add_shape(5, Inches(0.9), Inches(top), Inches(5.0), Inches(0.55))
    box.fill.solid(); box.fill.fore_color.rgb = WHITE
    box.line.color.rgb = BLUE if hot else LINE
    box.line.width = Pt(1.75 if hot else 1.0)
    box.shadow.inherit = False
    tfb = box.text_frame
    tfb.margin_top = Pt(2); tfb.margin_bottom = Pt(2)
    is_code = ("." in title) or title in ("EventChannel", "UavTelemetryPacket", "_applyDroneTelemetry")
    set_run(tfb.paragraphs[0].add_run(), title, 13, BLUE if hot else BLACK, bold=True, mono=is_code)
    tfd = textbox(s, 6.1, top + 0.03, 3.7, 0.5)
    set_run(tfd.paragraphs[0].add_run(), desc, 11.5, GRAY)
    if i < len(steps) - 1:
        ar = textbox(s, 1.45, top + 0.46, 1.0, 0.3)
        set_run(ar.paragraphs[0].add_run(), "▼", 10, BLUE if hot else GRAY)
    top += 0.74

# 実装詳細① ネイティブ
s = add_slide()
header(s, "実装詳細① ネイティブ (Kotlin)", "中身")
tf = textbox(s, 0.65, 1.8, 8.8, 1.9)
bullet(tf, [("WifiManager.startScan()", False, True),
            (" + ", False, False),
            ("SCAN_RESULTS_AVAILABLE", False, True),
            (" を受信", False, False)], 14)
bullet(tf, [("ScanResult.informationElements", False, True),
            (" から id=221 を走査", False, False)], 14)
bullet(tf, [("先頭が ", False, False), ("FA 0B BC 0D", False, True),
            (" の IE だけを抽出", False, False)], 14)
bullet(tf, [("OUI+type+counter の ", False, False), ("5バイトを除去", True, False),
            (" → message pack を EventChannel で配信", False, False)], 14)

codebox(s, 0.85, 4.0, 8.3, 2.05, [
    ("if (ie.id == 221 &&", False),
    ("    content.startsWith(0xFA,0x0B,0xBC,0x0D)) {", True),
    ("    val pack = content.copyOfRange(5, size) // 5B除去", True),
    ("    sink.success(mapOf(\"payload\" to pack, ...))", False),
    ("}", False),
])

tf = textbox(s, 0.65, 6.25, 8.8, 0.9)
bullet(tf, [("API 30 未満は IE 取得不可 → ", False, False),
            ("何も配信せず BLE のみで継続", True, False)], 13)

# 実装詳細② Dart
s = add_slide()
header(s, "実装詳細② Dart", "中身")
tf = textbox(s, 0.65, 1.8, 8.8, 1.7)
bullet(tf, [("EventChannel('uav/wifi_odid')", False, True),
            (" を購読（initState）", False, False)], 14)
bullet(tf, [("extractFromWifiBeacon()", False, True),
            (" を新規追加し IE を検証", False, False)], 14)
bullet(tf, [("解析は ", False, False),
            ("extractAllMessages / tryParseLocation を流用", True, False),
            ("（新規ロジック最小）", False, False)], 14)
bullet(tf, [("Location → ", False, False), ("_applyDroneTelemetry", False, True),
            (" に合流（BLE と完全共通）", False, False)], 14)

codebox(s, 0.85, 3.85, 8.3, 1.85, [
    ("final odid = UavTelemetryPacket", False),
    ("    .extractFromWifiBeacon(payload);", True),
    ("for (final msg in extractAllMessages(odid)) {", False),
    ("  final p = tryParseLocation(msg, seq);   // 再利用", True),
    ("  if (p != null) _applyDroneTelemetry(p); // 合流", False),
    ("}", False),
])

tf = textbox(s, 0.65, 5.95, 8.8, 1.1)
bullet(tf, [("BLE と並行して ", False, False), ("常時自動受信", True, False)], 13)
bullet(tf, [("ログは ", False, False), ("[WiFi ...]", False, True),
            (" で BLE と区別、RSSI/SSID も併記", False, False)], 13)

# 変更ファイル一覧
s = add_slide()
header(s, "変更ファイル一覧", "成果物")
rows = [
    ("WifiOdidScanner.kt", "新規", "WiFi スキャン + IE 抽出 + EventChannel 配信"),
    ("MainActivity.kt", "変更", "EventChannel を登録（配線）"),
    ("AndroidManifest.xml", "変更", "WiFi 権限を 3 つ追加"),
    ("lib/main.dart", "変更", "受信・パース・証明フローへ合流"),
    ("README.md ほか 3 件", "変更", "WiFi Beacon 対応を追記"),
]
top = 2.0
hdr = ["ファイル", "区分", "内容"]
xs = [0.7, 3.7, 4.7]
ws = [3.0, 1.0, 4.5]
for x, w, t in zip(xs, ws, hdr):
    tfb = textbox(s, x, top, w, 0.4)
    set_run(tfb.paragraphs[0].add_run(), t, 13, GRAY, bold=True)
top += 0.5
for name, kind, desc in rows:
    tfb = textbox(s, xs[0], top, ws[0], 0.5)
    set_run(tfb.paragraphs[0].add_run(), name, 13, BLACK, mono=True)
    tfb = textbox(s, xs[1], top, ws[1], 0.5)
    is_new = kind == "新規"
    set_run(tfb.paragraphs[0].add_run(), kind, 13, BLUE if is_new else BLACK, bold=is_new)
    tfb = textbox(s, xs[2], top, ws[2], 0.6)
    set_run(tfb.paragraphs[0].add_run(), desc, 12.5, BLACK)
    sep = s.shapes.add_shape(1, Inches(0.7), Inches(top + 0.52), Inches(8.5), Pt(0.75))
    sep.fill.solid(); sep.fill.fore_color.rgb = LINE
    sep.line.fill.background(); sep.shadow.inherit = False
    top += 0.78

tf = textbox(s, 0.65, top + 0.05, 8.8, 0.5)
bullet(tf, [("パース本体は ", False, False),
            ("既存資産を再利用したため追加コードは最小", True, False)], 13)

# 制約
s = add_slide()
header(s, "制約（プラットフォーム由来）", "注意点")
tf = textbox(s, 0.65, 1.9, 8.8, 5.2)
bullet(tf, [("Android 11 (API 30) 以上が必要", True, False)], 16)
bullet(tf, [("生 IE 取得 API ", False, False),
            ("getInformationElements()", False, True),
            (" が API 30 から", False, False)], 14, level=1)
bullet(tf, [("API 30 未満では ", False, False),
            ("自動的に無効化し BLE のみで動作", True, False),
            ("（クラッシュしない）", False, False)], 14, level=1)
bullet(tf, [("iOS は非対応", True, False),
            ("（WiFi ビーコン / IE を取得する公開 API が無い）", False, False)], 16, space_before=12)
bullet(tf, [("iOS は従来どおり BLE 受信のみで動作", False, False)], 14, level=1)
bullet(tf, [("追加権限（Android）", False, False)], 16, space_before=12)
bullet(tf, [("ACCESS_WIFI_STATE / CHANGE_WIFI_STATE / NEARBY_WIFI_DEVICES", False, True)],
       13, level=1)
bullet(tf, [("スキャン結果取得には既存の ", False, False),
            ("ACCESS_FINE_LOCATION", False, True), (" も必要", False, False)], 13, level=1)
bullet(tf, [("WiFi NAN も対応済み（", False, False),
            ("Wi-Fi Aware 対応端末のみ", True, False),
            ("・実機検証は今後）", False, False)], 16, space_before=12)

# ════════════════════════════════════════════════════
# 章 03 — 画面 (UI)
# ════════════════════════════════════════════════════
divider("03", "画面 (UI)", "受信経路の可視化 / WiFi Raw タブ")

# UI で見える化
s = add_slide()
header(s, "UI で見える化", "画面対応①")
tf = textbox(s, 0.65, 1.8, 8.8, 2.4)
pa(tf, "WiFi 受信を足したが、受信しても BLE / WiFi どちらの経路か画面で分からない",
   [("ドローンカードに ", False, False),
    ("受信経路バッジ（青=WiFi / 紫=BLE）", True, False), (" を表示", False, False)],
   space_before=2)
bullet(tf, [("未受信時は ", False, False),
            ("BLE / WiFi スキャン中…", False, True), ("、", False, False),
            ("捕捉後は ", False, False),
            ("BLE / WiFi 受信中…", False, True), (" に変化", False, False)], 13)
bullet(tf, [("上部ステップバー ", False, False), ("BLE", False, True),
            (" → ", False, False), ("BLE/WiFi", False, True),
            (" に変更", False, False)], 13)

codebox(s, 0.85, 4.35, 8.3, 1.55, [
    ("// 受信経路を記録して UI へ", False),
    ("_applyDroneTelemetry(packet, source: 'WiFi');", True),
    ("// → カードに  [WiFi]  バッジを点灯", False),
])

tf = textbox(s, 0.65, 6.1, 8.8, 0.9)
bullet(tf, [("状態変数 ", False, False),
            ("_lastDroneSource / _wifiOdidSeen", False, True),
            (" を追加", False, False)], 13)

# WiFi Raw スキャン画面（新タブ）
s = add_slide()
header(s, "WiFi Raw スキャン画面", "画面対応② 新タブ")
tf = textbox(s, 0.65, 1.8, 8.8, 5.3)
pa(tf, "どんな Remote ID が飛んでいるか生で確認する手段が WiFi に無い（BLE には BLE Raw がある）",
   [("「BLE Raw」の WiFi 版タブを新規追加", True, False),
    ("（5つ目のタブ）", False, False)], space_before=2)
bullet(tf, [("周辺の WiFi をリアルタイム一覧表示する診断画面", False, False)], 13)
bullet(tf, [("カードで確認できる項目", False, False)], 14, space_before=10)
bullet(tf, [("SSID / BSSID / RSSI / チャンネル / セキュリティ", False, False)], 13, level=1)
bullet(tf, [("Vendor IE (221) の ", False, False), ("hex dump", False, True),
            ("（長押しでコピー）", False, False)], 13, level=1)
bullet(tf, [("OpenDroneID は緑で強調", True, False),
            (" + 解析サマリー", False, False)], 14, space_before=12)
bullet(tf, [("FA 0B BC 0D", False, True),
            (" の IE を検出 → 緑枠 + ", False, False),
            ("「Remote ID」", False, False), (" タグ", False, False)], 13, level=1)
bullet(tf, [("BasicID / Location（緯度経度・高度）/ System を表示", False, False)], 13, level=1)
bullet(tf, [("用途: ", False, False),
            ("今どんな Remote ID が飛んでいるかを生で確認できる", True, False)],
       15, space_before=12)

# ════════════════════════════════════════════════════
# 章 04 — 受信の網羅と設計
# ════════════════════════════════════════════════════
divider("04", "受信の網羅と設計", "Beacon + NAN / スキャン1本化 / 重複防止")

# ネイティブのスキャン1本化
s = add_slide()
header(s, "ネイティブのスキャン1本化", "設計")
tf = textbox(s, 0.65, 1.8, 8.8, 1.8)
pa(tf, "証明用と診断用で WiFi を別々にスキャンすると、startScan の制限（2分に4回）で結果が減る",
   [("スキャンを ", False, False), ("WifiScanHub に1本化", True, False),
    ("し、2系統へ配信", False, False)], space_before=2)

cols = ["EventChannel", "用途", "配信内容"]
xs = [0.7, 3.5, 5.3]
ws = [2.8, 1.8, 4.0]
top = 3.7
for x, w, t in zip(xs, ws, cols):
    tfb = textbox(s, x, top, w, 0.4)
    set_run(tfb.paragraphs[0].add_run(), t, 13, GRAY, bold=True)
top += 0.5
rows = [
    ("uav/wifi_odid", "証明フロー", "message pack のみ"),
    ("uav/wifi_raw", "WiFi Raw タブ", "全ネットワーク + 全 IE"),
]
for ch, use, cont in rows:
    tfb = textbox(s, xs[0], top, ws[0], 0.5)
    set_run(tfb.paragraphs[0].add_run(), ch, 13, BLUE, mono=True, bold=True)
    tfb = textbox(s, xs[1], top, ws[1], 0.5)
    set_run(tfb.paragraphs[0].add_run(), use, 12.5, BLACK)
    tfb = textbox(s, xs[2], top, ws[2], 0.5)
    set_run(tfb.paragraphs[0].add_run(), cont, 12.5, BLACK)
    sep = s.shapes.add_shape(1, Inches(0.7), Inches(top + 0.5), Inches(8.6), Pt(0.75))
    sep.fill.solid(); sep.fill.fore_color.rgb = LINE
    sep.line.fill.background(); sep.shadow.inherit = False
    top += 0.72

tf = textbox(s, 0.65, top + 0.1, 8.8, 1.0)
bullet(tf, [("両画面が ", False, False), ("同じスキャン結果を共有", True, False),
            ("（二重スキャンを回避）", False, False)], 14)
bullet(tf, [("最初の購読で開始 / 最後の解除で停止", False, False)], 13)

# DJI を取りこぼさない（Beacon + NAN）
s = add_slide()
header(s, "DJI を取りこぼさない", "受信② 方式の網羅")
tf = textbox(s, 0.65, 1.8, 8.8, 1.9)
pa(tf, "DJI は機種・地域で WiFi の送信方式が違い、Beacon だけだと取りこぼす恐れ",
   [("WiFi NAN（Wi-Fi Aware）受信も追加", True, False),
    ("し、Beacon と同じ証明フローへ合流", False, False)], space_before=2)

cols = ["WiFi の方式", "普及度", "対応条件"]
xs = [0.7, 3.7, 5.6]
ws = [3.0, 1.9, 3.7]
top = 3.65
for x, w, t in zip(xs, ws, cols):
    tfb = textbox(s, x, top, w, 0.4)
    set_run(tfb.paragraphs[0].add_run(), t, 13, GRAY, bold=True)
top += 0.5
rows = [
    ("WiFi Beacon", "◎ 主流（DJI の大半）", "Android 11+"),
    ("WiFi NAN", "△ 少数（保険）", "Wi-Fi Aware 対応端末"),
]
for name, pop, cond in rows:
    is_beacon = name == "WiFi Beacon"
    tfb = textbox(s, xs[0], top, ws[0], 0.5)
    set_run(tfb.paragraphs[0].add_run(), name, 13, BLUE if is_beacon else BLACK,
            bold=is_beacon)
    tfb = textbox(s, xs[1], top, ws[1], 0.5)
    set_run(tfb.paragraphs[0].add_run(), pop, 12.5, BLACK)
    tfb = textbox(s, xs[2], top, ws[2], 0.5)
    set_run(tfb.paragraphs[0].add_run(), cond, 12.5, BLACK)
    sep = s.shapes.add_shape(1, Inches(0.7), Inches(top + 0.5), Inches(8.6), Pt(0.75))
    sep.fill.solid(); sep.fill.fore_color.rgb = LINE
    sep.line.fill.background(); sep.shadow.inherit = False
    top += 0.72

tf = textbox(s, 0.65, top + 0.15, 8.8, 1.1)
bullet(tf, [("一般的な傾向: ", False, False),
            ("Bluetooth ≒ Beacon ≫ NAN", True, False)], 14)
bullet(tf, [("BLE + WiFi Beacon で DJI の大半をカバー、NAN は保険", False, False)], 13)

# Beacon 優先・NAN 抑止（判定の図解）
s = add_slide()
header(s, "Beacon 優先・NAN 抑止", "受信③ 重複防止")
tf = textbox(s, 0.65, 1.78, 8.8, 1.4)
pa(tf, "Beacon と NAN を両方受けると、同じドローンを二重に検知・登録してしまう",
   [("Beacon で受信できている間（15秒）は NAN を処理しない", True, False)],
   space_before=2)

# 判定フロー図
cond = rounded(s, 2.8, 3.35, 4.4, 0.7, BLUE, weight=1.6, fill=CODEBG)
ctf = cond.text_frame
cp = ctf.paragraphs[0]; cp.alignment = PP_ALIGN.CENTER
set_run(cp.add_run(), "直近15秒に Beacon を受信した？", 13, BLACK, bold=True)

# 分岐ラベル
center_label(s, 0.8, 4.25, 3.6, "YES ▼", 11, BLUE)
center_label(s, 5.6, 4.25, 3.6, "NO ▼", 11, GRAY)

yes_box = rounded(s, 0.8, 4.7, 3.6, 0.85, GRAY, weight=1.3)
ytf = yes_box.text_frame; ytf.word_wrap = True
yp = ytf.paragraphs[0]; yp.alignment = PP_ALIGN.CENTER
set_run(yp.add_run(), "NAN は処理しない", 13, BLACK, bold=True)
yp2 = ytf.add_paragraph(); yp2.alignment = PP_ALIGN.CENTER
set_run(yp2.add_run(), "（重複検知を防止）", 11, GRAY)

no_box = rounded(s, 5.6, 4.7, 3.6, 0.85, BLUE, weight=1.4)
ntf = no_box.text_frame; ntf.word_wrap = True
np = ntf.paragraphs[0]; np.alignment = PP_ALIGN.CENTER
set_run(np.add_run(), "NAN を採用", 13, BLUE, bold=True)
np2 = ntf.add_paragraph(); np2.alignment = PP_ALIGN.CENTER
set_run(np2.add_run(), "（保険として受信）", 11, GRAY)

tf = textbox(s, 0.65, 5.85, 8.8, 1.2)
bullet(tf, [("NAN は ", False, False),
            ("Beacon が来ないときだけのフォールバック", True, False)], 13)
bullet(tf, [("抑止は WiFi 内（Beacon↔NAN）のみ。", False, False),
            ("BLE は別経路で常に残す", False, False)], 12)

# ════════════════════════════════════════════════════
# 章 05 — 評価と考察
# ════════════════════════════════════════════════════
divider("05", "評価と考察", "BLE 比較 / セキュリティ / 今後")

# BLE と WiFi の比較
s = add_slide()
header(s, "BLE と WiFi Beacon の比較", "整理")
cols = ["項目", "BLE (従来)", "WiFi Beacon (今回)"]
xs = [0.7, 3.3, 6.3]
ws = [2.5, 3.0, 3.3]
for x, w, t in zip(xs, ws, cols):
    tfb = textbox(s, x, 1.95, w, 0.4)
    blue = t.startswith("WiFi")
    set_run(tfb.paragraphs[0].add_run(), t, 13, BLUE if blue else GRAY, bold=True)
rows = [
    ("主な対応機", "Parrot/Autel 等\n自作 Pi 送信機", "DJI など市販主流機"),
    ("搬送方式", "Service/Manufacturer\nData アドバタイズ", "ビーコンの\nベンダ固有 IE"),
    ("対応 OS", "Android / iOS 両方", "Android 11+ のみ\n(iOS 不可)"),
    ("実装", "flutter_blue_plus", "ネイティブ Kotlin\n+ EventChannel"),
    ("メッセージ解析", "UavTelemetryPacket", "同左（完全に再利用）"),
]
top = 2.45
for item, ble, wifi in rows:
    tfb = textbox(s, xs[0], top, ws[0], 0.7)
    set_run(tfb.paragraphs[0].add_run(), item, 12.5, BLACK, bold=True)
    for j, (val, x, w) in enumerate([(ble, xs[1], ws[1]), (wifi, xs[2], ws[2])]):
        tfb = textbox(s, x, top, w, 0.8)
        for k, line in enumerate(val.split("\n")):
            pp = tfb.paragraphs[0] if k == 0 else tfb.add_paragraph()
            pp.space_after = Pt(0)
            is_mono = any(c in line for c in ("_", "flutter_blue", "EventChannel"))
            set_run(pp.add_run(), line, 12, BLUE if (j == 1 and ("再利用" in line)) else BLACK,
                    mono=is_mono)
    sep = s.shapes.add_shape(1, Inches(0.7), Inches(top + 0.82), Inches(8.9), Pt(0.75))
    sep.fill.solid(); sep.fill.fore_color.rgb = LINE
    sep.line.fill.background(); sep.shadow.inherit = False
    top += 0.95

# セキュリティ / なりすまし考察
s = add_slide()
header(s, "セキュリティ / なりすまし考察", "考察")
tf = textbox(s, 0.65, 1.9, 8.8, 5.3)
bullet(tf, [("Remote ID は ", False, False), ("平文ブロードキャスト", True, False),
            ("（BLE も WiFi も同じ）", False, False)], 15)
bullet(tf, [("第三者が偽の位置を ", False, False),
            ("なりすまし送信", True, False), (" できる余地がある", False, False)], 15, level=1)
bullet(tf, [("本プロジェクトの位置づけ", False, False)], 15, space_before=12)
bullet(tf, [("ZK 証明は「受信した値が ", False, False),
            ("30m/5秒以内である", False, False),
            ("」ことを示すもの", False, False)], 13, level=1)
bullet(tf, [("送信元の真正性そのものは別レイヤの課題", False, False)], 13, level=1)
bullet(tf, [("緩和策（既存 / 今後）", False, False)], 15, space_before=12)
bullet(tf, [("OpenDroneID ", False, False), ("Authentication メッセージ", True, False),
            (" による署名検証", False, False)], 13, level=1)
bullet(tf, [("カメラ + YOLO 検知", False, False),
            (" との突合で物理的な存在を裏付け", False, False)], 13, level=1)
bullet(tf, [("RSSI / 複数受信での整合性チェック", False, False)], 13, level=1)
bullet(tf, [("→ ", False, False),
            ("「電波の受信」と「映像の検知」の二重確認が強み", True, False)], 15, space_before=12)

# 今後の拡張
s = add_slide()
header(s, "今後の拡張", "ロードマップ")
tf = textbox(s, 0.65, 1.95, 8.8, 5.2)
bullet(tf, [("WiFi NAN の実機検証", True, False), ("（実装は完了）", False, False)], 16)
bullet(tf, [("Wi-Fi Aware 対応端末 + NAN 送信機での受信確認", False, False)], 13, level=1)
bullet(tf, [("NAN の Service Specific Info フレーミングの最終調整", False, False)],
       13, level=1)
bullet(tf, [("Authentication メッセージ検証", True, False)], 16, space_before=12)
bullet(tf, [("type=2 Auth を解析し ", False, False),
            ("機体署名を検証", False, False), ("（なりすまし対策）", False, False)], 13, level=1)
bullet(tf, [("BT5 Long Range 受信", True, False)], 16, space_before=12)
bullet(tf, [("Extended Advertising でより遠距離の受信", False, False)], 13, level=1)
bullet(tf, [("BLE Raw Scan 画面への WiFi 統合表示", True, False)], 16, space_before=12)
bullet(tf, [("domain/uav_telemetry.dart", False, True),
            (" へ同ヘルパーを展開し一覧表示", False, False)], 13, level=1)
bullet(tf, [("iOS 代替", True, False)], 16, space_before=12)
bullet(tf, [("外部受信機(ESP32 等)→BLE ブリッジで WiFi を中継", False, False)], 13, level=1)

# ════════════════════════════════════════════════════
# 章 06 — 品質と検証
# ════════════════════════════════════════════════════
divider("06", "品質と検証", "見つかった課題と対応 / テスト・ビルド")

# 見つかった課題と対応
s = add_slide()
header(s, "見つかった課題と対応", "品質")
tf = textbox(s, 0.65, 1.8, 8.8, 5.4)
pa(tf, "WiFi Raw に、もう消えたネットワークがいつまでも残る",
   [("30秒見えなければ自動で除去", True, False),
    ("・最大60件にキャップした", False, False)], space_before=2)
pa(tf, "実機ドローンが無いと受信処理が正しいか確認できない",
   [("合成サンプルでユニットテストを追加", True, False),
    ("（6件パス・実機不要）", False, False)])
pa(tf, "Android 13+ は WiFi 権限が別建てで、要求していなかった",
   [("起動時に ", False, False), ("NEARBY_WIFI_DEVICES を要求", True, False),
    ("するようにした", False, False)])
pa(tf, "端末の位置情報が OFF だと WiFi が無言で空になり原因不明",
   [("画面に警告と", False, False),
    ("「位置情報設定を開く」ボタンを表示", True, False)])

p = tf.add_paragraph()
p.space_before = Pt(16)
set_run(p.add_run(), "未対応（影響小）: ", 12.5, GRAY, bold=True)
set_run(p.add_run(), "startScan 間隔の緩和 / iOS でタブ非表示 / パーサ重複の統合",
        12.5, GRAY)

# 検証と残タスク
s = add_slide()
header(s, "検証と残タスク", "状況")
tf = textbox(s, 0.65, 1.85, 8.8, 5.3)
section(tf, "■ 確認済み", space_before=0)
bullet(tf, [("flutter analyze", False, True),
            (" — 変更由来のエラー・警告なし", False, False)], 14)
bullet(tf, [("flutter build apk --debug", False, True),
            (" → ", False, False), ("ビルド成功", True, False),
            ("（Kotlin・Dart 両方コンパイル）", False, False)], 14)
bullet(tf, [("flutter test", False, True),
            (" — WiFi パーサ ", False, False), ("6件すべてパス", True, False)], 14)
bullet(tf, [("受信 / UI バッジ / WiFi Raw タブ / 改善対応まで実装・ビルド済み",
            False, False)], 14)

section(tf, "■ 残り（実機での受信確認）")
bullet(tf, [("Android 11+ 実機で ", False, False), ("flutter run", False, True)], 14)
bullet(tf, [("DJI 実機 / OpenDroneID 送信で ", False, False),
            ("[WiFi/Beacon Location] lat=…", False, True),
            (" を確認", False, False)], 14)
bullet(tf, [("NAN は ", False, False),
            ("Wi-Fi Aware 対応端末で [WiFi/NAN …] を確認", True, False),
            ("（実装済み・未検証）", False, False)], 14)
bullet(tf, [("受信データで ZK 証明が生成・検証できること", False, False)], 14)

p = tf.add_paragraph()
p.space_before = Pt(18)
set_run(p.add_run(), "成果: ", 16, BLACK, bold=True)
set_run(p.add_run(), "DJI 等の WiFi（Beacon＋NAN）ドローンを検知・証明できるようになった",
        16, BLUE, bold=True)

# ════════════════════════════════════════════════════
# ページ番号（タイトルを除く全スライド右下）
# ════════════════════════════════════════════════════
for i, slide in enumerate(prs.slides):
    if i == 0:
        continue
    tb = slide.shapes.add_textbox(Inches(9.05), Inches(7.02), Inches(0.75), Inches(0.32))
    p = tb.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.RIGHT
    set_run(p.add_run(), str(i + 1), 9, GRAY)

out = "wifi_beacon_changes.pptx"
prs.save(out)
print("saved:", out, "slides:", len(prs.slides._sldIdLst))
