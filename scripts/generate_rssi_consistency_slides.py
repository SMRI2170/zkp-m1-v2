#!/usr/bin/env python3
"""RemoteID なりすまし検出（RSSI 整合チェック）機能まとめスライド。

ドローンを改造せず、地上（端末）側の RSSI 実測だけで RemoteID 放送位置の
矛盾を検出する機能を、背景〜ZK回路〜アプリ実装〜限界まで1本にまとめる。

デザイン（進捗第11回スタイル / ミニマル）:
  - 背景 白 / 黒文字（1A1A1A）、補助グレー（555555）。色は原則使わない。
  - フォント Yu Gothic / コードは Courier New。枠はコード抜粋のみ。
  - タイトル直下に細い横罫線。4:3 (10 x 7.5 inch)
"""

import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn

INK = RGBColor(0x1A, 0x1A, 0x1A)
GRAY = RGBColor(0x55, 0x55, 0x55)
RULE = RGBColor(0xCC, 0xCC, 0xCC)
CODEBG = RGBColor(0xF7, 0xF7, 0xF7)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "Yu Gothic"
MONO = "Courier New"

prs = Presentation()
prs.slide_width = Inches(10)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
_page = [0]


def _set_font(r, font=FONT):
    r.font.name = font
    rPr = r._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {}); rPr.append(el)
        el.set("typeface", font)


def run(p, text, size, color=INK, bold=False, font=FONT):
    r = p.add_run(); r.text = text
    r.font.size = Pt(size); r.font.color.rgb = color; r.font.bold = bold
    _set_font(r, font); return r


def add_slide(number=True):
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid(); s.background.fill.fore_color.rgb = WHITE
    if number:
        _page[0] += 1
        tf = s.shapes.add_textbox(Inches(9.2), Inches(7.05), Inches(0.55), Inches(0.35)).text_frame
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.RIGHT
        run(p, str(_page[0]), 10, GRAY)
    return s


def tbox(s, l, t, w, h):
    tf = s.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h)).text_frame
    tf.word_wrap = True; return tf


def hrule(s, top, l=0.7, w=8.6):
    ln = s.shapes.add_shape(1, Inches(l), Inches(top), Inches(w), Pt(1.0))
    ln.fill.solid(); ln.fill.fore_color.rgb = RULE
    ln.line.fill.background(); ln.shadow.inherit = False


def title(s, text):
    tf = tbox(s, 0.68, 0.42, 8.7, 0.8)
    run(tf.paragraphs[0], text, 23, INK, bold=True)
    hrule(s, 1.12)


def subhead(tf, text, space_before=13):
    p = tf.add_paragraph(); p.space_before = Pt(space_before)
    run(p, text, 15, INK, bold=True); return p


def bullet(tf, text, size=13.5, space_before=7, indent=False, bold=False, first=False):
    p = tf.add_paragraph(); p.space_before = Pt(2 if first else space_before)
    run(p, ("   ・ " if indent else "・ "), size, INK)
    run(p, text, size, INK, bold=bold); return p


def sub(tf, text, size=11.5, space_before=2):
    p = tf.add_paragraph(); p.space_before = Pt(space_before)
    run(p, "      " + text, size, GRAY); return p


def codebox(s, l, t, w, h, lines, size=11.5):
    box = s.shapes.add_shape(1, Inches(l), Inches(t), Inches(w), Inches(h))
    box.fill.solid(); box.fill.fore_color.rgb = CODEBG
    box.line.color.rgb = RULE; box.line.width = Pt(0.75); box.shadow.inherit = False
    tf = box.text_frame; tf.word_wrap = True
    tf.margin_left = Pt(10); tf.margin_right = Pt(8)
    tf.margin_top = Pt(7); tf.margin_bottom = Pt(7)
    for i, item in enumerate(lines):
        text, gray = item if isinstance(item, tuple) else (item, False)
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_before = Pt(2.5)
        run(p, text, size, GRAY if gray else INK, font=MONO)
    return box


def _cell_border(cell, color="CCCCCC", w=6350):
    tc = cell._tc; tcPr = tc.get_or_add_tcPr()
    for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        old = tcPr.find(qn(tag))
        if old is not None:
            tcPr.remove(old)
        ln = tcPr.makeelement(qn(tag), {"w": str(w), "cap": "flat"})
        fill = ln.makeelement(qn("a:solidFill"), {})
        clr = fill.makeelement(qn("a:srgbClr"), {"val": color})
        fill.append(clr); ln.append(fill); tcPr.append(ln)


