"""OpenDroneID 規格 + 実装 詳細スライド（32枚・情報分散版）

使い方:
  python3 scripts/generate_opendroneid_slides.py
"""

from pathlib import Path
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

OUTPUT_PATH = Path("opendroneid_spec_and_impl.pptx")

W     = Inches(10)
H     = Inches(7.5)
M     = Inches(0.48)
IW    = W - M * 2
TOTAL = 35

C_BG    = RGBColor(0xFF, 0xFF, 0xFF)
C_BLACK = RGBColor(0x00, 0x00, 0x00)
C_TEXT  = RGBColor(0x1A, 0x1A, 0x1A)
C_SUB   = RGBColor(0x55, 0x55, 0x55)
C_RULE  = RGBColor(0xCC, 0xCC, 0xCC)
C_LIGHT = RGBColor(0xF0, 0xF0, 0xF0)
C_BOX   = RGBColor(0xF7, 0xF7, 0xF7)
C_TH    = RGBColor(0x11, 0x11, 0x11)
C_THFG  = RGBColor(0xFF, 0xFF, 0xFF)
C_TR1   = RGBColor(0xFF, 0xFF, 0xFF)
C_TR2   = RGBColor(0xF2, 0xF2, 0xF2)

FONT = "Hiragino Sans"
MONO = "Courier New"


# ── ヘルパー ──────────────────────────────────────────────────────────────────

def set_bg(s):
    bg = s.background; bg.fill.solid(); bg.fill.fore_color.rgb = C_BG

def rect(s, l, t, w, h, c, border=False, bc=None):
    sh = s.shapes.add_shape(1, l, t, w, h)
    sh.fill.solid(); sh.fill.fore_color.rgb = c
    if border:
        sh.line.width = Pt(0.75)
        sh.line.color.rgb = bc or C_RULE
    else:
        sh.line.fill.background()
    return sh

def txb(s, text, l, t, w, h, size=12, bold=False, color=C_TEXT,
        align=PP_ALIGN.LEFT, italic=False, mono=False):
    b = s.shapes.add_textbox(l, t, w, h)
    tf = b.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; p.alignment = align
    r = p.add_run(); r.text = text
    r.font.size = Pt(size); r.font.bold = bold; r.font.italic = italic
    r.font.color.rgb = color; r.font.name = MONO if mono else FONT
    return b

def mline(s, lines, l, t, w, h, size=12, color=C_TEXT, gap=5, mono=False, bold_idx=None):
    b = s.shapes.add_textbox(l, t, w, h)
    tf = b.text_frame; tf.word_wrap = True
    first = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        r = p.add_run(); r.text = line
        r.font.size = Pt(size); r.font.color.rgb = color
        r.font.name = MONO if mono else FONT
        r.font.bold = (bold_idx is not None and i in bold_idx)
        p.space_after = Pt(gap)

def code(s, lines, l, t, w, h, size=9):
    rect(s, l, t, w, h, C_BOX, border=True)
    mline(s, lines, l+Inches(0.12), t+Inches(0.09),
          w-Inches(0.24), h-Inches(0.18), size=size, color=C_TEXT, gap=2, mono=True)

def tbl(s, headers, rows, l, t, w, cw=None, fs=10, rh=0.40):
    nr = len(rows)+1; nc = len(headers)
    tb = s.shapes.add_table(nr, nc, l, t, w, Inches(rh)*nr).table
    if cw:
        for i, v in enumerate(cw): tb.columns[i].width = v
    else:
        for col in tb.columns: col.width = w // nc
    def cs(cell, text, hd=False, ev=False):
        cell.fill.solid()
        cell.fill.fore_color.rgb = C_TH if hd else (C_TR2 if ev else C_TR1)
        tf = cell.text_frame; tf.word_wrap = True
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.LEFT
        r = p.add_run(); r.text = text
        r.font.size = Pt(fs); r.font.bold = hd
        r.font.color.rgb = C_THFG if hd else C_TEXT; r.font.name = FONT
    for ci, h in enumerate(headers): cs(tb.cell(0, ci), h, hd=True)
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row): cs(tb.cell(ri+1, ci), val, ev=(ri%2==1))

def hdr(s, title, sub=None, part=None):
    set_bg(s)
    rect(s, 0, 0, W, Inches(0.08), C_BLACK)
    rect(s, 0, Inches(0.08), Inches(0.06), H-Inches(0.08), C_BLACK)
    if part:
        txb(s, part, M, Inches(0.10), IW, Inches(0.25), size=10, color=C_SUB)
        txb(s, title, M, Inches(0.33), IW, Inches(0.55), size=21, bold=True, color=C_BLACK)
    else:
        txb(s, title, M, Inches(0.13), IW, Inches(0.55), size=22, bold=True, color=C_BLACK)
    if sub:
        txb(s, sub, M, Inches(0.70), IW, Inches(0.28), size=11, color=C_SUB)
    rect(s, M, Inches(1.05), IW, Pt(1), C_RULE)

def sec(s, text, l, t, w=None, size=13):
    if w is None: w = IW - (l - M)
    txb(s, text, l, t, w, Inches(0.35), size=size, bold=True, color=C_BLACK)
    rect(s, l, t+Inches(0.35), w, Pt(1), C_RULE)

def pnum(s, n):
    txb(s, f"{n} / {TOTAL}", W-Inches(0.75), H-Inches(0.30),
        Inches(0.65), Inches(0.25), size=9, color=C_SUB, align=PP_ALIGN.RIGHT)

def bignum(s, number, label, l, t, w, h):
    """大きな数字とラベルを表示するカード"""
    rect(s, l, t, w, h, C_LIGHT, border=True)
    txb(s, number, l, t+Inches(0.15), w, h*0.55,
        size=42, bold=True, color=C_BLACK, align=PP_ALIGN.CENTER)
    txb(s, label, l, t+h*0.65, w, h*0.35,
        size=11, color=C_SUB, align=PP_ALIGN.CENTER)

def step_box(s, num, title, body, l, t, w, h):
    rect(s, l, t, w, h, C_LIGHT, border=True)
    rect(s, l, t, w, Inches(0.38), C_BLACK)
    txb(s, f"  {num}  {title}", l+Inches(0.08), t+Inches(0.04),
        w-Inches(0.12), Inches(0.30), size=12, bold=True, color=C_BG)
    txb(s, body, l+Inches(0.12), t+Inches(0.45),
        w-Inches(0.24), h-Inches(0.55), size=11, color=C_TEXT)

def part_divider(s, part_num, part_title, subtitle):
    """章区切りスライド"""
    set_bg(s)
    rect(s, 0, 0, W, H, C_BLACK)
    txb(s, f"Part {part_num}", M, Inches(2.2), IW, Inches(0.6),
        size=16, color=RGBColor(0xAA, 0xAA, 0xAA), align=PP_ALIGN.CENTER)
    txb(s, part_title, M, Inches(2.9), IW, Inches(1.1),
        size=36, bold=True, color=C_BG, align=PP_ALIGN.CENTER)
    txb(s, subtitle, M, Inches(4.1), IW, Inches(0.5),
        size=14, color=RGBColor(0xBB, 0xBB, 0xBB), align=PP_ALIGN.CENTER)


