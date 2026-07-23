"""
BLE リモートID 検知強化 変更説明 PowerPoint 生成スクリプト
4:3 / 20 スライド
"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
import copy

# ─── 定数 ────────────────────────────────────────────────────────────────────

W = Inches(10)      # 4:3 幅
H = Inches(7.5)     # 4:3 高さ

# カラーパレット
C_BG        = RGBColor(0x0A, 0x0F, 0x0D)   # 濃紺黒（背景）
C_BG2       = RGBColor(0x11, 0x1A, 0x17)   # カード背景
C_GREEN     = RGBColor(0x30, 0xD1, 0x58)   # アクセント緑
C_TEAL      = RGBColor(0x0B, 0x6E, 0x69)   # ティール
C_WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
C_WHITE54   = RGBColor(0xAA, 0xAA, 0xAA)
C_ORANGE    = RGBColor(0xFF, 0x95, 0x00)
C_RED       = RGBColor(0xFF, 0x3B, 0x30)
C_BLUE      = RGBColor(0x21, 0x96, 0xF3)
C_YELLOW    = RGBColor(0xFF, 0xD7, 0x40)
C_CODE_BG   = RGBColor(0x1E, 0x28, 0x24)
C_CODE_TEXT = RGBColor(0x80, 0xCB, 0xC4)

# ─── ヘルパー ─────────────────────────────────────────────────────────────────

def new_prs():
    prs = Presentation()
    prs.slide_width  = W
    prs.slide_height = H
    return prs

def blank_slide(prs):
    layout = prs.slide_layouts[6]   # completely blank
    return prs.slides.add_slide(layout)

def fill_bg(slide, color=C_BG):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color

def add_rect(slide, l, t, w, h, color, alpha=None):
    shape = slide.shapes.add_shape(1, l, t, w, h)  # MSO_SHAPE_TYPE.RECTANGLE
    shape.line.fill.background()
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    return shape

def add_text(slide, text, l, t, w, h,
             size=18, bold=False, color=C_WHITE,
             align=PP_ALIGN.LEFT, wrap=True, italic=False):
    txb = slide.shapes.add_textbox(l, t, w, h)
    tf  = txb.text_frame
    tf.word_wrap = wrap
    p   = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size  = Pt(size)
    run.font.bold  = bold
    run.font.color.rgb = color
    run.font.italic = italic
    return txb

def add_para(tf, text, size=14, bold=False, color=C_WHITE,
             align=PP_ALIGN.LEFT, italic=False, space_before=0):
    p = tf.add_paragraph()
    p.alignment = align
    p.space_before = Pt(space_before)
    run = p.add_run()
    run.text = text
    run.font.size  = Pt(size)
    run.font.bold  = bold
    run.font.color.rgb = color
    run.font.italic = italic
    return p

def slide_header(slide, title, subtitle=None):
    """上部グリーンバー＋タイトル"""
    add_rect(slide, 0, 0, W, Inches(0.08), C_GREEN)
    add_text(slide, title,
             Inches(0.4), Inches(0.15), Inches(9.2), Inches(0.7),
             size=24, bold=True, color=C_WHITE)
    if subtitle:
        add_text(slide, subtitle,
                 Inches(0.4), Inches(0.78), Inches(9.2), Inches(0.4),
                 size=13, color=C_WHITE54)
    # 下部ライン
    add_rect(slide, 0, Inches(7.3), W, Inches(0.04), C_TEAL)

def bullet_box(slide, items, l, t, w, h,
               icon="●", icon_color=C_GREEN,
               text_size=13, title=None, title_size=14):
    """箇条書きボックス"""
    box = add_rect(slide, l, t, w, h, C_BG2)
    txb = slide.shapes.add_textbox(l + Inches(0.15), t + Inches(0.1),
                                   w - Inches(0.3), h - Inches(0.2))
    tf = txb.text_frame
    tf.word_wrap = True
    first = True
    if title:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        run = p.add_run()
        run.text = title
        run.font.size = Pt(title_size)
        run.font.bold = True
        run.font.color.rgb = C_GREEN
    for item in items:
        p = tf.paragraphs[0] if (first and not title) else tf.add_paragraph()
        first = False
        p.space_before = Pt(2)
        run_icon = p.add_run()
        run_icon.text = icon + " "
        run_icon.font.size = Pt(text_size)
        run_icon.font.color.rgb = icon_color
        run_text = p.add_run()
        run_text.text = item
        run_text.font.size = Pt(text_size)
        run_text.font.color.rgb = C_WHITE

def code_box(slide, lines, l, t, w, h, title=None):
    """コード表示ボックス"""
    add_rect(slide, l, t, w, h, C_CODE_BG)
    add_rect(slide, l, t, Inches(0.04), h, C_TEAL)
    yoff = Inches(0.1)
    if title:
        add_text(slide, title,
                 l + Inches(0.1), t + yoff, w - Inches(0.2), Inches(0.3),
                 size=10, color=C_WHITE54, italic=True)
        yoff += Inches(0.28)
    txb = slide.shapes.add_textbox(
        l + Inches(0.1), t + yoff, w - Inches(0.2), h - yoff - Inches(0.1))
    tf = txb.text_frame
    tf.word_wrap = False
    first = True
    for line in lines:
        color = C_GREEN if line.startswith("# ") or line.startswith("//") \
                else (C_ORANGE if "def " in line or "class " in line or "static" in line
                      else C_CODE_TEXT)
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        run = p.add_run()
        run.text = line
        run.font.size = Pt(10)
        run.font.color.rgb = color

def tag(slide, label, l, t, color=C_GREEN):
    w = Inches(len(label) * 0.11 + 0.3)
    add_rect(slide, l, t, w, Inches(0.28), color)
    add_text(slide, label, l + Inches(0.08), t + Inches(0.04),
             w - Inches(0.16), Inches(0.22),
             size=10, bold=True, color=C_BG)
    return l + w + Inches(0.1)

def arrow(slide, x1, y, x2):
    """水平矢印"""
    line = slide.shapes.add_connector(1, x1, y, x2, y)
    line.line.color.rgb = C_GREEN
    line.line.width = Pt(1.5)


# ═══════════════════════════════════════════════════════════════════════════════
# スライド生成
# ═══════════════════════════════════════════════════════════════════════════════

prs = new_prs()

# ─────────────────────────────────────────────────────────────────────────────
# S01: タイトル
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)

# 背景グラデーション風装飾
add_rect(sl, 0, 0, W, Inches(3.5), RGBColor(0x0B, 0x20, 0x1A))
add_rect(sl, 0, 0, Inches(0.12), H, C_GREEN)
add_rect(sl, 0, Inches(7.3), W, Inches(0.2), C_TEAL)

add_text(sl, "BLE Remote ID 検知システム", Inches(0.4), Inches(0.8),
         Inches(9.2), Inches(1.0), size=32, bold=True, color=C_WHITE)
add_text(sl, "検知強化・可視化・安定化", Inches(0.4), Inches(1.75),
         Inches(9.2), Inches(0.6), size=20, color=C_GREEN, bold=True)
add_text(sl, "変更内容 詳細解説", Inches(0.4), Inches(2.35),
         Inches(9.2), Inches(0.5), size=16, color=C_WHITE54)

add_rect(sl, Inches(0.4), Inches(3.1), Inches(9.2), Inches(0.03), C_TEAL)

add_text(sl, "対象アプリ: rapidsnark_app (Flutter / Dart)",
         Inches(0.4), Inches(3.25), Inches(9.2), Inches(0.4),
         size=13, color=C_WHITE54)
add_text(sl, "変更ファイル数: 6  |  新規ファイル: 3  |  スライド枚数: 20",
         Inches(0.4), Inches(3.65), Inches(9.2), Inches(0.4),
         size=12, color=C_WHITE54)

for i, (label, col) in enumerate([
    ("検知パターン拡張", C_GREEN),
    ("BLE Raw 可視化", C_BLUE),
    ("スキャン安定化", C_ORANGE),
    ("ビルド修正", C_YELLOW),
]):
    x = Inches(0.4 + i * 2.35)
    add_rect(sl, x, Inches(4.5), Inches(2.1), Inches(0.8), col)
    add_text(sl, label, x + Inches(0.08), Inches(4.6),
             Inches(1.94), Inches(0.6), size=12, bold=True,
             color=C_BG, align=PP_ALIGN.CENTER)

# ─────────────────────────────────────────────────────────────────────────────
# S02: 目次
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "目次", "本資料で説明する4つのテーマ")

sections = [
    ("01", "背景と前提知識", "Remote ID / BLE / OpenDroneID とは", C_TEAL),
    ("02", "検知パターン拡張", "App Code 対応・複数メーカー対応", C_GREEN),
    ("03", "BLE Raw スキャナー", "未解析データの可視化機能", C_BLUE),
    ("04", "スキャン安定化", "Android レート制限の解消", C_ORANGE),
]
for i, (num, title, sub, col) in enumerate(sections):
    y = Inches(1.3 + i * 1.4)
    add_rect(sl, Inches(0.3), y, Inches(0.7), Inches(1.1), col)
    add_text(sl, num, Inches(0.3), y + Inches(0.25), Inches(0.7), Inches(0.6),
             size=22, bold=True, color=C_BG, align=PP_ALIGN.CENTER)
    add_rect(sl, Inches(1.1), y, Inches(8.5), Inches(1.1), C_BG2)
    add_text(sl, title, Inches(1.25), y + Inches(0.12),
             Inches(8.2), Inches(0.45), size=17, bold=True, color=C_WHITE)
    add_text(sl, sub, Inches(1.25), y + Inches(0.57),
             Inches(8.2), Inches(0.4), size=12, color=C_WHITE54)

# ─────────────────────────────────────────────────────────────────────────────
# S03: アプリ概要
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "アプリ概要", "rapidsnark_app とは何か")

add_text(sl, "UAV Safety ZK — ドローン安全証明アプリ",
         Inches(0.4), Inches(1.1), Inches(9.2), Inches(0.5),
         size=18, bold=True, color=C_GREEN)

bullet_box(sl, [
    "ドローン（UAV）の Remote ID 信号を BLE でリアルタイム受信",
    "受信した位置情報と自分の GPS 位置を比較して「接近」を証明",
    "ゼロ知識証明（ZK Proof）で位置情報を秘匿しながら証明生成",
    "カメラで映像を録画し、YOLO モデルでドローンを映像検出",
    "Flutter / Dart 製クロスプラットフォームアプリ（Android / iOS）",
], Inches(0.3), Inches(1.7), Inches(9.4), Inches(2.2))

add_rect(sl, Inches(0.3), Inches(4.05), Inches(9.4), Inches(0.03), C_TEAL)
add_text(sl, "本資料で説明する変更の対象範囲",
         Inches(0.3), Inches(4.1), Inches(9.4), Inches(0.4),
         size=13, bold=True, color=C_WHITE54)

for i, (label, detail) in enumerate([
    ("BLE 受信部", "Remote ID 信号の受信・解析"),
    ("可視化UI", "生データの確認画面"),
    ("スキャン管理", "Bluetooth スキャンの制御"),
]):
    x = Inches(0.3 + i * 3.17)
    add_rect(sl, x, Inches(4.6), Inches(3.0), Inches(0.9), C_BG2)
    add_text(sl, label, x + Inches(0.1), Inches(4.68),
             Inches(2.8), Inches(0.35), size=13, bold=True, color=C_GREEN)
    add_text(sl, detail, x + Inches(0.1), Inches(5.0),
             Inches(2.8), Inches(0.4), size=11, color=C_WHITE54)

# ─────────────────────────────────────────────────────────────────────────────
# S04: Remote ID とは
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "Remote ID とは？", "ドローンが義務として発信する識別信号")

add_text(sl, "📡  ドローン（UAV）が飛行中に自動的に発信する「電子プレート」",
         Inches(0.4), Inches(1.1), Inches(9.2), Inches(0.45),
         size=15, color=C_WHITE)

bullet_box(sl, [
    "機体の位置（緯度・経度・高度）",
    "速度・方向・飛行状態（離陸中 / 飛行中 / 着地中）",
    "UAS-ID（機体識別番号）",
    "オペレーター（操縦者）の位置情報",
], Inches(0.3), Inches(1.65), Inches(4.5), Inches(2.3),
   title="送信される情報", icon="▸")

bullet_box(sl, [
    "航空法改正により 2022年〜義務化（日本）",
    "国際規格: ASTM F3411-22a",
    "通信方式: BLE（Bluetooth） / Wi-Fi",
    "誰でも受信可能（一方向ブロードキャスト）",
], Inches(5.1), Inches(1.65), Inches(4.6), Inches(2.3),
   title="制度・規格", icon="▸")

add_rect(sl, Inches(0.3), Inches(4.1), Inches(9.4), Inches(2.8),
         RGBColor(0x0B, 0x20, 0x1A))
add_text(sl, "通信の流れ",
         Inches(0.5), Inches(4.18), Inches(9.0), Inches(0.35),
         size=12, bold=True, color=C_WHITE54)

for i, label in enumerate(["ドローン本体", "BLE 電波（0xFFFA）", "スマートフォン", "アプリ（解析）"]):
    x = Inches(0.5 + i * 2.35)
    col = C_GREEN if i == 0 else (C_BLUE if i == 2 else C_TEAL)
    if i % 2 == 1:
        add_text(sl, "→→→", x, Inches(4.75),
                 Inches(2.0), Inches(0.5), size=14, color=col,
                 align=PP_ALIGN.CENTER)
        add_text(sl, label, x, Inches(5.15),
                 Inches(2.0), Inches(0.35), size=9, color=C_WHITE54,
                 align=PP_ALIGN.CENTER)
    else:
        add_rect(sl, x, Inches(4.62), Inches(1.8), Inches(0.8), C_BG2)
        add_text(sl, label, x + Inches(0.05), Inches(4.75),
                 Inches(1.7), Inches(0.55), size=11, bold=True, color=col,
                 align=PP_ALIGN.CENTER)

# ─────────────────────────────────────────────────────────────────────────────
# S05: BLE と OpenDroneID
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "BLE と OpenDroneID 規格", "通信方式とメッセージ構造の基礎")

add_text(sl, "BLE（Bluetooth Low Energy）",
         Inches(0.4), Inches(1.1), Inches(4.5), Inches(0.4),
         size=16, bold=True, color=C_GREEN)
bullet_box(sl, [
    "低消費電力の近距離無線通信",
    "接続不要でブロードキャスト送信",
    "受信側は周囲全機を同時に検知可能",
    "スキャン = パッシブ受信（接続しない）",
], Inches(0.3), Inches(1.55), Inches(4.5), Inches(2.2))

add_text(sl, "OpenDroneID メッセージ種別",
         Inches(5.1), Inches(1.1), Inches(4.6), Inches(0.4),
         size=16, bold=True, color=C_BLUE)

msg_types = [
    ("Type 0", "BasicID",     "機体 UAS-ID", C_GREEN),
    ("Type 1", "Location",    "位置・速度・高度", C_BLUE),
    ("Type 4", "System",      "オペレーター位置", C_ORANGE),
    ("Type F", "MessagePack", "複数メッセージ束", C_TEAL),
]
for i, (t, name, desc, col) in enumerate(msg_types):
    y = Inches(1.55 + i * 0.55)
    add_rect(sl, Inches(5.1), y, Inches(4.6), Inches(0.48), C_BG2)
    add_text(sl, t, Inches(5.2), y + Inches(0.08),
             Inches(0.9), Inches(0.32), size=10, bold=True, color=col)
    add_text(sl, name, Inches(6.1), y + Inches(0.08),
             Inches(1.5), Inches(0.32), size=11, bold=True, color=C_WHITE)
    add_text(sl, desc, Inches(7.7), y + Inches(0.08),
             Inches(1.8), Inches(0.32), size=10, color=C_WHITE54)

add_rect(sl, Inches(0.3), Inches(3.9), Inches(9.4), Inches(0.03), C_TEAL)
add_text(sl, "Location メッセージ 25バイト構造（ASTM F3411-22a）",
         Inches(0.3), Inches(4.0), Inches(9.4), Inches(0.35),
         size=13, bold=True, color=C_WHITE54)

fields = [
    ("Byte0", "Type|Proto", C_GREEN),
    ("Byte1", "Status|Flags", C_BLUE),
    ("Byte2-4", "Dir/Speed", C_ORANGE),
    ("Byte5-12", "Lat/Lon", C_GREEN),
    ("Byte13-18", "Alt/Height", C_BLUE),
    ("Byte19-24", "Acc/TS", C_WHITE54),
]
total_w = Inches(9.4)
widths = [0.9, 1.1, 1.0, 1.5, 1.6, 1.4]
x = Inches(0.3)
for j, ((label, desc, col), w_f) in enumerate(zip(fields, widths)):
    bw = Inches(w_f)
    add_rect(sl, x, Inches(4.45), bw - Inches(0.04), Inches(0.6), col)
    add_text(sl, label, x + Inches(0.04), Inches(4.5),
             bw - Inches(0.08), Inches(0.22), size=8, bold=True, color=C_BG)
    add_text(sl, desc, x + Inches(0.04), Inches(4.7),
             bw - Inches(0.08), Inches(0.22), size=8, color=C_BG)
    x += bw

add_text(sl, "✓ このパケット構造を解析してドローンの位置情報を取得する",
         Inches(0.3), Inches(5.25), Inches(9.4), Inches(0.4),
         size=12, color=C_GREEN)

# ─────────────────────────────────────────────────────────────────────────────
# S06: 変更前の問題点
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "変更前の問題点", "何が検知できていなかったか")

add_text(sl, "変更前に対応していたパターン（2種類のみ）",
         Inches(0.4), Inches(1.1), Inches(9.2), Inches(0.4),
         size=15, bold=True, color=C_WHITE)

for i, (title, detail) in enumerate([
    ("OpenDroneID 標準",  "BLE Service UUID 0xFFFA の Service Data"),
    ("DJI 旧機種のみ",    "Manufacturer Data の Company ID 0x2005 のみ"),
]):
    x = Inches(0.3 + i * 4.85)
    add_rect(sl, x, Inches(1.6), Inches(4.6), Inches(0.85), C_BG2)
    add_text(sl, "✓ " + title, x + Inches(0.1), Inches(1.68),
             Inches(4.4), Inches(0.38), size=13, bold=True, color=C_GREEN)
    add_text(sl, detail, x + Inches(0.1), Inches(2.02),
             Inches(4.4), Inches(0.35), size=11, color=C_WHITE54)

add_rect(sl, Inches(0.3), Inches(2.65), Inches(9.4), Inches(0.03), C_RED)
add_text(sl, "❌  検知できていなかったケース",
         Inches(0.3), Inches(2.75), Inches(9.4), Inches(0.4),
         size=15, bold=True, color=C_RED)

problems = [
    ("App Code プレフィックス付きデータ",
     "opendroneid-core-c 実装が先頭に 0x0D を付加する場合、\n先頭バイトをメッセージタイプと誤解釈し解析失敗"),
    ("DJI 新ファーム / Parrot / Autel / Skydio",
     "Company ID が 0x2005 以外のメーカーは\n完全に無視されていた"),
    ("未知データの確認手段がない",
     "何らかの BLE 信号が来ても、解析に失敗すると\nユーザーが内容を確認する方法がなかった"),
]
for i, (t, d) in enumerate(problems):
    y = Inches(3.25 + i * 1.1)
    add_rect(sl, Inches(0.3), y, Inches(0.5), Inches(0.95), C_RED)
    add_text(sl, str(i+1), Inches(0.3), y + Inches(0.25),
             Inches(0.5), Inches(0.45), size=18, bold=True, color=C_WHITE,
             align=PP_ALIGN.CENTER)
    add_rect(sl, Inches(0.85), y, Inches(8.85), Inches(0.95), C_BG2)
    add_text(sl, t, Inches(0.98), y + Inches(0.1),
             Inches(8.6), Inches(0.35), size=13, bold=True, color=C_WHITE)
    add_text(sl, d, Inches(0.98), y + Inches(0.45),
             Inches(8.6), Inches(0.45), size=11, color=C_WHITE54)

# ─────────────────────────────────────────────────────────────────────────────
# S07: 変更①概要
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "変更① 検知パターン拡張 — 概要",
             "lib/domain/uav_telemetry.dart の extractFromServiceData / extractFromManufacturerData")

add_text(sl, "2つの改善を実施",
         Inches(0.4), Inches(1.1), Inches(9.2), Inches(0.4),
         size=15, bold=True, color=C_WHITE)

# 改善1
add_rect(sl, Inches(0.3), Inches(1.6), Inches(0.08), Inches(2.0), C_GREEN)
add_text(sl, "改善 A  |  App Code (0x0D) プレフィックスの除去",
         Inches(0.5), Inches(1.65), Inches(9.1), Inches(0.4),
         size=14, bold=True, color=C_GREEN)
bullet_box(sl, [
    "opendroneid-core-c（オープンソース実装）は Service Data の先頭に 0x0D を付加",
    "変更前: 0x0D をメッセージタイプとして誤解析 → 解析失敗",
    "変更後: 先頭が 0x0D なら除去してから解析 → 正常に動作",
], Inches(0.5), Inches(2.1), Inches(9.1), Inches(1.35))

add_rect(sl, Inches(0.3), Inches(3.55), Inches(0.08), Inches(2.0), C_BLUE)
add_text(sl, "改善 B  |  対応メーカーの拡張",
         Inches(0.5), Inches(3.6), Inches(9.1), Inches(0.4),
         size=14, bold=True, color=C_BLUE)

makers = [
    ("0x2005", "DJI (旧機種)", "既存", C_WHITE54),
    ("0x2006", "DJI (新ファーム)", "追加", C_GREEN),
    ("0x0043", "Parrot", "追加", C_GREEN),
    ("0x0417", "Autel Robotics", "追加", C_GREEN),
    ("0x06D6", "Skydio", "追加", C_GREEN),
]
for i, (cid, name, status, col) in enumerate(makers):
    x = Inches(0.5 + i * 1.88)
    add_rect(sl, x, Inches(4.1), Inches(1.78), Inches(1.0), C_BG2)
    add_text(sl, cid, x + Inches(0.08), Inches(4.17),
             Inches(1.62), Inches(0.3), size=10, color=C_CODE_TEXT,
             bold=True)
    add_text(sl, name, x + Inches(0.08), Inches(4.45),
             Inches(1.62), Inches(0.3), size=11, color=C_WHITE)
    add_rect(sl, x + Inches(0.08), Inches(4.78), Inches(0.5), Inches(0.2), col)
    add_text(sl, status, x + Inches(0.08), Inches(4.78),
             Inches(0.5), Inches(0.2), size=9, bold=True, color=C_BG,
             align=PP_ALIGN.CENTER)

# ─────────────────────────────────────────────────────────────────────────────
# S08: App Code の実装詳細
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "変更① — App Code 対応の実装",
             "extractFromServiceData() の変更詳細")

add_text(sl, "変更前",
         Inches(0.3), Inches(1.1), Inches(4.5), Inches(0.35),
         size=13, bold=True, color=C_RED)
code_box(sl, [
    "static List<int>? extractFromServiceData(",
    "    Map<dynamic, List<int>> serviceData) {",
    "  for (final entry in serviceData.entries) {",
    "    final key = entry.key.toString().toLowerCase();",
    "    // 0xFFFA を含む UUID を探してそのまま返す",
    "    if (key.contains('fffa')) return entry.value;",
    "    // ↑ 先頭が 0x0D でも気にせず返していた",
    "  }",
    "  return null;",
    "}",
], Inches(0.3), Inches(1.5), Inches(4.5), Inches(2.5))

add_text(sl, "変更後",
         Inches(5.2), Inches(1.1), Inches(4.5), Inches(0.35),
         size=13, bold=True, color=C_GREEN)
code_box(sl, [
    "static const _odidAppCode = 0x0D;",
    "",
    "static List<int>? extractFromServiceData(",
    "    Map<dynamic, List<int>> serviceData) {",
    "  for (final entry in serviceData.entries) {",
    "    final key = entry.key.toString().toLowerCase();",
    "    if (!key.contains('fffa')) continue;",
    "    final raw = entry.value;",
    "    if (raw.isEmpty) continue;",
    "    // 0x0D があれば除去してから返す",
    "    if (raw[0] == _odidAppCode && raw.length > 1)",
    "      return raw.sublist(1);",
    "    return raw;",
    "  }",
    "  return null;",
    "}",
], Inches(5.2), Inches(1.5), Inches(4.5), Inches(3.5))

add_text(sl, "データの流れ（変更後）",
         Inches(0.3), Inches(4.15), Inches(4.5), Inches(0.35),
         size=11, bold=True, color=C_WHITE54)

steps = [
    ("[0x0D][0x10][..25B..]", "受信データ"),
    "→",
    "[0x10][..25B..]",
    "→",
    "Location解析OK",
]
x = Inches(0.3)
for s in steps:
    if s == "→":
        add_text(sl, "→", x, Inches(4.55), Inches(0.4), Inches(0.4),
                 size=14, color=C_GREEN, align=PP_ALIGN.CENTER)
        x += Inches(0.4)
    else:
        if isinstance(s, tuple):
            txt, sub = s
        else:
            txt, sub = s, ""
        bw = Inches(1.8) if "[0x0D]" in txt else Inches(1.5)
        add_rect(sl, x, Inches(4.5), bw, Inches(0.45), C_BG2)
        add_text(sl, txt, x + Inches(0.05), Inches(4.55),
                 bw - Inches(0.1), Inches(0.35), size=9, color=C_CODE_TEXT)
        x += bw + Inches(0.05)

# ─────────────────────────────────────────────────────────────────────────────
# S09: メーカー拡張の実装詳細
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "変更① — 複数メーカー対応の実装",
             "extractFromManufacturerData() の変更詳細")

add_text(sl, "変更前（DJI 1社のみ固定値チェック）",
         Inches(0.3), Inches(1.1), Inches(4.5), Inches(0.35),
         size=13, bold=True, color=C_RED)
code_box(sl, [
    "// 1社しか対応できない定数",
    "static const _djiLegacyCompanyId = 0x2005;",
    "",
    "static List<int>? extractFromManufacturerData(",
    "    Map<int, List<int>> manufacturerData) {",
    "  // DJI 旧機種だけチェック",
    "  final payload = manufacturerData[_djiLegacyCompanyId];",
    "  if (payload != null && payload.isNotEmpty)",
    "    return payload;",
    "  return null;",
    "}",
], Inches(0.3), Inches(1.5), Inches(4.5), Inches(2.8))

add_text(sl, "変更後（マップで複数メーカーをループ）",
         Inches(5.2), Inches(1.1), Inches(4.5), Inches(0.35),
         size=13, bold=True, color=C_GREEN)
code_box(sl, [
    "// 拡張可能なマップで管理",
    "static const _knownManufacturerIds = <int, String>{",
    "  0x2005: 'DJI (legacy)',",
    "  0x2006: 'DJI',",
    "  0x0043: 'Parrot',",
    "  0x0417: 'Autel Robotics',",
    "  0x06D6: 'Skydio',",
    "};",
    "",
    "static List<int>? extractFromManufacturerData(",
    "    Map<int, List<int>> manufacturerData) {",
    "  for (final id in _knownManufacturerIds.keys) {",
    "    final raw = manufacturerData[id];",
    "    if (raw == null || raw.isEmpty) continue;",
    "    // 0x0D App Code も除去",
    "    if (raw[0] == _odidAppCode && raw.length > 1)",
    "      return raw.sublist(1);",
    "    return raw;",
    "  }",
    "  return null;",
    "}",
], Inches(5.2), Inches(1.5), Inches(4.5), Inches(4.8))

add_text(sl, "✓ 新しいメーカーへの対応は マップに1行追加するだけ",
         Inches(0.3), Inches(5.55), Inches(4.5), Inches(0.4),
         size=12, color=C_GREEN)

# ─────────────────────────────────────────────────────────────────────────────
# S10: BLE Raw スキャナー概要
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "変更② BLE Raw スキャナー — 概要",
             "解析できなかったデータも全て確認できる新機能")

add_text(sl, "なぜ必要か？",
         Inches(0.4), Inches(1.15), Inches(9.2), Inches(0.4),
         size=15, bold=True, color=C_ORANGE)
bullet_box(sl, [
    "近くで BLE 信号を受信しているのに Remote ID として認識されない場合がある",
    "従来は「解析失敗 = 何も見えない」状態で原因が調査できなかった",
    "生バイト列を見ることで「規格違反・フォーマット差異・別メーカー」を特定できる",
], Inches(0.3), Inches(1.6), Inches(9.4), Inches(1.5))

add_text(sl, "新機能で可能になること",
         Inches(0.4), Inches(3.2), Inches(9.2), Inches(0.4),
         size=15, bold=True, color=C_GREEN)

features = [
    ("全 BLE デバイス表示", "解析成功・失敗問わず周囲の全デバイスを一覧"),
    ("Hex Dump 表示", "16バイト区切り＋ASCII列でデータを可視化"),
    ("診断メッセージ", "解析失敗した具体的な理由を日本語で表示"),
    ("クリップボードコピー", "hex データを長押しでコピーして外部調査可能"),
]
for i, (title, desc) in enumerate(features):
    x = Inches(0.3 + (i % 2) * 4.85)
    y = Inches(3.7 + (i // 2) * 1.3)
    add_rect(sl, x, y, Inches(4.6), Inches(1.1), C_BG2)
    add_rect(sl, x, y, Inches(0.06), Inches(1.1), C_GREEN)
    add_text(sl, title, x + Inches(0.15), y + Inches(0.1),
             Inches(4.3), Inches(0.38), size=13, bold=True, color=C_GREEN)
    add_text(sl, desc, x + Inches(0.15), y + Inches(0.5),
             Inches(4.3), Inches(0.5), size=11, color=C_WHITE54)

# ─────────────────────────────────────────────────────────────────────────────
# S11: 新規ファイルとデータモデル
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "変更② — 新規ファイルとデータモデル",
             "追加した3つのファイルの役割")

files = [
    ("lib/domain/raw_ble_device.dart",
     "データモデル",
     "BLE デバイスの生広告データを保持するクラス。\nデバイスID・名前・RSSI・UUID・ServiceData・\nManufacturerData・受信日時を格納。",
     C_GREEN),
    ("lib/providers/raw_ble_provider.dart",
     "状態管理",
     "Riverpod Notifier。BleService の rawResults\nストリームを購読し、最新50件を RSSI 降順\nで保持・更新する。",
     C_BLUE),
    ("lib/features/ble_raw_scan/\nble_raw_scan_page.dart",
     "UI",
     "BLE Raw タブの画面実装。デバイス一覧・\nhex dump・診断ボックスを描画する\nConsumerWidget。",
     C_ORANGE),
]
for i, (path, role, desc, col) in enumerate(files):
    y = Inches(1.3 + i * 1.85)
    add_rect(sl, Inches(0.3), y, Inches(9.4), Inches(1.7), C_BG2)
    add_rect(sl, Inches(0.3), y, Inches(0.07), Inches(1.7), col)
    add_text(sl, path, Inches(0.5), y + Inches(0.1),
             Inches(6.0), Inches(0.4), size=11, color=C_CODE_TEXT, bold=True)
    add_rect(sl, Inches(6.7), y + Inches(0.08), Inches(1.0), Inches(0.3), col)
    add_text(sl, role, Inches(6.7), y + Inches(0.08),
             Inches(1.0), Inches(0.3), size=10, bold=True, color=C_BG,
             align=PP_ALIGN.CENTER)
    add_text(sl, desc, Inches(0.5), y + Inches(0.55),
             Inches(8.7), Inches(1.05), size=11, color=C_WHITE54)

# ─────────────────────────────────────────────────────────────────────────────
# S12: RawBleDevice クラス詳細
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "変更② — RawBleDevice データモデル詳細",
             "lib/domain/raw_ble_device.dart")

add_text(sl, "クラス構造",
         Inches(0.4), Inches(1.1), Inches(4.6), Inches(0.35),
         size=14, bold=True, color=C_WHITE54)
code_box(sl, [
    "class RawBleDevice {",
    "  final String deviceId;        // MAC / iOS UUID",
    "  final String deviceName;      // 広告名",
    "  final int rssi;               // 電波強度 (dBm)",
    "  final List<String> serviceUuids;  // UUID リスト",
    "  final Map<String, List<int>> serviceData;",
    "  final Map<int, List<int>> manufacturerData;",
    "  final DateTime receivedAt;    // 受信日時",
    "  final List<int>? odidPayload; // null = 未解析",
    "",
    "  bool get isOdid => odidPayload != null;",
    "}",
], Inches(0.3), Inches(1.5), Inches(4.6), Inches(3.2))

add_text(sl, "ポイント",
         Inches(5.2), Inches(1.1), Inches(4.5), Inches(0.35),
         size=14, bold=True, color=C_WHITE54)
bullet_box(sl, [
    "odidPayload が null = 解析不可\nnull でない = Remote ID として解析成功",
    "isOdid ゲッターで UI が\n簡単に色分け表示できる",
    "fromScanResult() で flutter_blue_plus の\nScanResult から直接変換",
    "serviceData のキーは小文字に統一\n（UUID の大小文字ゆれ対策）",
], Inches(5.2), Inches(1.5), Inches(4.5), Inches(3.5))

add_text(sl, "ユーティリティ関数（同ファイル内）",
         Inches(0.3), Inches(4.85), Inches(9.4), Inches(0.35),
         size=12, bold=True, color=C_WHITE54)
code_box(sl, [
    "// bytes → '0A 1B 2C ...' 形式",
    "String bytesToHex(List<int> bytes) => ...",
    "",
    "// Company ID → ブランド名（例: 0x0043 → 'Parrot'）",
    "String companyIdLabel(int id) => ...",
], Inches(0.3), Inches(5.25), Inches(9.4), Inches(1.5))

# ─────────────────────────────────────────────────────────────────────────────
# S13: UI 画面構成
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "変更② — BLE Raw スキャン画面の構成",
             "ble_raw_scan_page.dart の UI 設計")

add_text(sl, "画面レイアウト（モック）",
         Inches(0.3), Inches(1.1), Inches(3.8), Inches(0.35),
         size=13, bold=True, color=C_WHITE54)

# モック画面
add_rect(sl, Inches(0.3), Inches(1.5), Inches(3.5), Inches(5.6), C_BG2)
add_rect(sl, Inches(0.3), Inches(1.5), Inches(3.5), Inches(0.5), C_TEAL)
add_text(sl, "BLE Raw Scan     [クリア]",
         Inches(0.35), Inches(1.55), Inches(3.4), Inches(0.38),
         size=10, bold=True, color=C_WHITE)

for j, (name, tag_col, tag_text) in enumerate([
    ("DJI-ABCD", C_GREEN, "Remote ID"),
    ("Unknown-1122", C_WHITE54, "Unknown"),
    ("Unknown-3344", C_WHITE54, "Unknown"),
]):
    y = Inches(2.1 + j * 1.5)
    add_rect(sl, Inches(0.35), y, Inches(3.4), Inches(1.35), C_CODE_BG)
    add_rect(sl, Inches(0.35), y, Inches(3.4), Inches(0.04), tag_col)
    add_text(sl, name, Inches(0.5), y + Inches(0.1),
             Inches(3.1), Inches(0.32), size=10, bold=True, color=C_WHITE)
    add_rect(sl, Inches(0.5), y + Inches(0.45),
             Inches(1.0), Inches(0.22), tag_col)
    add_text(sl, tag_text, Inches(0.5), y + Inches(0.45),
             Inches(1.0), Inches(0.22), size=8, bold=True, color=C_BG,
             align=PP_ALIGN.CENTER)
    add_text(sl, "-45 dBm  AA:BB:CC", Inches(1.6), y + Inches(0.45),
             Inches(2.0), Inches(0.22), size=8, color=C_WHITE54)
    add_text(sl, "▼ タップして展開",
             Inches(0.5), y + Inches(0.82), Inches(3.0), Inches(0.35),
             size=8, color=C_WHITE54)

add_text(sl, "各コンポーネントの説明",
         Inches(4.1), Inches(1.1), Inches(5.6), Inches(0.35),
         size=13, bold=True, color=C_WHITE54)

components = [
    ("デバイスカード", "_DeviceCard",
     "各BLEデバイス1件を表示するウィジェット。\nタップで詳細を展開（ExpansionTile）"),
    ("タグ表示", "_Tag",
     "Remote ID（緑）/ Unknown（グレー）/ \nDrone（青）を色分けで表示"),
    ("Hex Dump", "_HexDump",
     "16バイト区切り＋ASCII列。\n長押しでクリップボードにコピー"),
    ("診断ボックス", "_OdidSummary\n_UnknownDataDiag",
     "解析結果または失敗理由を表示。\n成功は緑・失敗はオレンジ"),
]
for i, (name, cls, desc) in enumerate(components):
    y = Inches(1.55 + i * 1.35)
    add_rect(sl, Inches(4.1), y, Inches(5.6), Inches(1.2), C_BG2)
    add_text(sl, name, Inches(4.25), y + Inches(0.1),
             Inches(2.5), Inches(0.35), size=13, bold=True, color=C_WHITE)
    add_text(sl, cls, Inches(6.85), y + Inches(0.1),
             Inches(2.7), Inches(0.35), size=10, color=C_CODE_TEXT, italic=True)
    add_text(sl, desc, Inches(4.25), y + Inches(0.5),
             Inches(5.3), Inches(0.6), size=11, color=C_WHITE54)

# ─────────────────────────────────────────────────────────────────────────────
# S14: 診断ボックスの詳細
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "変更② — 診断ボックスの詳細",
             "解析成功・失敗の両方を詳細に表示")

add_text(sl, "■  解析成功の場合（緑ボックス）",
         Inches(0.3), Inches(1.1), Inches(9.4), Inches(0.35),
         size=14, bold=True, color=C_GREEN)
code_box(sl, [
    "✓ App Code (0x0D) 検出 → 除去して解析",
    "✓ [Type 1  Proto 0  25B] Location",
    "    35.689500, 139.691700",
    "    Alt(baro)=42.0m  Alt(geo)=43.5m",
    "    SpeedH=2.5m/s  SpeedV=0.0m/s",
    "    Dir=180°  AIRBORNE",
    "✓ [Type 0  Proto 0  25B] BasicID: JPN-DJI-12345678",
], Inches(0.3), Inches(1.52), Inches(9.4), Inches(2.0),
   title="")

add_text(sl, "■  解析失敗の場合（オレンジボックス）",
         Inches(0.3), Inches(3.65), Inches(9.4), Inches(0.35),
         size=14, bold=True, color=C_ORANGE)
code_box(sl, [
    "✗ [Type 1  Proto 0  20B] Location: バイト数不足 (20/25)",
    "✗ [Type 1  Proto 0  25B] Location: 座標がゼロ（未設定）",
    "? [Type 6  Proto 2  25B] 未知タイプ",
    "⚠ OpenDroneID 形式の可能性あり（UUID が 0xFFFA 以外）",
    'ASCII: "DJI..."',
    "バイト数: 18  先頭: 0x10",
], Inches(0.3), Inches(4.07), Inches(9.4), Inches(1.85))

add_text(sl, "失敗パターンと原因の対応表",
         Inches(0.3), Inches(6.05), Inches(9.4), Inches(0.3),
         size=11, bold=True, color=C_WHITE54)

for i, (pattern, cause) in enumerate([
    ("バイト数不足", "途中で途切れたパケット"),
    ("座標がゼロ", "GPSが未取得の状態で送信"),
    ("未知タイプ", "規格外 / 将来の拡張タイプ"),
]):
    x = Inches(0.3 + i * 3.15)
    add_rect(sl, x, Inches(6.4), Inches(3.0), Inches(0.7), C_BG2)
    add_text(sl, pattern, x + Inches(0.1), Inches(6.47),
             Inches(2.8), Inches(0.28), size=11, bold=True, color=C_ORANGE)
    add_text(sl, cause, x + Inches(0.1), Inches(6.73),
             Inches(2.8), Inches(0.28), size=10, color=C_WHITE54)

# ─────────────────────────────────────────────────────────────────────────────
# S15: Hex Dump 表示
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "変更② — Hex Dump 表示の詳細",
             "Wireshark 形式の16バイト区切り表示")

add_text(sl, "表示形式",
         Inches(0.3), Inches(1.1), Inches(9.4), Inches(0.35),
         size=14, bold=True, color=C_WHITE54)
code_box(sl, [
    "オフセット  ←── 16バイトの HEX ──→           ← ASCII →",
    "0000  FA FF 10 00 6F 21 43 01  B4 7E 53 08 92 54 7A 01  ....o!C..~S..Tz.",
    "0010  64 01 00 00 FF FF FF FF  00 00 00 00 00            d............",
], Inches(0.3), Inches(1.5), Inches(9.4), Inches(1.5))

add_text(sl, "各部の意味",
         Inches(0.3), Inches(3.1), Inches(9.4), Inches(0.35),
         size=14, bold=True, color=C_WHITE54)

parts = [
    ("0000, 0010", "オフセット\n（バイト位置）", C_YELLOW),
    ("FA FF 10 00...", "16進数\n（実際のデータ）", C_CODE_TEXT),
    ("....o!C..", "ASCII表示\n（可読文字は文字・不可は '.'）", C_GREEN),
]
for i, (ex, desc, col) in enumerate(parts):
    x = Inches(0.3 + i * 3.15)
    add_rect(sl, x, Inches(3.5), Inches(3.0), Inches(1.5), C_BG2)
    add_rect(sl, x, Inches(3.5), Inches(3.0), Inches(0.06), col)
    add_text(sl, ex, x + Inches(0.1), Inches(3.6),
             Inches(2.8), Inches(0.55), size=11, color=col, bold=True)
    add_text(sl, desc, x + Inches(0.1), Inches(4.18),
             Inches(2.8), Inches(0.7), size=11, color=C_WHITE54)

add_text(sl, "実装コード（_HexDump._format）",
         Inches(0.3), Inches(5.1), Inches(9.4), Inches(0.35),
         size=12, bold=True, color=C_WHITE54)
code_box(sl, [
    "static String _format(List<int> bytes) {",
    "  const cols = 16;",
    "  for (var i = 0; i < bytes.length; i += cols) {",
    "    final chunk  = bytes.sublist(i, min(i+cols, bytes.length));",
    "    final offset = i.toRadixString(16).padLeft(4,'0').toUpperCase();",
    "    final hex    = chunk.map((b) => b.toRadixString(16)...).join(' ');",
    "    final ascii  = chunk.map((b) => b >= 0x20 && b < 0x7F",
    "                     ? String.fromCharCode(b) : '.').join();",
    "    buf.writeln('$offset  ${hexPadded}  $ascii');",
    "  }",
    "}",
], Inches(0.3), Inches(5.5), Inches(9.4), Inches(1.8))

# ─────────────────────────────────────────────────────────────────────────────
# S16: スキャン問題の説明
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "変更③ BLE スキャン安定化 — 問題の説明",
             "Android の BLE レート制限とその原因")

add_text(sl, "発生したエラー",
         Inches(0.3), Inches(1.1), Inches(9.4), Inches(0.35),
         size=14, bold=True, color=C_RED)
code_box(sl, [
    "E/BluetoothLeScanner: onScannerRegistered(status=6, scannerId=-1):",
    "  Failed. App is scanning too frequently",
    "E/BluetoothLeScanner: stopLeScan(): Error state, mScannerId=0",
], Inches(0.3), Inches(1.5), Inches(9.4), Inches(1.2))

add_text(sl, "Android BLE レート制限",
         Inches(0.3), Inches(2.85), Inches(9.4), Inches(0.35),
         size=14, bold=True, color=C_ORANGE)
bullet_box(sl, [
    "Android 7.0（API 24）以降に搭載された保護機能",
    "30秒以内に5回を超えて startScan() を呼ぶとブロックされる",
    "バックグラウンドでは制限がさらに厳しい",
], Inches(0.3), Inches(3.25), Inches(9.4), Inches(1.4))

add_text(sl, "なぜ制限に引っかかったか（変更前の構造）",
         Inches(0.3), Inches(4.75), Inches(9.4), Inches(0.35),
         size=14, bold=True, color=C_WHITE54)

add_rect(sl, Inches(0.3), Inches(5.15), Inches(4.4), Inches(1.5), C_BG2)
add_text(sl, "BleService\n（ODID 解析用）",
         Inches(0.4), Inches(5.25), Inches(4.2), Inches(0.7),
         size=12, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
add_rect(sl, Inches(0.9), Inches(5.9), Inches(3.2), Inches(0.35), C_RED)
add_text(sl, "startScan() 独自管理",
         Inches(0.9), Inches(5.9), Inches(3.2), Inches(0.35),
         size=10, color=C_WHITE, align=PP_ALIGN.CENTER)

add_rect(sl, Inches(5.3), Inches(5.15), Inches(4.4), Inches(1.5), C_BG2)
add_text(sl, "RawBleNotifier\n（BLE Raw 表示用）",
         Inches(5.4), Inches(5.25), Inches(4.2), Inches(0.7),
         size=12, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
add_rect(sl, Inches(5.8), Inches(5.9), Inches(3.2), Inches(0.35), C_RED)
add_text(sl, "startScan() 独自管理",
         Inches(5.8), Inches(5.9), Inches(3.2), Inches(0.35),
         size=10, color=C_WHITE, align=PP_ALIGN.CENTER)

add_text(sl, "⬆  2つが独立してスキャンを管理 → start/stop が頻発 → 制限に抵触",
         Inches(0.3), Inches(6.8), Inches(9.4), Inches(0.4),
         size=12, color=C_RED, bold=True)

# ─────────────────────────────────────────────────────────────────────────────
# S17: スキャン修正後のアーキテクチャ
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "変更③ — 修正後のアーキテクチャ",
             "スキャンを BleService に集約・rawResults ストリームを共有")

add_text(sl, "修正後の構造",
         Inches(0.3), Inches(1.1), Inches(9.4), Inches(0.35),
         size=14, bold=True, color=C_WHITE54)

# 中央 BleService ボックス
add_rect(sl, Inches(3.2), Inches(1.55), Inches(3.6), Inches(2.5), C_TEAL)
add_text(sl, "BleService",
         Inches(3.2), Inches(1.65), Inches(3.6), Inches(0.5),
         size=16, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
add_text(sl, "（スキャン管理 1本のみ）",
         Inches(3.2), Inches(2.1), Inches(3.6), Inches(0.35),
         size=11, color=C_BG, align=PP_ALIGN.CENTER)
add_rect(sl, Inches(3.35), Inches(2.5), Inches(3.3), Inches(0.4),
         RGBColor(0x07, 0x50, 0x4C))
add_text(sl, "startScan() × 1",
         Inches(3.35), Inches(2.55), Inches(3.3), Inches(0.3),
         size=11, color=C_WHITE, align=PP_ALIGN.CENTER)
add_rect(sl, Inches(3.35), Inches(3.0), Inches(3.3), Inches(0.4),
         RGBColor(0x07, 0x50, 0x4C))
add_text(sl, "timeout: 30s + 2s delay",
         Inches(3.35), Inches(3.05), Inches(3.3), Inches(0.3),
         size=11, color=C_WHITE, align=PP_ALIGN.CENTER)

# 左: bleHistoryProvider
add_rect(sl, Inches(0.2), Inches(2.1), Inches(2.6), Inches(1.8), C_BG2)
add_text(sl, "bleHistoryProvider\n（ODID パース済み）",
         Inches(0.3), Inches(2.25), Inches(2.4), Inches(0.9),
         size=11, bold=True, color=C_GREEN, align=PP_ALIGN.CENTER)
add_text(sl, "← packets",
         Inches(0.3), Inches(3.1), Inches(2.4), Inches(0.5),
         size=10, color=C_CODE_TEXT, align=PP_ALIGN.CENTER)
# 矢印
add_text(sl, "◀━━━━", Inches(2.8), Inches(2.65), Inches(0.6), Inches(0.4),
         size=14, color=C_GREEN)

# 右: RawBleNotifier
add_rect(sl, Inches(7.2), Inches(2.1), Inches(2.6), Inches(1.8), C_BG2)
add_text(sl, "RawBleNotifier\n（BLE Raw タブ用）",
         Inches(7.3), Inches(2.25), Inches(2.4), Inches(0.9),
         size=11, bold=True, color=C_BLUE, align=PP_ALIGN.CENTER)
add_text(sl, "← rawResults",
         Inches(7.3), Inches(3.1), Inches(2.4), Inches(0.5),
         size=10, color=C_CODE_TEXT, align=PP_ALIGN.CENTER)
add_text(sl, "━━━━▶", Inches(6.8), Inches(2.65), Inches(0.6), Inches(0.4),
         size=14, color=C_BLUE)

# 3つの改善
add_text(sl, "3つの改善点",
         Inches(0.3), Inches(4.25), Inches(9.4), Inches(0.35),
         size=14, bold=True, color=C_WHITE54)

improvements = [
    ("スキャン一本化",
     "BleService だけがスキャンを管理\nRawBleNotifier は rawResults を購読するだけ",
     C_GREEN),
    ("再起動インターバル",
     "スキャン終了後 2秒待機してから再スキャン\n連続 start/stop を防止",
     C_ORANGE),
    ("タイムアウト延長",
     "20秒 → 30秒に延長\nstart/stop の頻度を約 33% 削減",
     C_BLUE),
]
for i, (title, desc, col) in enumerate(improvements):
    x = Inches(0.3 + i * 3.15)
    add_rect(sl, x, Inches(4.65), Inches(3.0), Inches(2.4), C_BG2)
    add_rect(sl, x, Inches(4.65), Inches(3.0), Inches(0.06), col)
    add_text(sl, title, x + Inches(0.12), Inches(4.75),
             Inches(2.76), Inches(0.4), size=13, bold=True, color=col)
    add_text(sl, desc, x + Inches(0.12), Inches(5.2),
             Inches(2.76), Inches(1.7), size=11, color=C_WHITE54)

# ─────────────────────────────────────────────────────────────────────────────
# S18: ProviderScope と ビルド修正
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "変更④ ビルド修正",
             "import パス修正 / ProviderScope / Gradle キャッシュ")

add_text(sl, "A  |  削除済みファイルへの import 修正",
         Inches(0.3), Inches(1.1), Inches(9.4), Inches(0.35),
         size=14, bold=True, color=C_WHITE)
code_box(sl, [
    "// 修正前: リファクタリングで削除されたファイルへの参照",
    "import 'drone_detection/drone_camera_page.dart'; // ← ファイル削除済み",
    "import 'uav_yolo_detector.dart';                 // ← パス変更済み",
    "",
    "// 修正後",
    "import 'detection/uav_yolo_detector.dart';       // 新しい正しいパス",
], Inches(0.3), Inches(1.5), Inches(9.4), Inches(1.9))

add_text(sl, "B  |  ProviderScope の追加",
         Inches(0.3), Inches(3.55), Inches(9.4), Inches(0.35),
         size=14, bold=True, color=C_WHITE)
bullet_box(sl, [
    "BleRawScanPage は ConsumerWidget（Riverpod を使用）",
    "Riverpod を使うウィジェットは必ず祖先に ProviderScope が必要",
    "main.dart の runApp を ProviderScope で包むことで全体に適用",
], Inches(0.3), Inches(3.95), Inches(5.5), Inches(1.5))
code_box(sl, [
    "// 修正前",
    "runApp(const RapidsnarkApp());",
    "",
    "// 修正後",
    "runApp(const ProviderScope(",
    "  child: RapidsnarkApp(),",
    "));",
], Inches(5.9), Inches(3.55), Inches(3.8), Inches(2.1))

add_text(sl, "C  |  Gradle kotlin-dsl キャッシュ破損",
         Inches(0.3), Inches(5.6), Inches(9.4), Inches(0.35),
         size=14, bold=True, color=C_WHITE)
code_box(sl, [
    "# エラー: Could not read workspace metadata from",
    "#   ~/.gradle/caches/8.12/kotlin-dsl/.../metadata.bin",
    "",
    "# 修正コマンド",
    "rm -rf ~/.gradle/caches/8.12/kotlin-dsl",
    "rm -rf android/.gradle",
    "flutter clean && flutter pub get",
], Inches(0.3), Inches(6.0), Inches(9.4), Inches(1.3))

# ─────────────────────────────────────────────────────────────────────────────
# S19: 変更ファイル一覧
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
slide_header(sl, "変更ファイル一覧", "新規作成 3 件 / 変更 5 件")

add_text(sl, "🆕  新規作成",
         Inches(0.3), Inches(1.1), Inches(9.4), Inches(0.35),
         size=14, bold=True, color=C_GREEN)

new_files = [
    ("lib/domain/raw_ble_device.dart",
     "BLE 生広告データモデル（RawBleDevice クラス）"),
    ("lib/providers/raw_ble_provider.dart",
     "BLE Raw スキャン Notifier（Riverpod）"),
    ("lib/features/ble_raw_scan/ble_raw_scan_page.dart",
     "BLE Raw スキャン画面 UI（ConsumerWidget）"),
]
for i, (path, desc) in enumerate(new_files):
    y = Inches(1.5 + i * 0.65)
    add_rect(sl, Inches(0.3), y, Inches(9.4), Inches(0.58), C_BG2)
    add_rect(sl, Inches(0.3), y, Inches(0.06), Inches(0.58), C_GREEN)
    add_text(sl, path, Inches(0.5), y + Inches(0.06),
             Inches(5.5), Inches(0.25), size=10, color=C_CODE_TEXT, bold=True)
    add_text(sl, desc, Inches(6.2), y + Inches(0.06),
             Inches(3.4), Inches(0.45), size=10, color=C_WHITE54)

add_text(sl, "✏️  変更",
         Inches(0.3), Inches(3.6), Inches(9.4), Inches(0.35),
         size=14, bold=True, color=C_BLUE)

changed_files = [
    ("lib/domain/uav_telemetry.dart",
     "App Code 対応・_knownManufacturerIds マップ追加"),
    ("lib/main.dart",
     "import 修正・ProviderScope 追加・BLE Raw タブ・メーカー ID 拡張"),
    ("lib/services/ble_service.dart",
     "rawResults ストリーム追加・2秒 delay・30秒 timeout"),
    ("lib/providers/raw_ble_provider.dart",
     "自前スキャン廃止・BleService.rawResults 購読に変更"),
    ("lib/features/safety_proof/safety_proof_page.dart",
     "BLE Raw タブ追加（main.dart 側が実際の起動対象）"),
]
for i, (path, desc) in enumerate(changed_files):
    y = Inches(4.0 + i * 0.65)
    add_rect(sl, Inches(0.3), y, Inches(9.4), Inches(0.58), C_BG2)
    add_rect(sl, Inches(0.3), y, Inches(0.06), Inches(0.58), C_BLUE)
    add_text(sl, path, Inches(0.5), y + Inches(0.06),
             Inches(5.5), Inches(0.25), size=10, color=C_CODE_TEXT, bold=True)
    add_text(sl, desc, Inches(6.2), y + Inches(0.06),
             Inches(3.4), Inches(0.45), size=10, color=C_WHITE54)

# ─────────────────────────────────────────────────────────────────────────────
# S20: まとめ
# ─────────────────────────────────────────────────────────────────────────────
sl = blank_slide(prs)
fill_bg(sl)
add_rect(sl, 0, 0, W, Inches(0.08), C_GREEN)
add_rect(sl, 0, 0, Inches(0.12), H, C_GREEN)
add_rect(sl, 0, Inches(7.3), W, Inches(0.2), C_TEAL)

add_text(sl, "まとめ",
         Inches(0.4), Inches(0.3), Inches(9.2), Inches(0.6),
         size=26, bold=True, color=C_WHITE)

summary = [
    ("①", "検知パターン拡張",
     ["App Code (0x0D) プレフィックスを除去して解析",
      "DJI新 / Parrot / Autel / Skydio を追加",
      "新メーカー追加はマップに1行追加するだけ"],
     C_GREEN),
    ("②", "BLE Raw スキャナー",
     ["解析可否問わず全 BLE デバイスを表示",
      "Wireshark 形式 Hex Dump + ASCII 表示",
      "解析失敗の具体的な理由を日本語で診断"],
     C_BLUE),
    ("③", "スキャン安定化",
     ["BleService への集約で start/stop 頻度を削減",
      "再起動 2秒インターバル・30秒 timeout",
      "Android レート制限エラーを解消"],
     C_ORANGE),
    ("④", "ビルド修正",
     ["削除済みファイルへの import を修正",
      "ProviderScope で Riverpod を全体適用",
      "Gradle kotlin-dsl キャッシュ破損の解消"],
     C_YELLOW),
]
for i, (num, title, points, col) in enumerate(summary):
    x = Inches(0.25 + (i % 2) * 4.9)
    y = Inches(1.05 + (i // 2) * 3.05)
    add_rect(sl, x, y, Inches(4.6), Inches(2.75), C_BG2)
    add_rect(sl, x, y, Inches(4.6), Inches(0.06), col)
    add_rect(sl, x, y, Inches(0.5), Inches(2.75), col)
    add_text(sl, num, x, y + Inches(0.9),
             Inches(0.5), Inches(0.8), size=20, bold=True, color=C_BG,
             align=PP_ALIGN.CENTER)
    add_text(sl, title, x + Inches(0.6), y + Inches(0.15),
             Inches(3.85), Inches(0.45), size=14, bold=True, color=col)
    for j, pt in enumerate(points):
        add_text(sl, "• " + pt,
                 x + Inches(0.6), y + Inches(0.65 + j * 0.6),
                 Inches(3.85), Inches(0.55), size=11, color=C_WHITE54)

# ─────────────────────────────────────────────────────────────────────────────
# 保存
# ─────────────────────────────────────────────────────────────────────────────
out = "/Users/smri/Downloads/cursor/m1/BLE_detection_changes.pptx"
prs.save(out)
print(f"Saved: {out}  ({len(prs.slides)} slides)")
