#!/usr/bin/env python3
"""週18 まとめスライド — RSSI による RemoteID なりすまし検知。

背景 → 検知原理 → 判定ロジック(相対許容/ロバスト) → 脅威モデル →
評価(ROC) → 回路・レジストリ統合 → 現状と今後。

デザイン（進捗第11回スタイル / ミニマル）: 白背景・黒文字・Yu Gothic / Courier New、
枠はコード抜粋のみ、タイトル直下に横罫線、4:3 (10 x 7.5 inch)。
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
ACCENT = RGBColor(0x33, 0x3E, 0x6E)
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


def hrule(s, top, l=0.7, w=8.6, color=RULE):
    ln = s.shapes.add_shape(1, Inches(l), Inches(top), Inches(w), Pt(1.0))
    ln.fill.solid(); ln.fill.fore_color.rgb = color
    ln.line.fill.background(); ln.shadow.inherit = False


def title(s, text):
    tf = tbox(s, 0.68, 0.42, 8.7, 0.8)
    run(tf.paragraphs[0], text, 22, INK, bold=True)
    hrule(s, 1.1)


def subhead(tf, text, space_before=13):
    p = tf.add_paragraph(); p.space_before = Pt(space_before)
    run(p, text, 15, INK, bold=True); return p


def bullet(tf, text, size=13, space_before=6, indent=False, bold=False, first=False):
    p = tf.add_paragraph(); p.space_before = Pt(2 if first else space_before)
    run(p, ("   ・ " if indent else "・ "), size, INK)
    run(p, text, size, INK, bold=bold); return p


def sub(tf, text, size=11, space_before=2):
    p = tf.add_paragraph(); p.space_before = Pt(space_before)
    run(p, "      " + text, size, GRAY); return p


def codebox(s, l, t, w, h, lines, size=11):
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


def table(s, l, t, w, rows, col_w, header=True, fs=11, row_h=0.34):
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
tf = tbox(s, 0.9, 2.2, 8.2, 0.5)
run(tf.paragraphs[0], "進捗まとめ（2026-07 / 週18）", 15, GRAY)
tf = tbox(s, 0.88, 2.75, 8.4, 1.6)
run(tf.paragraphs[0], "RSSI による RemoteID", 30, INK, bold=True)
p = tf.add_paragraph(); p.space_before = Pt(4)
run(p, "なりすまし検知", 30, INK, bold=True)
hrule(s, 4.5, l=0.92, w=5.4, color=ACCENT)
tf = tbox(s, 0.92, 4.68, 8.2, 1.6)
run(tf.paragraphs[0], "放送位置 vs 実測レンジの矛盾を、多端末で検知し合意する", 14, INK)
p = tf.add_paragraph(); p.space_before = Pt(6)
run(p, "相対許容回路 / 中央値集約 / 脅威モデル / 合成ROC / 回路・レジストリ統合", 11.5, GRAY, font=MONO)

# 2 課題と原理
s = add_slide()
title(s, "課題と検知原理")
tf = tbox(s, 0.7, 1.35, 8.7, 1.5)
bullet(tf, "RemoteID は自己申告 → 放送位置が本物かは裏取りできない", first=True, bold=True)
bullet(tf, "ドローンは改造不可。検証は地上側・受動的に、物理量で行うしかない")
codebox(s, 0.7, 3.0, 8.6, 2.0, [
    "各端末が同じ放送について 2 通りの独立な距離を得る:",
    "  d_claim = |放送位置 − 自端末GPS|      （幾何）",
    "  d_meas  = RSSI から推定             （電波の物理）",
    "",
    "本物なら一致 / 位置詐称・中継で乖離 → 矛盾を検知",
])
tf = tbox(s, 0.7, 5.2, 8.7, 1.2)
bullet(tf, "放送だけ見れば区別できない。実測を突き合わせて初めて分かる", size=12.5, first=True)

# 3 判定ロジック
s = add_slide()
title(s, "判定ロジック — 相対許容 + ロバスト集約")
tf = tbox(s, 0.7, 1.3, 8.7, 1.2)
bullet(tf, "RSSI 誤差は乗法的（相対%）→ 許容は固定 m でなく相対帯で", first=True)
bullet(tf, "単発 RSSI は粗い → 複数サンプルの中央値で外れ値に強くする")
codebox(s, 0.7, 2.75, 8.6, 1.7, [
    "consistent ⇔  d_meas*(1-r) ≤ d_claim ≤ d_meas*(1+r)   (r=±90%)",
    "d_meas = median(直近サンプル)   # マルチパス外れ値に頑健",
])
tf = tbox(s, 0.7, 4.65, 8.7, 1.8)
subhead(tf, "実装（回路・モデル・アプリで一致）", 0)
bullet(tf, "回路 remoteid_consistency_rel.circom（二乗＋DEN^2倍で整数比較, 約650制約）", first=True)
bullet(tf, "中央値集約: 真30m・外れ値20%で 平均誤差 14.3m → 4.5m")
bullet(tf, "アプリ: 直近10件RSSIを中央値集約して live 判定（BLE/WiFi 両経路）")

# 4 脅威モデル
s = add_slide()
title(s, "脅威モデル — 何を防ぎ、何を防がないか")
table(s, 0.7, 1.45, 8.6, [
    ["攻撃", "手口", "RSSI多witnessで検知"],
    ["位置詐称（主眼）", "放送位置だけ別地点に書換", "○ 真の発信源近くで矛盾"],
    ["捏造", "存在しない機体をでっち上げ", "△〜○"],
    ["リプレイ", "過去の放送を再送", "○（新鮮さ併用=M3）"],
    ["中継/ワームホール", "遠方の本物信号を近くで再放送", "✕ 原理的限界"],
    ["Sybil / witness GPS詐称", "偽端末・自位置詐称", "✕ 別対策(M3)"],
], col_w=[2.3, 3.8, 2.5], fs=11, row_h=0.5)
tf = tbox(s, 0.7, 5.2, 8.7, 1.4)
bullet(tf, "主眼は位置詐称。中継・Sybil は明確な限界として M3(真正性)に委ねる",
       size=12.5, first=True, bold=True)

# 5 評価
s = add_slide()
title(s, "評価 — 本当に検知できるか（合成ROC）")
tf = tbox(s, 0.7, 1.3, 8.7, 0.5)
run(tf.paragraphs[0], "eval_spoof_detection.py（端末分散40m・集約M=8・FPR=5%）", 12, GRAY)
table(s, 0.7, 1.85, 4.2, [
    ["Δ(位置詐称)", "検知率(N=5)"],
    ["10 m", "28%"],
    ["20 m", "75%"],
    ["30 m", "91%"],
    ["50 m", "98%"],
], col_w=[2.1, 2.1], fs=11, row_h=0.42)
table(s, 5.1, 1.85, 4.2, [
    ["witness 数", "検知率(Δ=30m)"],
    ["1 台", "64%"],
    ["3 台", "83%"],
    ["8 台", "98%"],
    ["σ=8dB", "48%"],
], col_w=[2.1, 2.1], fs=11, row_h=0.42)
tf = tbox(s, 0.7, 4.5, 8.7, 2.0)
subhead(tf, "結論", 0)
bullet(tf, "粗い位置詐称（Δ≳20–30m）は実用的に検知可能、細かいズレは苦手", first=True)
bullet(tf, "多 witness が本質的に必要（単独64% → 8台98%）", bold=True)
bullet(tf, "ノイズσが検知率を左右 → 実機較正(Phase3)が数値を決める")

# 5b 評価の深掘り（融合方式 / 較正精度）
s = add_slide()
title(s, "評価の深掘り — 融合方式 / 較正精度")
tf = tbox(s, 0.7, 1.25, 8.7, 0.45)
run(tf.paragraphs[0], "多辺測量を実装して比較、および較正ズレの影響を定量化", 12, GRAY)
tf = tbox(s, 0.7, 1.75, 8.7, 0.4)
run(tf.paragraphs[0], "融合方式の比較（Δ=20m, FPR=5%）", 13, INK, bold=True)
table(s, 0.7, 2.15, 8.6, [
    ["条件", "中央値合意", "多辺測量"],
    ["N=6, σ=4dB（現実的）", "83%", "58%"],
    ["N=6, σ=2dB（低ノイズ）", "99%", "99%"],
    ["N=12, σ=4dB", "94%", "93%"],
], col_w=[3.6, 2.5, 2.5], fs=11, row_h=0.4)
tf = tbox(s, 0.7, 4.05, 8.7, 0.4)
run(tf.paragraphs[0], "較正ズレの頑健性（Δ=30m, N=5）", 13, INK, bold=True)
table(s, 0.7, 4.45, 8.6, [
    ["較正", "一致", "n +0.5", "n −0.5", "A +6dB"],
    ["検知率", "91%", "72%", "7.7%", "8%"],
], col_w=[1.7, 1.7, 1.7, 1.7, 1.8], fs=11, row_h=0.4)
tf = tbox(s, 0.7, 5.55, 8.7, 1.1)
bullet(tf, "現実的ノイズでは中央値合意が有利 → 簡素な合意を既定に（回路・実装と一致）",
       size=12, first=True, bold=True)
bullet(tf, "較正がズレると検知は崩壊 → 実機較正(Phase3)は必須（A数dB・n±0.5未満）",
       size=12, bold=True)

# 6 回路・レジストリ統合
s = add_slide()
title(s, "回路・レジストリ統合（Phase 4）")
tf = tbox(s, 0.7, 1.3, 8.7, 1.0)
bullet(tf, "witness 回路に consistency_ok を統合（public 15）→ レジストリで集計", first=True)
codebox(s, 0.7, 2.35, 8.6, 2.2, [
    "同一 drone_id × time_bucket で、相異なる登録端末が K 台:",
    "  consistency_ok=1 が K 台 → ConsensusReached（放送を裏取り＝trusted）",
    "  consistency_ok=0 が K 台 → SpoofAlert（実測と矛盾＝なりすまし疑い）",
])
tf = tbox(s, 0.7, 4.75, 8.7, 1.7)
subhead(tf, "E2E 実証（Hardhat 11/11 通過）", 0)
bullet(tf, "実証明3台（整合2台＋詐称1台）→ 実 Groth16Verifier 検証", first=True)
bullet(tf, "整合2台で trusted 合意成立、詐称1台は suspicious 側に計上", bold=True)
bullet(tf, "K 台が矛盾を出せば SpoofAlert（なりすまし合意）も確認")

# 7 現状と今後
s = add_slide()
title(s, "現状と今後")
tf = tbox(s, 0.7, 1.4, 8.7, 2.6)
subhead(tf, "できたこと（週18）", 0)
bullet(tf, "相対許容回路 / 中央値ロバスト化（回路・モデル・アプリ一致）", first=True)
bullet(tf, "脅威モデル明文化 + 合成ROC で検知可否を定量化")
bullet(tf, "consistency_ok を witness 回路・レジストリに統合、trusted/SpoofAlert を E2E 実証")
tf = tbox(s, 0.7, 3.9, 8.7, 2.7)
subhead(tf, "今後", 0)
bullet(tf, "実機 DJI で RSSI 較正（A/n/σ 確定）→ ROC を実データで再評価（Phase 3）", first=True)
bullet(tf, "K の最終決定（実機 σ 依存）")
bullet(tf, "M3 真正性: 中継・Sybil・witness GPS 詐称への対処（署名RemoteID・端末Attestation）")
sub(tf, "到達点は「K台の登録witnessが物理的矛盾を認めた」。真正性の完成は M3 と合わせて")

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "week18")
os.makedirs(OUT_DIR, exist_ok=True)
out_path = os.path.join(OUT_DIR, "week18_rssi_spoof_detection.pptx")
prs.save(out_path)
print(f"saved: {os.path.abspath(out_path)}  ({len(prs.slides._sldIdLst)} slides)")