def table(s, l, t, w, rows, col_w, header=True, fs=12, row_h=0.34):
    nr = len(rows); nc = len(rows[0])
    gtbl = s.shapes.add_table(nr, nc, Inches(l), Inches(t), Inches(w), Inches(row_h * nr))
    tbl = gtbl.table; tbl.first_row = False; tbl.horz_banding = False
    for ci, cw in enumerate(col_w):
        tbl.columns[ci].width = Inches(cw)
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = tbl.cell(ri, ci)
            cell.fill.solid(); cell.fill.fore_color.rgb = WHITE
            cell.margin_left = Pt(6); cell.margin_right = Pt(4)
            cell.margin_top = Pt(2); cell.margin_bottom = Pt(2)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            _cell_border(cell)
            p = cell.text_frame.paragraphs[0]
            run(p, str(val), fs, INK, bold=(header and ri == 0))
    return tbl


# 1 表紙
s = add_slide(number=False)
tf = tbox(s, 0.9, 2.15, 8.2, 0.5)
run(tf.paragraphs[0], "進捗まとめ（2026-07-07 / 週17）", 15, GRAY)
tf = tbox(s, 0.88, 2.7, 8.4, 1.9)
run(tf.paragraphs[0], "RemoteID なりすまし検出", 32, INK, bold=True)
p = tf.add_paragraph(); p.space_before = Pt(4)
run(p, "RSSI 整合チェック（ドローン改造なし）", 26, INK, bold=True)
hrule(s, 4.55, l=0.92, w=5.6)
tf = tbox(s, 0.92, 4.72, 8.2, 1.6)
run(tf.paragraphs[0], "地上の端末が測る受信強度だけで、放送位置の矛盾を検出する", 14, INK)
p = tf.add_paragraph(); p.space_before = Pt(6)
run(p, "circuit remoteid_consistency.circom / app lib/core/rssi_ranging.dart", 12, GRAY, font=MONO)

# 2 背景
s = add_slide()
title(s, "背景 — RemoteID は「自己申告」")
tf = tbox(s, 0.7, 1.4, 8.7, 2.3)
bullet(tf, "DJI 等は RemoteID で ID と位置を放送する（アプリは受信済み）", first=True)
bullet(tf, "だが放送は詐称・リプレイ・非放送ができ、本物かを裏取りできない", bold=True)
bullet(tf, "ドローンには署名も機器も足せない（閉じた市販品）")
tf = tbox(s, 0.7, 3.9, 8.7, 2.8)
subhead(tf, "→ 検証は地上側・受動的に、ドローンが操作できない物理量で行うしかない", 0)
bullet(tf, "端末が測れる現実的な物理量 = RemoteID ビーコンの受信強度 RSSI", first=True)
bullet(tf, "「放送された位置」と「RSSI から測った距離」が矛盾したら詐称と判定")
sub(tf, "放送だけ見れば区別できない。実測を突き合わせて初めて分かる")

# 3 RSSI モデル
s = add_slide()
title(s, "RSSI → 距離 の較正モデル")
codebox(s, 0.7, 1.4, 8.6, 1.35, [
    "RSSI(d) = A - 10 n log10(d)   ⇔   d = 10^((A - RSSI)/(10 n))",
    ("A=1m時RSSI  n=伝搬指数  （実機DJIで (rssi,真距離) を集めて fit）", True),
])
tf = tbox(s, 0.7, 2.95, 8.7, 0.7)
bullet(tf, "合成データで較正 → パラメータを正しく回復（A=-40.2, n=2.49, σ=3.5dB）", first=True)
table(s, 0.7, 3.75, 8.6, [
    ["真の距離", "推定", "±2σ 帯", "measured_range_cm"],
    ["3 m", "2.9 m", "[1.6, 5.6] m", "295"],
    ["10 m", "9.9 m", "[5.2, 18.7] m", "987"],
    ["30 m", "29.8 m", "[15.7, 56.5] m", "2975"],
], col_w=[1.7, 1.5, 2.8, 2.6], fs=11.5, row_h=0.42)
tf = tbox(s, 0.7, 6.0, 8.7, 1.0)
bullet(tf, "発見: RSSI 誤差は「固定 m」でなく「相対 %」（±38%/1σ, ±90%/2σ）", size=12.5, first=True, bold=True)
sub(tf, "距離が伸びるほど帯が広がる → 許容は相対で設計、細かい詐称は無理・粗い矛盾のみ")