# =============================================================================
def build():
    prs = Presentation()
    prs.slide_width = W; prs.slide_height = H
    blank = prs.slide_layouts[6]

    # =========================================================================
    # 1. 表紙
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    set_bg(sl)
    rect(sl, 0, 0, W, Inches(0.14), C_BLACK)
    rect(sl, 0, H-Inches(0.14), W, Inches(0.14), C_BLACK)
    txb(sl, "OpenDroneID", M, Inches(0.9), IW, Inches(1.1),
        size=44, bold=True, color=C_BLACK, align=PP_ALIGN.CENTER)
    txb(sl, "ASTM F3411-22a 規格の詳細と\nドローン / Flutter アプリ 両面実装の解説",
        M, Inches(2.15), IW, Inches(0.85), size=18, color=C_SUB, align=PP_ALIGN.CENTER)
    rect(sl, Inches(1.0), Inches(3.20), Inches(8.0), Pt(1.5), C_BLACK)
    mline(sl, [
        "送信側:   Raspberry Pi  +  Python  (uav/remote_id.py)",
        "受信側:   Flutter Android アプリ  (rapidsnark_app/lib/main.dart)",
        "準拠仕様: opendroneid-core-c  /  ASTM F3411-22a",
    ], Inches(2.0), Inches(3.40), Inches(6.0), Inches(1.5), size=13, color=C_TEXT, gap=8)
    txb(sl, "35 スライド構成", M, H-Inches(0.42), IW, Inches(0.28),
        size=10, color=C_SUB, align=PP_ALIGN.CENTER)
    pnum(sl, 1)

    # =========================================================================
    # PART 1: 規格の背景
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    part_divider(sl, 1, "規格の背景と概要", "なぜ OpenDroneID が必要なのか")
    pnum(sl, 2)

    # =========================================================================
    # 3. なぜリモートIDが必要か
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "なぜリモートIDが必要か", "ドローンは「見えない車」だった", part="Part 1 — 規格の背景")
    pnum(sl, 3)

    txb(sl,
        "道路を走る車にはナンバープレートがある。\n"
        "しかし飛行中のドローンには、地上から「どの機体か」を識別する手段がなかった。",
        M, Inches(1.18), IW, Inches(0.80), size=14, color=C_TEXT)

    problems = [
        ("問題 1", "不審ドローンへの対処が困難",
         "空港や重要施設の上空に出現しても、\n機体の所有者・目的を即座に確認できない"),
        ("問題 2", "事故発生時の責任追跡が困難",
         "墜落事故があっても「どの機体か」を\n後から特定するすべがない"),
        ("問題 3", "飛行許可の実効性がない",
         "許可証なしで飛行しても、地上からリアルタイムで\n発見・照合する仕組みがなかった"),
    ]
    for i, (tag, title, body) in enumerate(problems):
        x = M + Inches(3.00) * i
        rect(sl, x, Inches(2.18), Inches(2.85), Inches(3.00), C_LIGHT, border=True)
        txb(sl, tag,   x+Inches(0.12), Inches(2.25), Inches(2.60), Inches(0.28),
            size=10, color=C_SUB)
        txb(sl, title, x+Inches(0.12), Inches(2.55), Inches(2.60), Inches(0.40),
            size=13, bold=True, color=C_BLACK)
        txb(sl, body,  x+Inches(0.12), Inches(3.00), Inches(2.60), Inches(1.10),
            size=12, color=C_TEXT)

    txb(sl, "解決策 →", M, Inches(5.42), Inches(1.20), Inches(0.45),
        size=13, bold=True, color=C_BLACK)
    rect(sl, M+Inches(1.25), Inches(5.42), IW-Inches(1.25), Inches(1.55), C_BOX, border=True)
    txb(sl,
        "飛行中のドローンが BLE（Bluetooth Low Energy）や Wi-Fi で\n"
        "自分の ID・位置・速度をリアルタイムにブロードキャストする\n"
        "→ それが OpenDroneID（リモートID）",
        M+Inches(1.40), Inches(5.55), IW-Inches(1.50), Inches(1.25),
        size=13, color=C_TEXT)

    # =========================================================================
    # 4. OpenDroneID とは
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "OpenDroneID とは", "国際標準の「ドローン電子ナンバープレート」", part="Part 1 — 規格の背景")
    pnum(sl, 4)

    txb(sl,
        "ASTM International（米国材料試験協会）が制定した規格。\n"
        "ドローンが飛行中に BLE または Wi-Fi で自身の情報をブロードキャストする方式を標準化している。",
        M, Inches(1.18), IW, Inches(0.80), size=14, color=C_TEXT)

    tbl(sl,
        ["規格名", "制定機関", "対応バージョン", "備考"],
        [
            ["ASTM F3411-19",   "ASTM International", "v1.0",
             "初版。BLE Legacy Advertising のみ"],
            ["ASTM F3411-22a",  "ASTM International", "v2（本実装）",
             "BLE / Wi-Fi NaN 対応。プロトコルバージョン = 2"],
            ["ASD-STAN prEN 4709-002", "欧州 ASD-STAN", "欧州版",
             "ASTM と相互運用性あり。ペイロード互換"],
            ["ANSI/CTA-2063-A", "CTA",               "シリアル番号規格",
             "UAS_ID のフォーマットを規定"],
        ],
        M, Inches(2.10), IW,
        cw=[Inches(2.2), Inches(2.2), Inches(1.5), Inches(3.0)], fs=11)

    txb(sl, "本プロジェクトが準拠するバージョン",
        M, Inches(4.12), IW, Inches(0.35), size=13, bold=True, color=C_BLACK)
    rect(sl, M, Inches(4.50), IW, Inches(1.20), C_BOX, border=True)
    mline(sl, [
        "・ASTM F3411-22a（プロトコルバージョン = 2）",
        "・参照実装: opendroneid-core-c（GitHub: opendroneid/opendroneid-core-c）",
        "・BLE 伝送方式: Legacy Advertising（ADV_NONCONN_IND）",
        "・実装メッセージ: BasicID + Location の 2 種類",
    ], M+Inches(0.15), Inches(4.60), IW-Inches(0.3), Inches(1.00),
        size=12, color=C_TEXT, gap=4)

    # =========================================================================
    # 5. 日本での義務化
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "日本での義務化", "2022年6月 航空法改正でリモートID搭載が義務に", part="Part 1 — 規格の背景")
    pnum(sl, 5)

    txb(sl, "2022年6月20日施行", M, Inches(1.18), IW, Inches(0.45),
        size=22, bold=True, color=C_BLACK)
    txb(sl,
        "改正航空法により、登録が必要な無人航空機（100 g 以上）への\nリモートID 機器の搭載が義務化された。",
        M, Inches(1.68), IW, Inches(0.72), size=14, color=C_TEXT)

    tbl(sl,
        ["項目", "内容"],
        [
            ["対象機体",   "機体登録が必要な無人航空機（最大離陸重量 100 g 以上）"],
            ["送信情報",   "機体登録番号・製造番号・位置・速度・高度・方向など"],
            ["送信方式",   "無線（BLE または Wi-Fi）によるリアルタイム放送"],
            ["送信頻度",   "1 秒に 1 回以上（本実装は 1 秒ごと）"],
            ["例外",       "屋内飛行・係留飛行・特定の認証機体など"],
        ],
        M, Inches(2.62), Inches(8.5), cw=[Inches(1.8), Inches(6.7)], fs=12)

    rect(sl, M, Inches(5.45), IW, Inches(1.60), C_BOX, border=True)
    txb(sl, "このプロジェクトにとっての意味",
        M+Inches(0.15), Inches(5.52), IW-Inches(0.3), Inches(0.35),
        size=13, bold=True, color=C_BLACK)
    mline(sl, [
        "・独自フォーマットでなく ASTM F3411-22a 準拠にすることで「法令準拠の送信装置」として機能する",
        "・DJI 等の市販機が送る BLE パケットと同じ形式 → 既存の受信アプリ・規制当局の検査機と互換",
        "・ZK 証明の信頼性向上：「規格準拠のテレメトリ」を入力にすることで証拠の正当性が増す",
    ], M+Inches(0.15), Inches(5.92), IW-Inches(0.3), Inches(1.02),
        size=12, color=C_TEXT, gap=4)

    # =========================================================================
    # 6. 6 種類のメッセージ
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "規格が定める 6 種類のメッセージ", "各メッセージが担う役割の分担", part="Part 1 — 規格の背景")
    pnum(sl, 6)

    tbl(sl,
        ["#", "メッセージ種別", "MessageType", "送信義務", "主な内容"],
        [
            ["1", "BasicID",      "0x0", "任意（推奨）",    "機体識別子（UAS_ID）・機体種別（マルチローター等）"],
            ["2", "Location",     "0x1", "必須・1秒以上",   "緯度・経度・高度・速度・方向・タイムスタンプ"],
            ["3", "Authentication","0x2","任意",            "機体の真正性を証明する署名データ（複数パケット可）"],
            ["4", "SelfID",       "0x3", "任意",            "飛行目的の説明文（例:「商業撮影」）"],
            ["5", "System",       "0x4", "任意（推奨）",    "オペレーター位置・運用エリア・UA 数量"],
            ["6", "OperatorID",   "0x5", "任意",            "オペレーター登録番号・登録機関"],
            ["—", "MessagePack",  "0xF", "拡張",            "複数メッセージを 1 BLE パケットに束ねる拡張形式"],
        ],
        M, Inches(1.12), IW,
        cw=[Inches(0.4), Inches(1.85), Inches(1.4), Inches(1.55), Inches(3.7)], fs=11)

    txb(sl, "本プロジェクトで実装したメッセージ",
        M, Inches(5.05), IW, Inches(0.35), size=13, bold=True, color=C_BLACK)
    rect(sl, M, Inches(5.45), Inches(4.5), Inches(1.55), C_LIGHT, border=True)
    txb(sl, "BasicID (0x0)",
        M+Inches(0.12), Inches(5.52), Inches(4.26), Inches(0.35),
        size=13, bold=True, color=C_BLACK)
    txb(sl, "機体の「名前と種別」。UAS_ID 文字列と\nマルチローター識別を送信する。",
        M+Inches(0.12), Inches(5.90), Inches(4.26), Inches(0.88),
        size=12, color=C_TEXT)

    rect(sl, Inches(5.10), Inches(5.45), Inches(4.5), Inches(1.55), C_LIGHT, border=True)
    txb(sl, "Location (0x1)  ← 送信義務あり",
        Inches(5.22), Inches(5.52), Inches(4.26), Inches(0.35),
        size=13, bold=True, color=C_BLACK)
    txb(sl, "位置・高度・速度・タイムスタンプ。\n1 秒に 1 回以上の送信が法的に必要。",
        Inches(5.22), Inches(5.90), Inches(4.26), Inches(0.88),
        size=12, color=C_TEXT)

    # =========================================================================
    # PART 2: BLE 通信の仕組み
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    part_divider(sl, 2, "BLE 通信の仕組み", "31 バイトの制約の中に情報を詰め込む")
    pnum(sl, 7)

    # =========================================================================
    # 8. BLE Advertising の基本
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "BLE Advertising の基本", "「呼びかけ」パケットを繰り返し発信するしくみ", part="Part 2 — BLE 通信の仕組み")
    pnum(sl, 8)

    txb(sl,
        "BLE（Bluetooth Low Energy）には「接続」と「広告（Advertising）」の 2 つのモードがある。\n"
        "OpenDroneID は接続なし広告（ADV_NONCONN_IND）を使う。",
        M, Inches(1.18), IW, Inches(0.80), size=14, color=C_TEXT)

    tbl(sl,
        ["BLE モード", "特徴", "OpenDroneID での採用"],
        [
            ["ADV_IND（接続可）",
             "接続要求を受け付ける\nペアリングが発生する可能性",
             "✗ 不要な接続試みが発生する"],
            ["ADV_NONCONN_IND（接続不可）",
             "接続要求を無視する\nスキャンするだけで受信できる",
             "✔ 採用。受信側はスキャンのみでOK"],
            ["SCAN_IND（スキャン応答あり）",
             "スキャン要求に追加データを返す",
             "✗ 不要な往復が発生する"],
        ],
        M, Inches(2.12), IW, cw=[Inches(2.2), Inches(3.5), Inches(3.2)], fs=12)

    txb(sl, "BLE Advertising パケットの制約",
        M, Inches(4.18), IW, Inches(0.35), size=13, bold=True, color=C_BLACK)
    rect(sl, M, Inches(4.55), IW, Inches(2.45), C_BOX, border=True)
    mline(sl, [
        "最大ペイロード: 31 バイト（BLE 4.x Legacy Advertising の制限）",
        "",
        "このうち OpenDroneID は 29 バイトを使用:",
        "  1 byte  : AD 要素の長さ（length = 28）",
        "  1 byte  : AD タイプ（0x16 = Service Data – 16-bit UUID）",
        "  2 bytes : Service UUID（0xFFFA、リトルエンディアン）",
        " 25 bytes : ODID メッセージ本体",
        "  2 bytes : ゼロパディング（31 バイト枠を埋める）",
    ], M+Inches(0.15), Inches(4.65), IW-Inches(0.3), Inches(2.22),
        size=12, color=C_TEXT, gap=3)

    # =========================================================================
    # 9. AD 要素の構造（図解）
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "BLE ペイロードの構造（図解）", "29 バイトが 31 バイト枠にどう収まるか", part="Part 2 — BLE 通信の仕組み")
    pnum(sl, 9)

    # バイト図解（大きめ）
    fields = [
        (Inches(0.70), "total_len\n= 29\n(0x1D)\n1 byte"),
        (Inches(0.70), "length\n= 28\n(0x1C)\n1 byte"),
        (Inches(0.70), "AD type\n0x16\n1 byte"),
        (Inches(1.00), "UUID\n0xFFFA\n(LE: FA FF)\n2 bytes"),
        (Inches(5.20), "25 バイト  ODID メッセージ本体\n（BasicID または Location）"),
        (Inches(0.70), "padding\n0x00 × 2\n2 bytes"),
    ]
    x = M; y = Inches(1.18)
    for w, label in fields:
        bg = C_LIGHT if label.startswith("25") else C_BOX
        rect(sl, x, y, w, Inches(1.50), bg, border=True)
        txb(sl, label, x+Inches(0.05), y+Inches(0.08),
            w-Inches(0.10), Inches(1.35), size=10, color=C_TEXT, align=PP_ALIGN.CENTER)
        x += w

    # 注釈矢印
    mline(sl, [
        "↑ hcitool コマンドの先頭バイト",
        "  （送信データ全体の長さ）",
    ], M, Inches(2.85), Inches(1.5), Inches(0.65), size=10, color=C_SUB)

    mline(sl, [
        "  ↑ AD 要素の長さ",
        "  = type(1)+UUID(2)+msg(25) = 28",
    ], Inches(0.65), Inches(2.85), Inches(1.7), Inches(0.65), size=10, color=C_SUB)

    mline(sl, [
        "↑ BLE 規定の AD タイプ",
        "0x16 = Service Data – 16-bit UUID",
    ], Inches(1.35), Inches(2.85), Inches(2.0), Inches(0.65), size=10, color=C_SUB)

    mline(sl, [
        "↑ OpenDroneID 専用の",
        "BLE Service UUID（ASTM で規定）",
    ], Inches(2.05), Inches(2.85), Inches(2.0), Inches(0.65), size=10, color=C_SUB)

    txb(sl, "AD タイプの意味（0x16 を使う理由）",
        M, Inches(3.72), IW, Inches(0.35), size=13, bold=True, color=C_BLACK)
    tbl(sl,
        ["AD タイプ値", "名称", "用途"],
        [
            ["0x01", "Flags",                        "BLE デバイスの機能フラグ"],
            ["0x03", "Complete List of 16-bit UUIDs", "デバイスが対応する Service UUID の一覧"],
            ["0x09", "Complete Local Name",           "デバイス名（文字列）"],
            ["0xFF", "Manufacturer Specific Data",    "メーカー独自データ（旧実装で使用していた型）"],
            ["0x16", "Service Data – 16-bit UUID",    "特定 UUID に紐づくサービスデータ ← OpenDroneID はこれ"],
        ],
        M, Inches(4.12), IW, cw=[Inches(1.1), Inches(3.0), Inches(4.8)], fs=11)

    # =========================================================================
    # 10. 変更前後の比較
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "実装変更: 独自フォーマット → OpenDroneID 準拠", "何がどう変わったか", part="Part 2 — BLE 通信の仕組み")
    pnum(sl, 10)

    txb(sl, "変更前（独自フォーマット）",
        M, Inches(1.18), Inches(4.35), Inches(0.35), size=13, bold=True, color=C_BLACK)
    code(sl, [
        "BLE Manufacturer Specific Data  (AD type 0xFF)",
        "  Company ID : 0x02E5",
        "  [MAGIC=0x5A][VERSION=0x01]",
        "  [lat_e7 4B][lon_e7 4B]",
        "  [alt_dm 2B][unix_time 4B][seq 1B]",
        "  合計: 17 バイト（完全独自仕様）",
    ], M, Inches(1.58), Inches(4.35), Inches(2.05), size=10)

    txb(sl, "変更後（OpenDroneID 準拠）",
        Inches(5.00), Inches(1.18), Inches(4.60), Inches(0.35), size=13, bold=True, color=C_BLACK)
    code(sl, [
        "BLE Service Data  (AD type 0x16)",
        "  Service UUID : 0xFFFA",
        "  [25 バイト ASTM F3411 メッセージ]",
        "  合計: 29 バイト（規格準拠）",
        "  ↕",
        "  BasicID  / Location を交互送信",
    ], Inches(5.00), Inches(1.58), Inches(4.60), Inches(2.05), size=10)

    txb(sl, "フィールドごとの変化",
        M, Inches(3.82), IW, Inches(0.35), size=13, bold=True, color=C_BLACK)
    tbl(sl,
        ["フィールド", "変更前（独自）", "変更後（ODID）", "変化のポイント"],
        [
            ["AD タイプ",    "0xFF (Manufacturer Specific)", "0x16 (Service Data)",
             "規格で定められた型に変更"],
            ["識別子",       "Company ID 0x02E5",            "Service UUID 0xFFFA",
             "ASTM F3411 専用 UUID に統一"],
            ["高度単位",     "int16 LE、デシメートル (0.1 m)", "uint16 LE、(alt+1000)/0.5 (0.5 m)",
             "範囲が −1000 m〜+31 km に拡大"],
            ["タイムスタンプ","uint32 LE、Unix 絶対秒",        "uint16 LE、時間内秒×10（相対値）",
             "バイト数を 4B→2B に削減"],
            ["機体識別子",   "なし",                          "BasicID の UAS_ID（20 バイト）",
             "機体の追跡が可能に"],
            ["速度・方向",   "なし",                          "Direction / SpeedH / SpeedV",
             "飛行状況が把握できるように"],
            ["互換性",       "独自のみ",                      "市販機・規制機関・受信アプリと互換",
             "オープンエコシステムへ"],
        ],
        M, Inches(4.22), IW,
        cw=[Inches(1.5), Inches(2.1), Inches(2.4), Inches(2.9)], fs=10)

    # =========================================================================
    # PART 3: メッセージ仕様
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    part_divider(sl, 3, "メッセージ仕様の詳細", "25 バイトに情報を詰め込むエンコード設計")
    pnum(sl, 11)

    # =========================================================================
    # 12. BasicID — 役割と概要
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "BasicID メッセージ — 役割と概要", "「この機体は誰か」を伝えるメッセージ", part="Part 3 — メッセージ仕様")
    pnum(sl, 12)

    txb(sl,
        "BasicID は機体の「名前カード」。UAS_ID（機体識別子）と機体の種類を\n"
        "周囲の受信者に伝えるためのメッセージ。MessageType = 0x0。",
        M, Inches(1.18), IW, Inches(0.80), size=14, color=C_TEXT)

    txb(sl, "IDType — 識別子の種類",
        M, Inches(2.18), Inches(4.4), Inches(0.35), size=13, bold=True, color=C_BLACK)
    tbl(sl,
        ["値", "定数名", "意味"],
        [
            ["0", "NONE",              "なし"],
            ["1", "SERIAL_NUMBER",     "製造シリアル番号（本実装）"],
            ["2", "CAA_REGISTRATION",  "航空当局の登録番号"],
            ["3", "UTM_ASSIGNED_UUID", "UTM システムが割り当てた UUID"],
            ["4", "SPECIFIC_SESSION",  "特定セッション用 ID"],
        ],
        M, Inches(2.58), Inches(4.4), cw=[Inches(0.45), Inches(2.0), Inches(1.95)], fs=11)

    txb(sl, "UAType — 機体の種類",
        Inches(5.0), Inches(2.18), Inches(4.6), Inches(0.35), size=13, bold=True, color=C_BLACK)
    tbl(sl,
        ["値", "定数名", "意味"],
        [
            ["0", "NONE",                      "未設定"],
            ["1", "AEROPLANE",                 "固定翼機"],
            ["2", "HELICOPTER_OR_MULTIROTOR",  "マルチローター（本実装）"],
            ["3", "GYROPLANE",                 "オートジャイロ"],
            ["4", "HYBRID_LIFT",               "ハイブリッド"],
        ],
        Inches(5.0), Inches(2.58), Inches(4.6),
        cw=[Inches(0.45), Inches(2.2), Inches(1.95)], fs=11)

    txb(sl, "本プロジェクトの設定",
        M, Inches(5.35), IW, Inches(0.35), size=13, bold=True, color=C_BLACK)
    rect(sl, M, Inches(5.75), IW, Inches(1.25), C_BOX, border=True)
    mline(sl, [
        "IDType  = 1（SERIAL_NUMBER）\n"
        "UAType  = 2（HELICOPTER_OR_MULTIROTOR）\n"
        "UAS_ID  = 'UAV-ZKP-M1-DEMO00'（18文字 + null 2バイト = 20バイト）",
    ], M+Inches(0.15), Inches(5.85), IW-Inches(0.3), Inches(1.00),
        size=13, color=C_TEXT, gap=5)

    # =========================================================================
    # 13. BasicID — バイト詳細
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "BasicID — 25 バイトの全フィールド", "バイトレイアウトとエンコード式", part="Part 3 — メッセージ仕様")
    pnum(sl, 13)

    tbl(sl,
        ["バイト", "フィールド", "型", "エンコード", "本実装の値"],
        [
            ["0",     "Header",    "uint8",    "(MessageType << 4) | ProtoVersion",
             "0x02 = (0<<4)|2"],
            ["1",     "IDType / UAType", "uint8",
             "上位 4 bit = IDType\n下位 4 bit = UAType",
             "0x12 = (1<<4)|2"],
            ["2-21",  "UAS_ID",    "20 bytes", "ASCII 文字列、右側を 0x00 でパディング",
             "'UAV-ZKP-M1-DEMO00\\x00\\x00'"],
            ["22-24", "Reserved",  "3 bytes",  "0x00 × 3",
             "0x00 0x00 0x00"],
        ],
        M, Inches(1.12), IW,
        cw=[Inches(0.72), Inches(1.6), Inches(0.85), Inches(3.0), Inches(2.73)], fs=11)

    txb(sl, "Byte 1 のビットレイアウト（重要）",
        M, Inches(3.10), IW, Inches(0.35), size=13, bold=True, color=C_BLACK)
    code(sl, [
        "Byte 1 ビット配置（opendroneid-core-c 準拠）:",
        "  bit 7  bit 6  bit 5  bit 4  |  bit 3  bit 2  bit 1  bit 0",
        "  ──────── IDType (上位ニブル) ──────── |  ──────── UAType (下位ニブル) ────────",
        "",
        "例: IDType=1, UAType=2 の場合",
        "  IDType = 1 = 0001",
        "  UAType = 2 = 0010",
        "  Byte 1 = (1 << 4) | 2 = 0001_0010 = 0x12",
        "",
        "⚠ 注意: IDType が上位ニブル（MSB 側）。逆にすると受信側で機体種別が変わってしまう。",
    ], M, Inches(3.52), IW, Inches(3.28), size=10)

    txb(sl, "Python エンコード",
        M, Inches(6.92), IW, Inches(0.35), size=13, bold=True, color=C_BLACK)
    code(sl, [
        "header = (ODID_MESSAGETYPE_BASIC_ID << 4) | ODID_PROTOCOL_VERSION  # (0<<4)|2 = 0x02",
        "id_ua  = ((id_type & 0x0F) << 4) | (ua_type & 0x0F)               # (1<<4)|2 = 0x12",
        "uas_id_b = uas_id[:20].ljust(20, b'\\x00')                          # 20バイトにパディング",
        "return struct.pack('<BB20s3s', header, id_ua, uas_id_b, b'\\x00\\x00\\x00')",
    ], M, Inches(7.30), IW, Inches(1.08), size=10)

    # =========================================================================
    # 14. Location — 役割と概要
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "Location メッセージ — 役割と概要", "「今どこにいるか」を伝える中心的メッセージ", part="Part 3 — メッセージ仕様")
    pnum(sl, 14)

    txb(sl,
        "Location は機体の現在位置・速度・高度・タイムスタンプを送信する。\n"
        "ASTM F3411 では 1 秒以上の頻度での送信が義務付けられている。MessageType = 0x1。",
        M, Inches(1.18), IW, Inches(0.80), size=14, color=C_TEXT)

    # 25バイトのカテゴリ図解
    cats = [
        (Inches(0.72), "Byte 0\nHeader\n（型・バージョン）"),
        (Inches(0.72), "Byte 1\nStatus / Flags\n（8 種のフラグ）"),
        (Inches(1.10), "Bytes 2-4\n速度・方向\n（Direction / SpeedH / SpeedV）"),
        (Inches(2.20), "Bytes 5-12\n位置\n（Latitude / Longitude）"),
        (Inches(1.80), "Bytes 13-18\n高度\n（Baro / Geo / Height）"),
        (Inches(0.90), "Bytes 19-20\n精度フラグ\n（Horiz / Vert 等）"),
        (Inches(1.20), "Bytes 21-23\nタイムスタンプ\n（0.1 秒単位）"),
        (Inches(0.36), "Byte 24\nRsv"),
    ]
    x = M; y = Inches(2.22)
    for w, label in cats:
        rect(sl, x, y, w, Inches(1.50), C_BOX, border=True)
        txb(sl, label, x+Inches(0.05), y+Inches(0.08),
            w-Inches(0.10), Inches(1.35), size=9, color=C_TEXT, align=PP_ALIGN.CENTER)
        x += w

    txb(sl, "各フィールドが持つ意味",
        M, Inches(3.92), IW, Inches(0.35), size=13, bold=True, color=C_BLACK)
    tbl(sl,
        ["フィールド群", "送信する情報", "なぜ必要か"],
        [
            ["Status / Flags（Byte 1）",
             "飛行状態（AIRBORNE 等）\n速度域・方向の補正フラグ",
             "機体が実際に飛んでいるか、速度のスケールはどちらかを判定するのに必要"],
            ["速度・方向（Bytes 2-4）",
             "進行方向（0〜359°）\n水平・垂直速度（m/s）",
             "機体の動きを把握。衝突回避や軌跡予測に使用"],
            ["位置（Bytes 5-12）",
             "緯度・経度（1e-7 度精度）",
             "地図上での位置特定。ZK 証明の主入力"],
            ["高度（Bytes 13-18）",
             "気圧高度（BME280 QFE）\nGPS 高度（WGS84）",
             "2 種類の高度を持つことで高度基準の違いに対応"],
            ["タイムスタンプ（Bytes 21-22）",
             "UTC 時間内の経過秒数（0.1 秒精度）",
             "ZK 証明の「5 秒以内」判定に必要"],
        ],
        M, Inches(4.32), IW, cw=[Inches(2.0), Inches(2.8), Inches(4.1)], fs=11)

    # =========================================================================
    # 15. Location Byte 0-1 詳細
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "Location — Byte 0 と Byte 1 の詳細", "Header とフラグバイトのビット設計", part="Part 3 — メッセージ仕様")
    pnum(sl, 15)

    txb(sl, "Byte 0 — Header", M, Inches(1.18), IW, Inches(0.35),
        size=14, bold=True, color=C_BLACK)
    code(sl, [
        "bit 7  bit 6  bit 5  bit 4  |  bit 3  bit 2  bit 1  bit 0",
        "────────── MessageType ────── |  ───────── ProtoVersion ─────────",
        "",
        "MessageType = 1（Location）",
        "ProtoVersion = 2（ASTM F3411-22a）",
        "→ Byte 0 = (1 << 4) | 2 = 0001_0010 = 0x12",
    ], M, Inches(1.58), IW, Inches(1.95), size=10)

    txb(sl, "Byte 1 — Status / Flags（8 ビット全解説）",
        M, Inches(3.65), IW, Inches(0.35), size=14, bold=True, color=C_BLACK)
    code(sl, [
        "bit 7  bit 6  bit 5  bit 4  |  bit 3  |  bit 2     |  bit 1       |  bit 0",
        "──────────── Status ──────── | Reserved|  HeightType| EWDirection  |  SpeedMult",
        "",
        "Status（bits 7-4, 上位ニブル）:",
        "  0 = UNDECLARED  1 = GROUND  2 = AIRBORNE（本実装）  3 = EMERGENCY  4 = RC_LOST",
        "",
        "HeightType（bit 2）:",
        "  0 = 離陸点基準（Over Takeoff）← 本実装  1 = 地上基準（Over Ground）",
        "",
        "EWDirection（bit 1）:",
        "  0 = 方向が 0-179°（東半球）  1 = 方向が 180-359°（+180° して送信）",
        "",
        "SpeedMult（bit 0）:",
        "  0 = 水平速度 × 0.25 m/s（低速域 0-63.75 m/s）",
        "  1 = 水平速度 × 0.75 m/s（高速域 63.75-254.25 m/s）",
    ], M, Inches(4.05), IW, Inches(3.35), size=9)

    txb(sl, "本実装の Byte 1 = 0x20",
        M, H-Inches(0.62), IW, Inches(0.32), size=12, bold=True, color=C_BLACK)
    code(sl, [
        "byte1 = ((AIRBORNE=2) << 4) | (Reserved=0 << 3) | (HeightType=0 << 2) | (EWDir=0 << 1) | (SpeedMult=0)",
        "     = 0x20 = 0010_0000",
    ], M, H-Inches(0.38), IW, Inches(0.32), size=10)

    # =========================================================================
    # 16. Location Bytes 2-12（速度・座標）
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "Location — Bytes 2〜12（速度・方向・座標）", "速度のデュアルスケールと座標の整数変換", part="Part 3 — メッセージ仕様")
    pnum(sl, 16)

    tbl(sl,
        ["バイト", "フィールド", "型", "エンコード方式", "値の範囲", "本実装"],
        [
            ["2", "Direction",       "uint8",
             "EWDir=0 → そのまま 0-179°\nEWDir=1 → raw+180° = 180-359°",
             "0〜359°", "0（方向不明）"],
            ["3", "SpeedHorizontal", "uint8",
             "SpeedMult=0 → raw × 0.25 m/s\nSpeedMult=1 → raw × 0.75 m/s",
             "0〜254.25 m/s", "0（静止）"],
            ["4", "SpeedVertical",   "int8（符号付き）",
             "× 0.5 m/s\n正=上昇、負=降下",
             "−62〜+62 m/s", "0（静止）"],
            ["5-8",  "Latitude",  "int32 LE（符号付き）",
             "lat_deg × 10,000,000\n南緯は負の値",
             "±90°（1e-7 度精度）",
             "GPS 実測値"],
            ["9-12", "Longitude", "int32 LE（符号付き）",
             "lon_deg × 10,000,000\n西経は負の値",
             "±180°（1e-7 度精度）",
             "GPS 実測値"],
        ],
        M, Inches(1.12), IW,
        cw=[Inches(0.72), Inches(1.70), Inches(1.0), Inches(2.25), Inches(1.5), Inches(1.73)],
        fs=10)

    txb(sl, "速度のデュアルスケール設計（なぜ 2 段階か）",
        M, Inches(4.20), IW, Inches(0.35), size=13, bold=True, color=C_BLACK)
    rect(sl, M, Inches(4.60), IW, Inches(1.60), C_BOX, border=True)
    mline(sl, [
        "uint8（0〜255）のままでは最大 255 × 0.25 = 63.75 m/s（≈ 229 km/h）しか表現できない",
        "しかし高速ドローンや固定翼機は 100 m/s 以上になる場合もある",
        "",
        "解決策: SpeedMult フラグで 2 段階切替",
        "  SpeedMult=0（低速）: raw × 0.25  → 最大 63.75 m/s（精度 0.25 m/s）",
        "  SpeedMult=1（高速）: raw × 0.75  → 最大 254.25 m/s（精度 0.75 m/s）",
        "  ※ 低速域では精度を細かく、高速域では範囲を広げる設計",
    ], M+Inches(0.15), Inches(4.70), IW-Inches(0.3), Inches(1.40),
        size=11, color=C_TEXT, gap=3)

    txb(sl, "座標の変換例",
        M, Inches(6.35), IW, Inches(0.35), size=13, bold=True, color=C_BLACK)
    code(sl, [
        "緯度 34.9686023° → 34.9686023 × 1e7 = 349,686,023 → int32 LE: 0xC7_0CE614",
        "経度 135.8992150° → 135.8992150 × 1e7 = 1,358,992,150 → int32 LE: 0x16_50E950 51",
        "南緯・西経は負の int32 → リトルエンディアンで送信（2 の補数表現）",
    ], M, Inches(6.75), IW, Inches(0.65), size=10)

    # =========================================================================
    # 17. Location Bytes 13-24（高度・精度・タイムスタンプ）
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "Location — Bytes 13〜24（高度・精度・タイムスタンプ）", "なぜ 2 種類の高度を持つか", part="Part 3 — メッセージ仕様")
    pnum(sl, 17)

    tbl(sl,
        ["バイト", "フィールド", "型", "エンコード式（uint16）", "本実装の値"],
        [
            ["13-14", "AltitudeBaro", "uint16 LE",
             "(alt_m + 1000) / 0.5\n−1000 m 基準、0.5 m 精度\n0xFFFF = 不明",
             "BME280 の QFE 相対高度"],
            ["15-16", "AltitudeGeo",  "uint16 LE",
             "同上エンコード\nGPS WGS84 楕円体高",
             "GPS の WGS84 高度"],
            ["17-18", "Height",       "uint16 LE",
             "同上エンコード\n地上からの高さ（AGL）\n0xFFFF = 不明",
             "0xFFFF（不明）"],
            ["19", "精度フラグ 1", "uint8",
             "bits 7-4: VertAccuracy\nbits 3-0: HorizAccuracy\n0 = UNKNOWN",
             "0x00（不明）"],
            ["20", "精度フラグ 2", "uint8",
             "bits 7-4: SpeedAccuracy\nbits 3-0: BaroAccuracy\n0 = UNKNOWN",
             "0x00（不明）"],
            ["21-22", "Timestamp",    "uint16 LE",
             "(unix_sec % 3600) × 10\n1 時間内の 0.1 秒単位経過秒数",
             "Pi の現在時刻から計算"],
            ["23", "TSAccuracy",  "uint8",
             "bits 3-0: タイムスタンプ精度\n0 = UNKNOWN",
             "0x00（不明）"],
            ["24", "Reserved",    "uint8", "0x00", "0x00"],
        ],
        M, Inches(1.12), IW,
        cw=[Inches(0.72), Inches(1.50), Inches(0.82), Inches(2.58), Inches(2.28)],
        fs=9, rh=0.38)

    txb(sl, "なぜ高度を 2 種類（Baro / Geo）持つか",
        M, Inches(6.12), IW, Inches(0.35), size=12, bold=True, color=C_BLACK)
    mline(sl, [
        "・AltitudeBaro（BME280）: 起動点からの相対高度。精度は高いが「どこから測るか」で変わる",
        "・AltitudeGeo（GPS）: WGS84 楕円体高。絶対的な高度だが誤差 ±10-30 m",
        "→ 両方を送ることで受信側が状況に応じて使い分けられる設計",
    ], M, Inches(6.50), IW, Inches(0.88), size=11, color=C_TEXT, gap=3)

    # =========================================================================
    # 18. タイムスタンプ設計
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "タイムスタンプ設計", "Unix 秒を 2 バイトに収める工夫", part="Part 3 — メッセージ仕様")
    pnum(sl, 18)

    txb(sl, "なぜ Unix 絶対秒（4 バイト）を使わないか",
        M, Inches(1.18), IW, Inches(0.35), size=14, bold=True, color=C_BLACK)
    rect(sl, M, Inches(1.58), IW, Inches(0.80), C_BOX, border=True)
    txb(sl,
        "Unix 秒は 4 バイト必要。既に 25 バイト枠が他フィールドで埋まっているため、\n"
        "タイムスタンプに 4 バイトを使うと座標か高度のどちらかが削れなくなる。",
        M+Inches(0.15), Inches(1.65), IW-Inches(0.3), Inches(0.65), size=12, color=C_TEXT)

    txb(sl, "ASTM の解決策：時間内相対秒 × 10（uint16 = 2 バイト）",
        M, Inches(2.52), IW, Inches(0.35), size=14, bold=True, color=C_BLACK)
    code(sl, [
        "送信側（Pi / Python）:",
        "  ts = (unix_sec % 3600) * 10     # 1時間内の経過秒数を0.1秒単位で表現",
        "  例: unix_sec = 1,777,524,442",
        "      → 1,777,524,442 % 3600 = 1842 秒",
        "      → 1842 × 10 = 18420 → uint16 LE で送信",
        "",
        "受信側（Flutter / Dart）:",
        "  秒数 = tsRaw ÷ 10              # 0.1秒単位 → 秒",
        "  hourStart = nowSec - (nowSec % 3600)  # 現在時刻の「時間境界」",
        "  unix_sec  = hourStart + 秒数          # Unix秒に再構築",
        "",
        "uint16 の最大値 = 65535 ≥ 3600 × 10 = 36000  ✔  1時間分が収まる",
    ], M, Inches(2.92), IW, Inches(3.80), size=10)

    txb(sl, "時刻またぎ（59分 → 0分）の補正",
        M, Inches(6.85), IW, Inches(0.35), size=13, bold=True, color=C_BLACK)
    mline(sl, [
        "tsRaw が現在の秒数より大きい場合 → 前の時間帯の値 → hourStart から 1 時間引いて補正",
        "（本実装では簡易版として「現在の時間境界 + 時間内秒」を使用）",
    ], M, Inches(7.22), IW, Inches(0.55), size=12, color=C_TEXT, gap=3)

    # =========================================================================
    # PART 4: Pi 側実装
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    part_divider(sl, 4, "Pi 側実装（送信側）", "Python で OpenDroneID パケットをゼロから組み立てる")
    pnum(sl, 19)

    # =========================================================================
    # 20. Pi 側全体構成
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "Pi 側実装の全体構成", "remote_id.py の 4 レイヤー設計", part="Part 4 — Pi 側実装")
    pnum(sl, 20)

    layers = [
        ("テレメトリ取得レイヤー", [
            "StaticTelemetryProvider",
            "  → CLI 引数の固定座標",
            "JsonTelemetryProvider",
            "  → JSON ファイルから動的取得",
            "GpsBme280TelemetryProvider",
            "  → GPS（NMEA）+ BME280",
            "  → 別スレッドで常時受信",
        ]),
        ("エンコードレイヤー", [
            "_encode_altitude()",
            "_encode_direction()",
            "_encode_speed_h()",
            "_encode_speed_v()",
            "_encode_timestamp()",
            "build_basic_id_message()",
            "build_location_message()",
        ]),
        ("ペイロード組立レイヤー", [
            "build_adv_payload()",
            "  → 25B ODID メッセージ",
            "  → UUID 0xFFFA を付加",
            "  → 長さバイトを付加",
            "  → ゼロパディング",
            "  → 31B BLE パケット完成",
        ]),
        ("BLE 送信レイヤー", [
            "configure_adapter()",
            "  → hciconfig hci0 up",
            "enable_advertising()",
            "  → HCI 0x08/0x000A",
            "set_advertising_data()",
            "  → HCI 0x08/0x0008",
        ]),
    ]
    for i, (title, items) in enumerate(layers):
        x = M + Inches(2.28) * i
        rect(sl, x, Inches(1.18), Inches(2.15), Inches(5.00), C_LIGHT, border=True)
        txb(sl, title, x+Inches(0.1), Inches(1.25), Inches(1.95), Inches(0.38),
            size=11, bold=True, color=C_BLACK)
        rect(sl, x+Inches(0.1), Inches(1.65), Inches(1.95), Pt(0.8), C_RULE)
        mline(sl, items, x+Inches(0.1), Inches(1.75), Inches(1.95), Inches(4.28),
              size=10, color=C_TEXT, gap=3, mono=True)

    txb(sl, "メインループ（1 秒ごとに Location / BasicID を交互送信）",
        M, Inches(6.32), IW, Inches(0.35), size=12, bold=True, color=C_BLACK)
    code(sl, [
        "while True:",
        "    sample = provider.read()                       # テレメトリ取得",
        "    msg = build_location_message(sample) if seq%2==0 else build_basic_id_message()",
        "    set_advertising_data(build_adv_payload(msg))   # HCI へ書き込み",
        "    enable_advertising(True)                       # 送信開始",
        "    seq = (seq+1) % 256;  time.sleep(1.0)          # 1秒待機",
    ], M, Inches(6.72), IW, Inches(0.68), size=10)

    # =========================================================================
    # 21. エンコード関数群
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "Pi 側 — エンコード関数群の実装", "opendroneid-core-c と同一の係数・計算式", part="Part 4 — Pi 側実装")
    pnum(sl, 21)

    sec(sl, "定数定義（opendroneid-core-c と完全一致）", M, Inches(1.12))
    code(sl, [
        "_LATLON_MULT  = 10_000_000   # 座標: 1 LSB = 1e-7 度",
        "_ALT_DIV      = 0.5          # 高度: 1 LSB = 0.5 m",
        "_ALT_ADDER    = 1000         # 高度オフセット（−1000 m 基準）",
        "_SPEED_DIV    = [0.25, 0.75] # 水平速度: 低速域 / 高速域",
        "_VSPEED_DIV   = 0.5          # 垂直速度: 1 LSB = 0.5 m/s",
    ], M, Inches(1.55), Inches(4.8), Inches(1.50), size=10)

    sec(sl, "各エンコード関数", Inches(5.15), Inches(1.12), Inches(4.5))
    code(sl, [
        "def _encode_altitude(alt_m):",
        "    if alt_m <= -1000: return 0xFFFF",
        "    raw = round((alt_m + 1000) / 0.5)",
        "    return max(0, min(0xFFFE, raw))",
        "",
        "def _encode_direction(deg):  # → (EWDir, uint8)",
        "    if deg >= 180.0:",
        "        return 1, round(deg - 180.0)",
        "    return 0, round(deg)",
        "",
        "def _encode_speed_h(ms):    # → (SpeedMult, uint8)",
        "    if ms <= 63.75:",
        "        return 0, round(ms / 0.25)  # 低速域",
        "    return 1, round((ms-63.75)/0.75) # 高速域",
        "",
        "def _encode_speed_v(ms):    # → int8",
        "    return round(max(-62.0,min(62.0,ms)) / 0.5)",
        "",
        "def _encode_timestamp(unix_sec): # → uint16",
        "    return ((unix_sec % 3600) * 10) & 0xFFFF",
    ], Inches(5.15), Inches(1.55), Inches(4.5), Inches(5.82), size=9)

    sec(sl, "struct.pack フォーマット（Location 25 バイト）", M, Inches(3.18))
    code(sl, [
        "struct.pack('<BBBBbiiHHHBBHBB',",
        "    header,      # B = uint8  : byte 0",
        "    byte1,       # B = uint8  : byte 1",
        "    dir_enc,     # B = uint8  : byte 2  方向",
        "    speed_h_enc, # B = uint8  : byte 3  水平速度",
        "    speed_v_enc, # b = int8   : byte 4  垂直速度",
        "    lat_i32,     # i = int32LE: bytes 5-8   緯度",
        "    lon_i32,     # i = int32LE: bytes 9-12  経度",
        "    alt_baro,    # H = uint16LE: bytes 13-14 気圧高度",
        "    alt_geo,     # H = uint16LE: bytes 15-16 GPS高度",
        "    0xFFFF,      # H = uint16LE: bytes 17-18 Height=不明",
        "    acc19,       # B = uint8  : byte 19 精度",
        "    acc20,       # B = uint8  : byte 20 精度",
        "    ts,          # H = uint16LE: bytes 21-22 タイムスタンプ",
        "    ts_acc,      # B = uint8  : byte 23 TS精度",
        "    0,           # B = uint8  : byte 24 Reserved",
        ")",
    ], M, Inches(3.58), Inches(4.8), Inches(4.30), size=9)

    # =========================================================================
    # 22. HCI コマンド詳細
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "Pi 側 — HCI コマンドの詳細", "Bluetooth チップに直接コマンドを送る仕組み", part="Part 4 — Pi 側実装")
    pnum(sl, 22)

    txb(sl,
        "Python から subprocess 経由で hcitool を呼び出し、HCI（Host Controller Interface）\n"
        "コマンドを直接 Bluetooth チップに送信する。OS の Bluetooth スタックを介さない低レベル操作。",
        M, Inches(1.18), IW, Inches(0.80), size=13, color=C_TEXT)

    cmds = [
        ("Step 1  アダプタ UP",
         "sudo hciconfig hci0 up",
         "hci0（Bluetooth チップ）を有効化。既に UP の場合は\nnon-zero が返るが check=True を外してエラー無視。"),
        ("Step 2  広告パラメータ設定  (HCI OGF=0x08, OCF=0x0006)",
         "sudo hcitool -i hci0 cmd 0x08 0x0006\n"
         "    A0 00  ← Advertising_Interval_Min = 160×0.625ms = 100ms\n"
         "    A0 00  ← Advertising_Interval_Max = 100ms\n"
         "    03     ← ADV_NONCONN_IND（接続不可）\n"
         "    07     ← Channel 37+38+39（全3チャンネル）",
         "接続要求を無視するモード。スキャンのみで受信可能。"),
        ("Step 3  広告データ書き込み  (HCI OGF=0x08, OCF=0x0008)",
         "sudo hcitool -i hci0 cmd 0x08 0x0008\n"
         "    1D     ← total_length = 29\n"
         "    1C 16 FA FF ← length=28, AD-type=0x16, UUID=0xFFFA(LE)\n"
         "    [25バイト ODID メッセージ]\n"
         "    00 00  ← ゼロパディング",
         "チップのバッファに広告データを書き込む。"),
        ("Step 4  広告有効化  (HCI OGF=0x08, OCF=0x000A)",
         "sudo hcitool -i hci0 cmd 0x08 0x000A  01",
         "01 = Enable。ここから 1 秒後に Step 3+4 を繰り返す。"),
    ]
    for i, (title, cmd, note) in enumerate(cmds):
        y = Inches(2.18) + Inches(1.22) * i
        rect(sl, M, y, Inches(0.38), Inches(1.10), C_BLACK)
        txb(sl, str(i+1), M+Inches(0.04), y+Inches(0.28),
            Inches(0.30), Inches(0.45), size=18, bold=True, color=C_BG, align=PP_ALIGN.CENTER)
        txb(sl, title, M+Inches(0.48), y+Inches(0.04),
            IW-Inches(0.48), Inches(0.30), size=11, bold=True, color=C_BLACK)
        code(sl, cmd.splitlines(), M+Inches(0.48), y+Inches(0.36),
             Inches(5.8), Inches(0.68), size=9)
        txb(sl, note, Inches(6.45), y+Inches(0.08),
            Inches(3.15), Inches(0.98), size=10, color=C_TEXT)

    # =========================================================================
    # PART 5: Flutter 側実装
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    part_divider(sl, 5, "Flutter 側実装（受信側）", "UavTelemetryPacket でパケットを復元する")
    pnum(sl, 23)

    # =========================================================================
    # 24. UavTelemetryPacket クラス設計
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "Flutter — UavTelemetryPacket クラス設計", "受信したバイト列を Dart オブジェクトに変換する", part="Part 5 — Flutter 側実装")
    pnum(sl, 24)

    txb(sl,
        "BLE で受信した生バイト列（List<int>）を解析し、緯度・経度・高度・速度・時刻を\n"
        "Dart の型として取り出すクラス。Pi 側の Python と完全対称の逆演算を行う。",
        M, Inches(1.18), IW, Inches(0.80), size=13, color=C_TEXT)

    txb(sl, "クラスの全フィールド",
        M, Inches(2.12), IW, Inches(0.35), size=13, bold=True, color=C_BLACK)
    tbl(sl,
        ["フィールド名", "型", "由来", "説明"],
        [
            ["latitude",          "double", "Location bytes 5-8",  "緯度（度）= int32 ÷ 1e7"],
            ["longitude",         "double", "Location bytes 9-12", "経度（度）= int32 ÷ 1e7"],
            ["altitudeMeters",    "double", "Location bytes 13-14","気圧高度 m（BME280 QFE）"],
            ["altitudeGeoMeters", "double", "Location bytes 15-16","GPS 高度 m（WGS84）"],
            ["speedH",            "double", "Location byte 3",     "水平速度 m/s"],
            ["speedV",            "double", "Location byte 4",     "垂直速度 m/s（正=上昇）"],
            ["direction",         "double", "Location byte 2",     "進行方向 0-359°"],
            ["statusIsAirborne",  "bool",   "Location byte 1",     "Status == AIRBORNE(2)"],
            ["unixTimeSec",       "int",    "Location bytes 21-22","再構築した Unix タイムスタンプ"],
            ["sequence",          "int",    "アプリ内カウンタ",     "受信順の連番"],
            ["uasId",             "String?","BasicID bytes 2-21",  "機体識別子（BasicID から取得）"],
        ],
        M, Inches(2.52), IW,
        cw=[Inches(1.85), Inches(0.65), Inches(1.80), Inches(4.6)], fs=10)

    txb(sl, "定数（opendroneid-core-c と同一の値）",
        M, Inches(7.00), IW, Inches(0.35), size=12, bold=True, color=C_BLACK)
    code(sl, [
        "static const serviceUuid    = '0000fffa-0000-1000-8000-00805f9b34fb';  // 128bit 展開",
        "static const _msgTypeBasicId  = 0;  // ODID_MESSAGETYPE_BASIC_ID",
        "static const _msgTypeLocation = 1;  // ODID_MESSAGETYPE_LOCATION",
        "static const _statusAirborne  = 2;  // ODID_STATUS_AIRBORNE",
    ], M, Inches(7.38), IW, Inches(0.95), size=10)

    # =========================================================================
    # 25. UUID 検索と BLE スキャン設計
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "Flutter — UUID 検索と BLE スキャン設計", "withServices を使わない理由と 22 秒サイクル", part="Part 5 — Flutter 側実装")
    pnum(sl, 25)

    txb(sl, "UUID 検索に工夫が必要な理由",
        M, Inches(1.18), IW, Inches(0.35), size=13, bold=True, color=C_BLACK)
    tbl(sl,
        ["問題", "原因", "解決策"],
        [
            ["withServices フィルターが効かない",
             "remote_id.py は Service Data（AD type 0x16）のみを送信。\n"
             "UUID Advertisement List（AD type 0x03）を含まないため、\n"
             "Android の withServices フィルターが 0xFFFA を見つけられない",
             "withServices を空にして全広告を受信し、serviceData から 0xFFFA を手動検索"],
            ["GUID の表記ゆれ",
             "flutter_blue_plus は serviceData のキーを\n"
             "'0000fffa-0000-1000-8000-00805f9b34fb' という 128-bit 形式で返す。\n"
             "プラットフォームにより大文字/小文字が異なる",
             "key.toString().toLowerCase().contains('fffa') で検索"],
        ],
        M, Inches(1.58), IW, cw=[Inches(2.0), Inches(3.5), Inches(3.4)], fs=10)

    sec(sl, "UUID 検索の実装", M, Inches(4.00))
    code(sl, [
        "static List<int>? extractFromServiceData(Map<dynamic, List<int>> serviceData) {",
        "  for (final entry in serviceData.entries) {",
        "    if (entry.key.toString().toLowerCase().contains('fffa')) {",
        "      return entry.value;   // 25バイトの ODID メッセージ本体",
        "    }",
        "  }",
        "  return null;   // OpenDroneID パケットではない",
        "}",
    ], M, Inches(4.40), IW, Inches(2.15), size=10)

    sec(sl, "22 秒サイクルの連続スキャン", M, Inches(6.68))
    code(sl, [
        "// 起動時に即スキャン開始 + 22秒ごとに再スキャン",
        "_bleRescanTimer = Timer.periodic(Duration(seconds: 22), (_) {",
        "  if (!_isScanningDrone) unawaited(_restartBleScan());",
        "});",
        "// スキャン時間は 20秒。2秒の余裕で次のサイクルへ",
    ], M, Inches(7.05), IW, Inches(1.35), size=10)

    # =========================================================================
    # 26. tryParseLocation 実装
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "Flutter — tryParseLocation の全実装", "25 バイトから全フィールドを復元するコア処理", part="Part 5 — Flutter 側実装")
    pnum(sl, 26)

    code(sl, [
        "static UavTelemetryPacket? tryParseLocation(List<int>? rawBytes, int seq) {",
        "  if (rawBytes == null || rawBytes.length < 25) return null;",
        "",
        "  // ① byte 0: 上位4bit = MessageType。Location(1) でなければ無視",
        "  if ((rawBytes[0] >> 4) & 0x0F != 1) return null;",
        "",
        "  // ② byte 1: Status / Flags のビット分解",
        "  final byte1     = rawBytes[1] & 0xFF;",
        "  final status    = (byte1 >> 4) & 0x0F;   // bits 7-4: Status（上位ニブル）",
        "  final ewDir     = (byte1 >> 1) & 0x01;   // bit 1   : EWDirection",
        "  final speedMult = byte1 & 0x01;           // bit 0   : SpeedMult",
        "",
        "  // ③ ByteData でリトルエンディアン読み出し",
        "  final data = ByteData.sublistView(Uint8List.fromList(rawBytes));",
        "  final latI32  = data.getInt32 (5,  Endian.little);  // bytes 5-8",
        "  final lonI32  = data.getInt32 (9,  Endian.little);  // bytes 9-12",
        "  final altBaro = data.getUint16(13, Endian.little);  // bytes 13-14",
        "  final altGeo  = data.getUint16(15, Endian.little);  // bytes 15-16",
        "  final tsRaw   = data.getUint16(21, Endian.little);  // bytes 21-22",
        "",
        "  // ④ 無効座標（GPS Fix なし）はスキップ",
        "  if (latI32 == 0 && lonI32 == 0) return null;",
        "",
        "  // ⑤ 各フィールドをデコードしてオブジェクト生成",
        "  return UavTelemetryPacket(",
        "    latitude:          latI32 / 1e7,",
        "    longitude:         lonI32 / 1e7,",
        "    altitudeMeters:    _decodeAltitude(altBaro),",
        "    altitudeGeoMeters: _decodeAltitude(altGeo),",
        "    speedH:            _decodeSpeedH(rawBytes[3] & 0xFF, speedMult),",
        "    speedV:            _decodeSpeedV(rawBytes[4] & 0xFF),",
        "    direction:         _decodeDirection(rawBytes[2] & 0xFF, ewDir),",
        "    statusIsAirborne:  status == 2,   // AIRBORNE = 2",
        "    unixTimeSec:       _reconstructUnixTime(tsRaw),",
        "    sequence:          seq,",
        "  );",
        "}",
    ], M, Inches(1.12), IW, Inches(6.25), size=9)

    # =========================================================================
    # 27. デコード関数群
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "Flutter — デコード関数群", "Pi 側エンコードの逆演算を Dart で実装", part="Part 5 — Flutter 側実装")
    pnum(sl, 27)

    sec(sl, "高度のデコード（_decodeAltitude）", M, Inches(1.12))
    code(sl, [
        "// エンコード式の逆算: alt_m = raw × 0.5 − 1000",
        "static double _decodeAltitude(int raw) {",
        "  if (raw == 0xFFFF) return 0.0;   // 不明値は 0.0 で返す",
        "  return raw * 0.5 - 1000.0;",
        "}",
        "// 例: raw=2024 → 2024×0.5−1000 = 12.0 m ✔",
    ], M, Inches(1.55), Inches(4.8), Inches(1.70), size=10)

    sec(sl, "方向のデコード（_decodeDirection）", Inches(5.15), Inches(1.12), Inches(4.5))
    code(sl, [
        "// EWDirection=1 のとき raw+180° で西半球を復元",
        "static double _decodeDirection(int raw, int ewDir) {",
        "  return ewDir == 1 ? raw + 180.0 : raw.toDouble();",
        "}",
    ], Inches(5.15), Inches(1.55), Inches(4.5), Inches(1.10), size=10)

    sec(sl, "水平速度のデコード（_decodeSpeedH）", M, Inches(3.38))
    code(sl, [
        "// SpeedMult で2段階スケールを切替",
        "static double _decodeSpeedH(int raw, int speedMult) {",
        "  return speedMult == 1 ? raw * 0.75 : raw * 0.25;",
        "}",
        "// 例: raw=40, SpeedMult=0 → 40×0.25 = 10.0 m/s",
    ], M, Inches(3.80), Inches(4.8), Inches(1.50), size=10)

    sec(sl, "垂直速度のデコード（_decodeSpeedV）", Inches(5.15), Inches(3.38), Inches(4.5))
    code(sl, [
        "// int8 の 2の補数表現を Dart で処理",
        "static double _decodeSpeedV(int raw) {",
        "  final signed = raw >= 128 ? raw - 256 : raw;",
        "  return signed * 0.5;",
        "}",
        "// 例: raw=254 → 254-256=-2 → -2×0.5 = -1.0 m/s（降下）",
    ], Inches(5.15), Inches(3.80), Inches(4.5), Inches(1.50), size=10)

    sec(sl, "タイムスタンプ再構築（_reconstructUnixTime）", M, Inches(5.42))
    code(sl, [
        "static int _reconstructUnixTime(int tsRaw) {",
        "  if (tsRaw == 0xFFFF) {",
        "    return DateTime.now().millisecondsSinceEpoch ~/ 1000;  // 不明 → 現在時刻",
        "  }",
        "  final secInHour = tsRaw ~/ 10;               // 0.1秒単位 → 秒に変換",
        "  final nowSec    = DateTime.now().millisecondsSinceEpoch ~/ 1000;",
        "  final hourStart = nowSec - (nowSec % 3600);  // 現在時刻の「時間境界」",
        "  return hourStart + secInHour;",
        "}",
        "// 例: tsRaw=18420 → 18420÷10=1842秒 + hourStart → Unix秒",
    ], M, Inches(5.82), IW, Inches(2.55), size=10)

    # =========================================================================
    # 28. Message Pack — なぜ必要か
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "Message Pack — なぜ必要か", "実機ドローンは複数メッセージを1パケットに束ねて送る", part="Part 5 — Flutter 側実装")
    pnum(sl, 28)

    txb(sl,
        "Pi の remote_id.py は BasicID と Location を交互に 1 件ずつ送信する。\n"
        "しかし市販ドローンの多くは「Message Pack」形式で複数メッセージをまとめて1回で送信する。",
        M, Inches(1.18), IW, Inches(0.80), size=14, color=C_TEXT)

    sec(sl, "なぜまとめて送るのか", M, Inches(2.12))
    tbl(sl,
        ["観点", "単一メッセージ方式（Pi）", "Message Pack 方式（実機ドローン）"],
        [
            ["1回の送信内容",
             "BasicID または Location\nどちらか 1 種類だけ（25B）",
             "BasicID + Location + System 等\n複数種類を同時に（最大 9 × 25B = 225B）"],
            ["受信側の処理",
             "複数パケットを時刻で紐付ける必要あり\n「どの BasicID がどの Location か」が曖昧",
             "1パケット内に全情報が揃う\n受信側が紐付け処理を省ける"],
            ["BLE 方式",
             "ADV_NONCONN_IND（Legacy 31B 上限）\n25B メッセージ 1 件が限界",
             "BT5 Extended Advertising（最大 255B）\n複数メッセージを束ねても収まる"],
            ["信頼性",
             "いずれかのパケットを逃すと\n位置と ID が揃わない場合あり",
             "1パケットで全情報 → パケットロス耐性が高い"],
        ],
        M, Inches(2.55), IW,
        cw=[Inches(1.55), Inches(3.15), Inches(4.20)], fs=10)

    txb(sl,
        "→ 現行アプリは Message Pack を認識できず、実機ドローンのパケットを全て無視してしまう。",
        M, Inches(6.65), IW, Inches(0.35), size=12, italic=True, color=C_SUB)

    rect(sl, M, Inches(7.05), IW, Pt(1), C_RULE)
    txb(sl, "対応前: extractFromServiceData() の戻り値を直接 tryParseLocation() に渡していた",
        M, Inches(7.12), IW, Inches(0.26), size=10, color=C_SUB)

    # =========================================================================
    # 29. Message Pack バイト構造
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "Message Pack — バイト構造", "ASTM F3411-22a §7.9 の仕様", part="Part 5 — Flutter 側実装")
    pnum(sl, 29)

    txb(sl,
        "Message Pack は先頭 3 バイトのヘッダーと、その後に続く 25B × N のメッセージ列で構成される。\n"
        "MessageType = 0xF がパックであることを示す識別子。",
        M, Inches(1.18), IW, Inches(0.80), size=13, color=C_TEXT)

    sec(sl, "Message Pack ペイロード構造", M, Inches(2.12))

    fields = [
        (Inches(1.30), "Byte 0\n(0xF << 4) | ProtoVersion\ntype=0xF でパックと判別"),
        (Inches(1.30), "Byte 1\nSingleMessageSize\n常に 25（固定）"),
        (Inches(1.30), "Byte 2\nMsgPackSize\nメッセージ数 1〜9"),
        (Inches(1.80), "Bytes 3-27\n1 つ目のメッセージ\n（25B）"),
        (Inches(1.80), "Bytes 28-52\n2 つ目のメッセージ\n（25B）"),
        (Inches(1.50), "…\n最大 9 件\n225B"),
    ]
    x = M; y = Inches(2.62)
    for w, label in fields:
        rect(sl, x, y, w, Inches(1.35), C_BOX, border=True)
        txb(sl, label, x+Inches(0.05), y+Inches(0.06),
            w-Inches(0.10), Inches(1.22), size=9, color=C_TEXT, align=PP_ALIGN.CENTER)
        x += w

    sec(sl, "実機ドローン（DJI 等）の典型的なパック例", M, Inches(4.18))
    code(sl, [
        "Byte 0 : 0xF2  →  MessageType=0xF (Pack), ProtoVersion=2",
        "Byte 1 : 0x19  →  SingleMessageSize=25",
        "Byte 2 : 0x03  →  MsgPackSize=3  （3件入っている）",
        "",
        "Bytes  3- 27 : BasicID   メッセージ（25B）  MessageType=0",
        "Bytes 28- 52 : Location  メッセージ（25B）  MessageType=1",
        "Bytes 53- 77 : System    メッセージ（25B）  MessageType=4",
    ], M, Inches(4.58), IW, Inches(2.10), size=10)

    txb(sl,
        "→ Byte 0 の上位ニブルが 0xF かどうかを先にチェックし、0xF なら Pack として処理する。",
        M, Inches(6.82), IW, Inches(0.35), size=12, italic=True, color=C_SUB)

    rect(sl, M, Inches(7.22), IW, Pt(1), C_RULE)
    txb(sl, "単一メッセージは Byte 0 の上位ニブルが 0 (BasicID) または 1 (Location) など 0xF 以外になる",
        M, Inches(7.28), IW, Inches(0.26), size=10, color=C_SUB)

    # =========================================================================
    # 30. extractAllMessages() 実装
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "Flutter — extractAllMessages() の実装", "単一メッセージと Message Pack を統一処理する", part="Part 5 — Flutter 側実装")
    pnum(sl, 30)

    txb(sl,
        "Service Data の生バイト列を受け取り、含まれる 25B メッセージを全て取り出して返すメソッド。\n"
        "呼び出し側は戻り値をループするだけでよく、Pack か否かを意識しない。",
        M, Inches(1.18), IW, Inches(0.80), size=13, color=C_TEXT)

    sec(sl, "extractAllMessages() — Dart 実装", M, Inches(2.12))
    code(sl, [
        "static List<List<int>> extractAllMessages(List<int> payload) {",
        "  if (payload.isEmpty) return [];",
        "  final type = (payload[0] >> 4) & 0xF;",
        "",
        "  if (type != _msgTypeMsgPack) {",
        "    return [payload];   // 単一メッセージをそのままリストに包む",
        "  }",
        "",
        "  // Message Pack: ヘッダーを読んで 25B ずつ切り出す",
        "  if (payload.length < 3) return [];",
        "  final count = payload[2];          // Byte 2 = メッセージ数",
        "  final messages = <List<int>>[];",
        "  for (var i = 0; i < count; i++) {",
        "    final start = 3 + i * 25;        // ヘッダー 3B のあとに 25B ずつ",
        "    if (start + 25 > payload.length) break;",
        "    messages.add(payload.sublist(start, start + 25));",
        "  }",
        "  return messages;",
        "}",
    ], M, Inches(2.52), Inches(5.8), Inches(5.10), size=10)

    sec(sl, "BLE スキャンハンドラでの使い方", Inches(6.05), Inches(2.12), Inches(3.55))
    code(sl, [
        "// 修正前",
        "final bytes = extractFromServiceData(sd);",
        "tryParseUasId(bytes);",
        "tryParseLocation(bytes, seq++);",
        "",
        "// 修正後",
        "final bytes = extractFromServiceData(sd);",
        "final msgs = extractAllMessages(bytes!);",
        "for (final msg in msgs) {",
        "  tryParseUasId(msg);",
        "  tryParseLocation(msg, seq++);",
        "}",
    ], Inches(6.05), Inches(2.52), Inches(3.55), Inches(3.28), size=9)

    txb(sl, "この変更で対応できるケース",
        Inches(6.05), Inches(5.88), Inches(3.55), Inches(0.30),
        size=11, bold=True, color=C_BLACK)
    mline(sl, [
        "✓  Pi（単一メッセージ） — 従来通り動作",
        "✓  実機ドローン（Message Pack 3件） — 新たに対応",
        "✓  Pack の中の BasicID + Location を\n    同一ループで同時取得",
    ], Inches(6.05), Inches(6.22), Inches(3.55), Inches(1.22), size=11, color=C_TEXT, gap=6)

    # =========================================================================
    # PART 6: 準拠対応・検証・まとめ
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    part_divider(sl, 6, "準拠対応・検証・まとめ", "バグ修正・実機確認・送受信の対称性")
    pnum(sl, 31)

    # =========================================================================
    # 29. 発見したバグと修正（1/2）
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "準拠対応で発見したバグ — その 1", "ビット位置のずれが原因の 2 件", part="Part 6 — 準拠対応・検証")
    pnum(sl, 32)

    txb(sl,
        "最初の Flutter 実装は opendroneid-core-c の仕様と 4 箇所ずれていた。\n"
        "Pi 実機との通信テストで受信データのデコードがおかしいことに気づき、core-c ソースと突き合わせて特定した。",
        M, Inches(1.18), IW, Inches(0.80), size=13, color=C_TEXT)

    rect(sl, M, Inches(2.12), IW, Inches(2.22), C_BOX, border=True)
    txb(sl, "バグ ① — Location Byte 1 の Status ビット位置が逆だった",
        M+Inches(0.12), Inches(2.18), IW-Inches(0.24), Inches(0.35),
        size=13, bold=True, color=C_BLACK)
    code(sl, [
        "【修正前コメント】  Byte 1 : Status[3:0] | flags  ← Status が下位ニブル（LSB 側）",
        "【修正後・正しい仕様】 Byte 1 : Status[7:4] | flags  ← Status が上位ニブル（MSB 側）",
        "",
        "// 修正前（間違い）:",
        "final status = byte1 & 0x0F;         // 下位4bitを取り出していた",
        "// 修正後（正しい）:",
        "final status = (byte1 >> 4) & 0x0F;  // 上位4bitを取り出す",
    ], M+Inches(0.12), Inches(2.58), IW-Inches(0.24), Inches(1.60), size=10)

    rect(sl, M, Inches(4.48), IW, Inches(2.22), C_BOX, border=True)
    txb(sl, "バグ ② — AIRBORNE の定数値が違った",
        M+Inches(0.12), Inches(4.54), IW-Inches(0.24), Inches(0.35),
        size=13, bold=True, color=C_BLACK)
    code(sl, [
        "【修正前】  AIRBORNE = 1  （暗黙的に 1 としていた）",
        "【修正後】  AIRBORNE = 2  （opendroneid-core-c: GROUND=1, AIRBORNE=2）",
        "",
        "// Status 列挙値（opendroneid-core-c 準拠）:",
        "// UNDECLARED=0  GROUND=1  AIRBORNE=2  EMERGENCY=3  RC_LOST=4",
        "static const _statusAirborne = 2;  // 修正後",
        "statusIsAirborne: status == 2,      // 修正後のデコード",
    ], M+Inches(0.12), Inches(4.94), IW-Inches(0.24), Inches(1.60), size=10)

    txb(sl,
        "→ これらのバグがあると、AIRBORNE=2 を受信しても「飛行中でない」と判定してしまう。",
        M, H-Inches(0.42), IW, Inches(0.30), size=11, italic=True, color=C_SUB)

    # =========================================================================
    # 30. 発見したバグと修正（2/2）
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "準拠対応で発見したバグ — その 2", "ニブル順と未実装フィールドの 2 件", part="Part 6 — 準拠対応・検証")
    pnum(sl, 33)

    rect(sl, M, Inches(1.12), IW, Inches(2.22), C_BOX, border=True)
    txb(sl, "バグ ③ — BasicID Byte 1 のニブル順が逆だった",
        M+Inches(0.12), Inches(1.18), IW-Inches(0.24), Inches(0.35),
        size=13, bold=True, color=C_BLACK)
    code(sl, [
        "【修正前コメント】  Byte 1 : IDType[3:0] | UAType[7:4]  ← IDType が下位ニブル（間違い）",
        "【修正後・正しい仕様】 Byte 1 : (IDType << 4) | UAType  ← IDType が上位ニブル",
        "",
        "// IDType=1(Serial), UAType=2(Multirotor) の場合:",
        "// 誤: (2<<4)|1 = 0x21 → IDType=2(CAA), UAType=1(Aeroplane) と解釈されてしまう",
        "// 正: (1<<4)|2 = 0x12 → IDType=1(Serial), UAType=2(Multirotor) と正しく解釈",
    ], M+Inches(0.12), Inches(1.58), IW-Inches(0.24), Inches(1.60), size=10)

    rect(sl, M, Inches(3.48), IW, Inches(3.12), C_BOX, border=True)
    txb(sl, "バグ ④ — 方向・速度のデコードが未実装だった",
        M+Inches(0.12), Inches(3.54), IW-Inches(0.24), Inches(0.35),
        size=13, bold=True, color=C_BLACK)
    mline(sl, [
        "EWDirection フラグ（bit 1）と SpeedMult フラグ（bit 0）の存在を見落としており、",
        "方向・速度を単純に rawBytes[2], rawBytes[3] の値としてそのまま使っていた。",
    ], M+Inches(0.12), Inches(3.94), IW-Inches(0.24), Inches(0.55),
        size=12, color=C_TEXT, gap=3)
    code(sl, [
        "// 修正前（EWDirection / SpeedMult を無視）:",
        "direction: rawBytes[2].toDouble(),",
        "speedH:    rawBytes[3].toDouble(),",
        "",
        "// 修正後（フラグを読んでデコード）:",
        "direction: _decodeDirection(rawBytes[2] & 0xFF, ewDir),",
        "speedH:    _decodeSpeedH(rawBytes[3] & 0xFF, speedMult),",
        "speedV:    _decodeSpeedV(rawBytes[4] & 0xFF),   // int8 デコードも追加",
    ], M+Inches(0.12), Inches(4.55), IW-Inches(0.24), Inches(1.90), size=10)

    txb(sl, "修正後の最終構成（Pi ↔ Flutter 双方で一致）",
        M, Inches(6.72), IW, Inches(0.35), size=13, bold=True, color=C_BLACK)
    code(sl, [
        "Pi (remote_id.py)          Flutter (main.dart)",
        "Status 上位ニブル (7:4) ←→ (byte1 >> 4) & 0x0F",
        "AIRBORNE = 2            ←→ status == 2",
        "IDType 上位ニブル       ←→ (IDType << 4) | UAType",
        "EWDir / SpeedMult 実装  ←→ _decodeDirection / _decodeSpeedH",
    ], M, Inches(7.10), IW, Inches(1.28), size=10)

    # =========================================================================
    # 31. 送受信の完全対称性
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "送受信の完全対称性", "Pi エンコード ↔ Flutter デコード 全フィールド対応表", part="Part 6 — 準拠対応・検証")
    pnum(sl, 34)

    tbl(sl,
        ["フィールド", "Pi エンコード（Python）", "Flutter デコード（Dart）", "精度"],
        [
            ["緯度・経度",
             "round(deg × 1e7) → int32 LE\nstruct.pack('<...i', val)",
             "data.getInt32(N, Endian.little) / 1e7",
             "約 1 cm（1e-7 度）"],
            ["気圧高度",
             "round((alt+1000)/0.5) → uint16 LE\n0xFFFF = 不明",
             "getUint16(13) * 0.5 - 1000.0",
             "0.5 m"],
            ["GPS 高度",
             "同上（別フィールド alt_geo）",
             "getUint16(15) * 0.5 - 1000.0",
             "0.5 m"],
            ["水平速度",
             "(SpeedMult=0)→ raw = ms/0.25\n(SpeedMult=1)→ raw = (ms-63.75)/0.75",
             "(SpeedMult=0) raw×0.25\n(SpeedMult=1) raw×0.75",
             "0.25 m/s（低速域）\n0.75 m/s（高速域）"],
            ["垂直速度",
             "round(ms / 0.5) → int8",
             "raw≥128 → raw-256;  signed × 0.5",
             "0.5 m/s"],
            ["方向",
             "(EWDir=0) raw=deg\n(EWDir=1) raw=deg-180",
             "(EWDir=0) raw\n(EWDir=1) raw+180",
             "1°"],
            ["タイムスタンプ",
             "(unix_sec % 3600) × 10 → uint16 LE",
             "tsRaw÷10 + hourStart\n0xFFFF → 現在時刻",
             "0.1 秒"],
            ["Status",
             "AIRBORNE=2 を bits 7-4 に配置\nbyte1 = (2<<4)|flags = 0x20",
             "(byte1 >> 4) & 0x0F == 2\n→ statusIsAirborne = true",
             "離散値"],
            ["UAS_ID",
             "ASCII 20 bytes, 0x00 パディング\nstruct.pack('<...20s')",
             "sublist(2,22) → indexOf(0) → fromCharCodes",
             "20 文字 ASCII"],
        ],
        M, Inches(1.12), IW,
        cw=[Inches(1.45), Inches(2.55), Inches(2.60), Inches(2.30)], fs=9, rh=0.38)

    # =========================================================================
    # 32. まとめ
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr(sl, "まとめ", "OpenDroneID 実装で得た知見と設計のポイント", part="Part 6 — 準拠対応・検証")
    pnum(sl, 35)

    items = [
        ("規格の選択が互換性を決める",
         "AD type 0xFF → 0x16、UUID 0xFFFA への変更だけで、DJI・規制当局・受信アプリとの互換性が生まれた。"),
        ("Byte 1 のビット配置が最大の罠",
         "Status は上位ニブル（bits 7-4）。IDType も上位ニブル。逆にすると全て誤判定になる。"
         "opendroneid-core-c のソースを必ず参照すること。"),
        ("速度はデュアルスケール設計",
         "EWDirection・SpeedMult の 2 フラグで、方向と速度を 1 バイトずつに圧縮しつつ広い範囲をカバーする巧妙な設計。"),
        ("タイムスタンプは相対値で 2 バイトに収める",
         "(unix_sec % 3600) × 10 → uint16。受信側が現在の時間境界を足して Unix 秒を再構築する。"),
        ("高度は 2 種類持つ設計",
         "AltitudeBaro（BME280 QFE）と AltitudeGeo（GPS WGS84）を別フィールドに持つ。"
         "ZK 証明では QFE 高度を使い Pi とスマホの基準を統一する。"),
        ("withServices フィルターを使わない",
         "Pi は UUID Advertisement List（0x03）を送らないため Android のフィルターに引っかからない。"
         "全広告を受信して serviceData に 'fffa' が含まれるか手動検索する。"),
        ("Message Pack 対応で実機ドローンに繋がる",
         "市販ドローンは BasicID + Location + System を1パケットにまとめた Message Pack（type=0xF）で送信する。"
         "extractAllMessages() で Pack か否かを吸収し、呼び出し側のロジックを変えずに対応できる。"),
    ]

    for i, (title, body) in enumerate(items):
        y = Inches(1.12) + Inches(1.00) * i
        rect(sl, M, y, Inches(0.38), Inches(0.90), C_BLACK)
        txb(sl, str(i+1), M+Inches(0.04), y+Inches(0.18),
            Inches(0.30), Inches(0.45), size=20, bold=True,
            color=C_BG, align=PP_ALIGN.CENTER)
        txb(sl, title, M+Inches(0.50), y+Inches(0.04),
            IW-Inches(0.50), Inches(0.32), size=12, bold=True, color=C_BLACK)
        txb(sl, body, M+Inches(0.50), y+Inches(0.38),
            IW-Inches(0.50), Inches(0.52), size=11, color=C_TEXT)

    rect(sl, M, H-Inches(0.38), IW, Pt(1), C_RULE)
    txb(sl, "uav/remote_id.py  |  main.dart / UavTelemetryPacket  |  uav/OPENDRONEID_IMPLEMENTATION.md",
        M, H-Inches(0.32), IW, Inches(0.26), size=9, color=C_SUB, align=PP_ALIGN.CENTER)

    prs.save(str(OUTPUT_PATH))
    print(f"保存完了: {OUTPUT_PATH}  ({TOTAL} スライド)")


if __name__ == "__main__":
    build()
