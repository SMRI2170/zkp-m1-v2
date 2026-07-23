#!/usr/bin/env python3
"""M2 再帰アグリゲータ（gnark）まとめスライド。

複数端末の検証を1つに繋げる（rapidsnark=葉 / gnark=集約）。
Spike A interop → B 回路内再帰検証/N=3集約 → C EVM着地・定数gas。

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
tf = tbox(s, 0.9, 2.15, 8.2, 0.5)
run(tf.paragraphs[0], "M2 / 検証を1つに繋げる", 15, GRAY)
tf = tbox(s, 0.88, 2.7, 8.4, 1.5)
run(tf.paragraphs[0], "再帰アグリゲータ (gnark)", 30, INK, bold=True)
hrule(s, 4.25, l=0.92, w=5.4, color=ACCENT)
tf = tbox(s, 0.92, 4.43, 8.2, 1.6)
run(tf.paragraphs[0], "複数端末の独立証明を1つに集約し、オンチェーン検証を定数gasに", 14, INK)
p = tf.add_paragraph(); p.space_before = Pt(6)
run(p, "端末=rapidsnark(葉) / 集約=gnark(再帰) / EVM着地", 12, GRAY, font=MONO)

# 2 目的と分業
s = add_slide()
title(s, "目的と分業 — rapidsnark と gnark")
tf = tbox(s, 0.7, 1.35, 8.7, 1.5)
bullet(tf, "各端末が rapidsnark で証明を作る（葉プロ―バ・高速・オンデバイス）", first=True)
bullet(tf, "rapidsnark は証明を作るだけ。証明どうしを『繋ぐ』（再帰検証）はできない", bold=True)
sub(tf, "circom で Groth16-in-Groth16 は非現実的 → 繋ぐのは gnark")
codebox(s, 0.7, 3.1, 8.6, 2.4, [
    "端末: rapidsnark → π_i + public_i  （BN254 Groth16, snarkjs互換）",
    "   │  N 個の葉証明",
    "   ▼",
    "gnark 集約器: π_1..π_N を回路内で再帰検証 + 関係強制",
    "   → 集約証明 1個 → EVM で1回検証（定数gas）",
])
tf = tbox(s, 0.7, 5.7, 8.7, 0.8)
bullet(tf, "端末は現行 rapidsnark を一切変えずに繋げられる（形式変換のみ）", size=12, first=True)

# 3 手法の位置づけ
s = add_slide()
title(s, "手法の位置づけと最新フレームワーク")
table(s, 0.7, 1.5, 8.6, [
    ["種別", "内容", "FW"],
    ["再帰SNARK", "証明の中で証明を検証（採用）", "gnark"],
    ["フォールディング", "多数ステップを畳む", "Sonobe(Nova) / Plonky3"],
    ["集約", "同一VKを安く束ねる", "SnarkPack"],
    ["zkVM/集約層", "プログラム化して集約", "SP1 / RISC Zero / Nebra"],
], col_w=[1.9, 4.3, 2.4], fs=11, row_h=0.5)
tf = tbox(s, 0.7, 4.4, 8.7, 2.0)
bullet(tf, "今回は再帰SNARK(gnark)を採用 — 異種回路も扱え、関係を回路内で強制できる", first=True, bold=True)
bullet(tf, "circom維持で折りたたむなら Sonobe(Nova) が最新の代替")
sub(tf, "SnarkPack は同一VKの gas 最適化だが証明間の関係を強制しない")

# 4 Spike A
s = add_slide()
title(s, "Spike A — interop（最大リスクを先に）")
tf = tbox(s, 0.7, 1.35, 8.7, 1.3)
bullet(tf, "gnark で snarkjs(circom) の Groth16 証明をそのまま検証できるか", first=True)
sub(tf, "点の形式変換（特に G2 の座標順）が正しいか＝interopの核心")
codebox(s, 0.7, 2.7, 8.6, 1.7, [
    "gnark-crypto bn254 で e(A,B)=e(α,β)·e(vk_x,γ)·e(C,δ) を検証",
    "dev0(整合)/dev2(詐称) → OK   /   改ざん public → FAIL",
    "G2 座標順(A0=c0,A1=c1)は無変換で一致",
])
tf = tbox(s, 0.7, 4.6, 8.7, 1.2)
bullet(tf, "結果: rapidsnark/snarkjs の証明を gnark がそのまま扱える（interop 成立）",
       size=13, first=True, bold=True)

# 5 Spike B
s = add_slide()
title(s, "Spike B — 回路内再帰検証 → N=3 集約")
tf = tbox(s, 0.7, 1.35, 8.7, 0.7)
bullet(tf, "gnark 回路内で証明を検証（emulated BN254）し、N=3 を1つに集約", first=True)
codebox(s, 0.7, 2.1, 8.6, 1.5, [
    "回路内で強制: 同一drone_id / 同一time_bucket /",
    "  各within30==1 / device_pubkey相異 / consistency集計",
])
table(s, 0.7, 3.8, 8.6, [
    ["", "制約数", "prove", "verify", "setup(1回)"],
    ["1証明", "2.16M", "20.6s", "3ms", "5m"],
    ["N=3集約", "6.36M", "58.6s", "17ms", "14m40s"],
], col_w=[1.7, 1.9, 1.7, 1.6, 1.7], fs=11, row_h=0.42)
tf = tbox(s, 0.7, 5.5, 8.7, 0.9)
bullet(tf, "consistentCount=2 を検証（dev0,1整合・dev2詐称はsuspicious）", size=12.5, first=True, bold=True)

# 6 Spike C
s = add_slide()
title(s, "Spike C — EVM 着地・定数 gas")
tf = tbox(s, 0.7, 1.35, 8.7, 0.7)
bullet(tf, "集約証明の Solidity verifier を出力し、オンチェーンで1回検証", first=True)
codebox(s, 0.7, 2.1, 8.6, 1.3, [
    "gnark solidity export → AggregateVerifier.sol",
    "verifyProof(bytes proof, uint256[2] input) を Hardhat で検証",
])
table(s, 0.7, 3.6, 8.6, [
    ["方式", "N=3", "N=8", "スケール"],
    ["M1 個別検証", "~660k", "~1.76M", "O(N) 台数比例"],
    ["M2 集約(本方式)", "347k", "347k", "定数(N非依存)"],
], col_w=[2.8, 2.0, 2.0, 1.8], fs=11, row_h=0.45)
tf = tbox(s, 0.7, 5.4, 8.7, 1.0)
bullet(tf, "集約検証gas=347k は N に依存しない → 台数が増えるほど優位", size=13, first=True, bold=True)

# 7 まとめ
s = add_slide()
title(s, "まとめと残り")
tf = tbox(s, 0.7, 1.45, 8.7, 2.4)
subhead(tf, "実証できたこと", 0)
bullet(tf, "端末=rapidsnark(葉) / gnark=再帰集約 の分業が動作", first=True)
bullet(tf, "N台の独立証明を1つに集約し、関係(同一ドローン/端末相異/整合)を回路内強制")
bullet(tf, "オンチェーン検証は単一Groth16＝定数gas(347k)。プロ―バコストも現実的")
tf = tbox(s, 0.7, 3.9, 8.7, 2.6)
subhead(tf, "残り", 0)
bullet(tf, "群キー(drone_id/time_bucket)のpublic出力＋registry統合", first=True)
bullet(tf, "登録Merkleメンバーシップ（M2のSybilを定数gasで担保）")
bullet(tf, "包含性証明（集約者の検閲＝票の間引きを封じる）")
sub(tf, "重いのは setup(1回限り)のみ。setupのMPC化は本番の必須課題")

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "week18")
os.makedirs(OUT_DIR, exist_ok=True)
out_path = os.path.join(OUT_DIR, "m2_recursive_aggregator.pptx")
prs.save(out_path)
print(f"saved: {os.path.abspath(out_path)}  ({len(prs.slides._sldIdLst)} slides)")