# 4 ZK 回路
s = add_slide()
title(s, "ZK 回路 — remoteid_consistency.circom")
tf = tbox(s, 0.7, 1.35, 8.7, 0.7)
bullet(tf, "放送位置から計算した二乗距離が、実測レンジの許容帯に入るかを証明（座標は秘匿）", first=True)
codebox(s, 0.7, 2.15, 8.6, 1.7, [
    "claimed_dist_sq = |broadcast_pos - phone_pos|^2     # 放送値から計算",
    "lower = max(measured - TOL, 0),  upper = measured + TOL",
    "consistency_ok = ( lower^2 <= claimed_dist_sq <= upper^2 )",
    ("※ 平方根を避け、すべてスケール後の二乗で比較", True),
])
tf = tbox(s, 0.7, 4.05, 8.7, 0.55)
bullet(tf, "合成サンプルで検証（放送位置は同一、実測レンジだけ変える）", first=True)
table(s, 0.7, 4.65, 8.6, [
    ["入力", "放送位置(claimed)", "実測レンジ", "consistency_ok"],
    ["整合", "同一（≈3.4m）", "341 cm", "1"],
    ["詐称", "同一（≈3.4m）", "5000 cm", "0  ← 検出"],
], col_w=[1.3, 3.0, 2.0, 2.3], fs=11.5, row_h=0.42)
tf = tbox(s, 0.7, 6.35, 8.7, 0.6)
bullet(tf, "制約 約540（M1 の EdDSA 回路 1.2万に対し軽量 → 多witness集約に載せやすい）",
       size=12, first=True)

# 5 アプリ実装
s = add_slide()
title(s, "アプリ実装 — 端末で live 判定")
tf = tbox(s, 0.7, 1.35, 8.7, 1.5)
bullet(tf, "lib/core/rssi_ranging.dart: path-loss モデル＋整合チェック（自己完結）", first=True)
bullet(tf, "main.dart: BLE / WiFi の Location 受信ハンドラに配線")
sub(tf, "放送位置＋自端末GPS＋RSSI が揃うと、その場で verdict をログ表示")
codebox(s, 0.7, 3.0, 8.6, 1.9, [
    "// RemoteID Location 受信時",
    "claimed = 3D距離(自端末GPS, 放送位置)",
    "r = checkRssiConsistency(claimed, rssi)",
    "",
    "[BLE  RSSI-check] 整合         claimed=3.4m est=2.9m band[1.6,5.6]m",
    "[WiFi RSSI-check] なりすまし疑い claimed=3.4m est=48m band[27,84]m",
])
tf = tbox(s, 0.7, 5.1, 8.7, 1.0)
bullet(tf, "dart analyze クリーン（既存4回路・他機能は無改変で追加のみ）", size=12.5, first=True)
sub(tf, "この live ログが、実機 DJI での RSSI 較正データ収集の入口になる")

# 6 限界と今後
s = add_slide()
title(s, "正直な限界と今後")
tf = tbox(s, 0.7, 1.4, 8.7, 2.2)
subhead(tf, "限界（設計に明記）", 0)
bullet(tf, "RSSI は粗い（30mで[16,57]m）→ 単独では弱く、多witnessの冗長が必須", first=True)
bullet(tf, "リレー/ワームホール攻撃は RSSI 照合では原理的に防げない")
sub(tf, "精密化には将来 AoA / TDoA、真正性には端末アテステーションが要る")
tf = tbox(s, 0.7, 3.85, 8.7, 3.0)
subhead(tf, "今後", 0)
bullet(tf, "回路を相対許容（±%）版へ更新し、RSSI の現実に合わせる", first=True)
bullet(tf, "実機 DJI で (rssi, 真距離) を収集し A / n を較正、TOL を確定")
bullet(tf, "consistency_ok を M1 レジストリに統合 → 多witnessで放送真偽を合意")
sub(tf, "「接近の証明」でなく「なりすまし検出の証明」に軸足を置く")

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "week17")
os.makedirs(OUT_DIR, exist_ok=True)
out_path = os.path.join(OUT_DIR, "rssi_consistency_detection.pptx")
prs.save(out_path)
print(f"saved: {os.path.abspath(out_path)}  ({len(prs.slides._sldIdLst)} slides)")
