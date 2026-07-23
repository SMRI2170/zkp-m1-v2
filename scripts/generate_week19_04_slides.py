#!/usr/bin/env python3
"""week19/04_フレームワーク概要.md のスライド化（進捗第11回スタイル）。"""

import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
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
L, W, TOP = 0.7, 8.6, 1.35


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


def hrule(s, top, l=0.7, w=8.6, color=RULE):
    ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(l), Inches(top), Inches(w), Pt(1.0))
    ln.fill.solid(); ln.fill.fore_color.rgb = color
    ln.line.fill.background(); ln.shadow.inherit = False


def title(s, text):
    tf = s.shapes.add_textbox(Inches(0.68), Inches(0.42), Inches(8.7), Inches(0.8)).text_frame
    tf.word_wrap = True
    run(tf.paragraphs[0], text, 23, INK, bold=True)
    hrule(s, 1.14)


def _vlen(t):
    return int(sum(0.5 if ord(c) < 0x3000 else 1.0 for c in t))


def bullets(s, y, items, size0=16, size1=13.5):
    tf = s.shapes.add_textbox(Inches(L), Inches(y), Inches(W), Inches(0.4)).text_frame
    tf.word_wrap = True
    h = 0.0
    for i, (lv, text) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_before = Pt(0 if i == 0 else (6 if lv == 0 else 2))
        size = size0 if lv == 0 else size1
        run(p, ("■ " if lv == 0 else "　　・ "), size, INK); run(p, text, size, INK)
        cpl = max(14, int(590 / size)); lh = size * 1.5 / 72.0
        h += max(1, -(-_vlen(text) // cpl)) * lh + (0.07 if i else 0)
    return y + h + 0.12


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


def table(s, y, rows, col_w, fs=12, row_h=0.4):
    nr, nc = len(rows), len(rows[0])
    gtbl = s.shapes.add_table(nr, nc, Inches(L), Inches(y), Inches(sum(col_w)), Inches(row_h * nr))
    tbl = gtbl.table; tbl.first_row = False; tbl.horz_banding = False
    for ci, cw in enumerate(col_w):
        tbl.columns[ci].width = Inches(cw)
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = tbl.cell(ri, ci)
            cell.fill.solid(); cell.fill.fore_color.rgb = WHITE
            cell.margin_left = Pt(5); cell.margin_right = Pt(3)
            cell.margin_top = Pt(1); cell.margin_bottom = Pt(1)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            _cell_border(cell)
            run(cell.text_frame.paragraphs[0], str(val), fs, INK, bold=(ri == 0))
    return y + row_h * nr + 0.14


# ════════════════════════════════════════════════════════════════════════════
# S1 表紙
s = add_slide(number=False)
tf = s.shapes.add_textbox(Inches(0.9), Inches(2.6), Inches(8.2), Inches(1.2)).text_frame
tf.word_wrap = True
run(tf.paragraphs[0], "フレームワーク概要", 32, INK, bold=True)
hrule(s, 3.9, l=0.92, w=5.4)
tf = s.shapes.add_textbox(Inches(0.92), Inches(4.05), Inches(8.2), Inches(0.9)).text_frame
tf.word_wrap = True
run(tf.paragraphs[0], "それぞれ「何者か」入門 — 何者/核の仕組み/背景/使われ方", 15, INK)
tf = s.shapes.add_textbox(Inches(0.92), Inches(6.4), Inches(8.0), Inches(0.5)).text_frame
run(tf.paragraphs[0], "week19 / 04_フレームワーク概要", 12, GRAY)

# S2 読み方
s = add_slide(); title(s, "読み方（前提の言葉）")
bullets(s, TOP, [
    (0, "回路(circuit) = 証明したい計算を、足し算・掛け算の制約の集まりに変換したもの"),
    (0, "証明系 = 回路から証明を作り検証する数学エンジン（Groth16 / PLONK / STARK …）"),
    (0, "トラステッドセットアップ = 一部の証明系が要る“鍵作りの儀式”。漏れると偽造の恐れ"),
    (0, "フレームワーク ＝ おおむね「回路を書く言語 ＋ 証明系エンジン」の組み合わせ"),
], size0=16.5)

# S3 A① SNARK系（前半）
s = add_slide(); title(s, "A. 回路を書いてSNARK証明（1）")
bullets(s, TOP, [
    (0, "circom（＋snarkjs） = 回路記述の専用言語＋証明を扱うJSライブラリ"),
    (1, "iden3製。circomlibにPoseidon/EdDSA/比較。Tornado/Semaphore等・本案件の現行"),
    (0, "rapidsnark = circom回路の高速Groth16証明生成器（C++/アセンブリ）"),
    (1, "iden3製。snarkjsと同じ証明を桁違いに速く。サーバ・モバイル端末証明"),
    (0, "gnark = Goで書くフルスタックZKPライブラリ"),
    (1, "ConsenSys製。再帰・Solidity出力。ロールアップ・本案件の集約(M2)"),
])

# S4 A② SNARK系（後半）
s = add_slide(); title(s, "A. 回路を書いてSNARK証明（2）")
bullets(s, TOP, [
    (0, "Noir（＋Barretenberg） = Rust風の書きやすい高水準言語"),
    (1, "Aztec製。中間表現ACIR→bb(UltraHonk)。準備は1回きり。zk-email/パスポート系"),
    (0, "halo2 = 表現力の高い回路が書けるRust証明系（PLONK系）"),
    (1, "元Zcash→Ethereum財団PSE(KZG版)。chip/gadget・lookup。Zcash Orchard/Scroll"),
], size0=16.5)

# S5 B STARK・再帰・Folding
s = add_slide(); title(s, "B. STARK・再帰・Folding（集約向き）")
bullets(s, TOP, [
    (0, "Plonky2 / Plonky3 = 準備不要で再帰が速いSTARK系（PLONK＋FRI）"),
    (1, "Polygon Zero製。Goldilocks体で高速。Polygon zkEVM"),
    (0, "Nova / HyperNova（＋Sonobe） = Folding（畳み込み）集約方式"),
    (1, "Microsoft Research発。省メモリ。長い反復計算・端末側集約"),
    (0, "Cairo（＋Stwo） = StarkWareのSTARK言語＋VM（Starknetの実行環境）"),
    (1, "準備不要・Poseidon速い。モバイル実証(FibRace)。検証はStarknet前提"),
])

# S6 C zkVM ＋ D 橋渡し
s = add_slide(); title(s, "C. zkVM ／ D. モバイルへの橋渡し")
bullets(s, TOP, [
    (0, "RISC Zero / SP1 = 普通のプログラム(Rust)の実行そのものを証明するzkVM"),
    (1, "RISC-VをSTARKで証明。回路設計が要らない。証明は重くサーバ/GPU前提"),
    (0, "Mopro = 既存の証明器をモバイルアプリに載せる“橋渡し”ツールキット"),
    (1, "Ethereum財団PSE主導。circom/halo2/Noirを iOS/Android/Flutter バインディング化"),
], size0=16.5)

# S7 E 支える部品
s = add_slide(); title(s, "E. これらを支える部品（土台ライブラリ）")
bullets(s, TOP, [
    (0, "circomlib = circom用の標準回路集（Poseidon・EdDSA・比較）。本案件が多用"),
    (0, "arkworks = RustのZK部品群（有限体・曲線・Groth16）。Nova/ark-circomの土台"),
    (0, "Barretenberg = AztecのC++証明バックエンド。Noirを動かす本体・WASM版も"),
    (0, "witnesscalc = circomのwitness生成を高速化するC++。モバイルで効く"),
], size0=16.5)

# S8 一言まとめ表
s = add_slide(); title(s, "一言まとめ")
table(s, TOP, [
    ["名前", "種別", "一言"],
    ["circom + snarkjs", "言語＋証明系(Groth16)", "ZK回路記述の定番・実績豊富"],
    ["rapidsnark", "高速プローバ", "circom回路を端末で速く証明"],
    ["gnark", "Go 証明系", "集約・再帰に強いサーバ向け"],
    ["Noir + Barretenberg", "言語＋証明系(Honk)", "書きやすい・準備不要"],
    ["halo2", "証明系(PLONK)", "高度だが難しい"],
    ["Plonky2/3", "STARK", "準備不要・再帰高速"],
    ["Nova / Sonobe", "Folding", "省メモリで逐次集約"],
    ["Cairo / Stwo", "STARK言語＋VM", "Starknetの土台"],
    ["RISC Zero / SP1", "zkVM", "普通のコードで書ける(重い)"],
    ["Mopro", "モバイル橋渡し", "既存証明器をアプリ化"],
], col_w=[2.3, 2.5, 3.8], fs=11, row_h=0.4)

OUT = os.path.join(os.path.dirname(__file__), "..", "week19", "slides_04_フレームワーク概要.pptx")
prs.save(OUT)
print(f"saved: {os.path.abspath(OUT)}  ({len(prs.slides._sldIdLst)} slides)")
