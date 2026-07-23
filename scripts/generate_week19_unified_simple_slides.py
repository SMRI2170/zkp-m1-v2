#!/usr/bin/env python3
"""week19 統合デッキ（シンプル版）— 要点だけを1テーマ1枚で（進捗第11回スタイル）。"""

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
L, W, TOP = 0.7, 8.6, 1.4


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
    tf = s.shapes.add_textbox(Inches(0.68), Inches(0.44), Inches(8.7), Inches(0.8)).text_frame
    tf.word_wrap = True
    run(tf.paragraphs[0], text, 24, INK, bold=True)
    hrule(s, 1.18)


def _vlen(t):
    return int(sum(0.5 if ord(c) < 0x3000 else 1.0 for c in t))


def bullets(s, y, items, size0=17, size1=15):
    tf = s.shapes.add_textbox(Inches(L), Inches(y), Inches(W), Inches(0.4)).text_frame
    tf.word_wrap = True
    h = 0.0
    for i, (lv, text) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_before = Pt(0 if i == 0 else (8 if lv == 0 else 4))
        size = size0 if lv == 0 else size1
        run(p, ("■ " if lv == 0 else "　　・ "), size, INK); run(p, text, size, INK)
        cpl = max(14, int(600 / size)); lh = size * 1.55 / 72.0
        h += max(1, -(-_vlen(text) // cpl)) * lh + (0.1 if i else 0)
    return y + h + 0.14


def code(s, y, lines, w=W, fs=13.5):
    lh = fs * 1.75 / 72.0
    bh = lh * len(lines) + 0.28
    box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(L), Inches(y), Inches(w), Inches(bh))
    box.fill.solid(); box.fill.fore_color.rgb = CODEBG
    box.line.color.rgb = RULE; box.line.width = Pt(0.75); box.shadow.inherit = False
    tf = box.text_frame; tf.word_wrap = True
    tf.margin_left = Pt(10); tf.margin_right = Pt(8); tf.margin_top = Pt(8); tf.margin_bottom = Pt(8)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_before = Pt(0 if i == 0 else 3)
        run(p, ln, fs, INK, font=MONO)
    return y + bh + 0.16


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


def table(s, y, rows, col_w, fs=12.5, row_h=0.46):
    nr, nc = len(rows), len(rows[0])
    gtbl = s.shapes.add_table(nr, nc, Inches(L), Inches(y), Inches(sum(col_w)), Inches(row_h * nr))
    tbl = gtbl.table; tbl.first_row = False; tbl.horz_banding = False
    for ci, cw in enumerate(col_w):
        tbl.columns[ci].width = Inches(cw)
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = tbl.cell(ri, ci)
            cell.fill.solid(); cell.fill.fore_color.rgb = WHITE
            cell.margin_left = Pt(6); cell.margin_right = Pt(3)
            cell.margin_top = Pt(1); cell.margin_bottom = Pt(1)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            _cell_border(cell)
            run(cell.text_frame.paragraphs[0], str(val), fs, INK, bold=(ri == 0))
    return y + row_h * nr + 0.16


# ════════════════════════════════════════════════════════════════════════════
# S1 表紙
s = add_slide(number=False)
tf = s.shapes.add_textbox(Inches(0.9), Inches(2.5), Inches(8.3), Inches(1.5)).text_frame
tf.word_wrap = True
run(tf.paragraphs[0], "zk-UAV なりすまし検知", 31, INK, bold=True)
p = tf.add_paragraph(); p.space_before = Pt(4)
run(p, "多端末ZK集約とモバイル実装（要点）", 20, INK, bold=True)
hrule(s, 4.5, l=0.92, w=5.6)
tf = s.shapes.add_textbox(Inches(0.92), Inches(4.66), Inches(8.2), Inches(0.6)).text_frame
run(tf.paragraphs[0], "week19 統合（シンプル版）", 14, GRAY)

# S2 研究の全体像
s = add_slide(); title(s, "研究の全体像")
bullets(s, TOP, [
    (0, "ドローン無改造で、複数端末のRSSIから放送位置の真偽を判定し、"),
    (0, "各端末のZK証明を1つに集約してブロックチェーンに記録"),
    (0, "3本柱"),
    (1, "物理検知(RSSI) / ゼロ知識証明(座標は秘匿) / 多端末合意＋チェーン(改ざん・検閲耐性)"),
])

# S3 背景と検知原理
s = add_slide(); title(s, "背景と検知原理")
bullets(s, TOP, [
    (0, "RemoteIDは自己申告・署名なし → 位置フィールドの書換でなりすまし"),
    (0, "各端末が2つの距離を突き合わせ"),
    (1, "d_claim(放送位置と自GPSの幾何) と d_meas(RSSI推定) が乖離 → 詐称"),
    (0, "小さな詐称はノイズ以下 → 分散した複数端末の K-of-N 合意で検知（√N）"),
])

# S4 焦点
s = add_slide(); title(s, "本デッキの焦点")
y = code(s, TOP, [
    "各端末: RSSIで真偽判定 → ZK証明（座標秘匿）",
    "  → 複数端末を1つに集約 → チェーンで trusted / spoofAlert",
])
y = bullets(s, y + 0.12, [
    (0, "焦点 = 証明を「1つに集約」し「モバイルで生成」する土台の選定"),
    (0, "手法 → フレームワーク → モバイル → 決定 → 実測 → 安全"),
])

# S4b 結論（先に）
s = add_slide(); title(s, "この資料の位置づけと結論（先に）")
bullets(s, TOP, [
    (0, "位置づけ = 比較に基づく「研究方針の決定」資料（結論を先に示す）"),
    (0, "① 端末証明は Mopro で標準化（現行 circom 維持・移行最小）"),
    (0, "② 集約の端末寄せを Nova/Folding で検証（省メモリ）"),
    (0, "③ 必要なら Noir で ★1(トラステッドセットアップ)を根治（gas増は覚悟）"),
    (0, "以降 = この結論に至る根拠（手法・比較・実測・安全性）"),
])

# S5 手法の全体像
s = add_slide(); title(s, "手法の全体像（4つの層）")
y = code(s, TOP, [
    "層1  ZKPで何ができるか（秘匿したまま正しさを証明）",
    "層2  証明系（Groth16 / PLONK / STARK / Folding）",
    "層3  複数の証明をまとめる手法（本案件の肝）",
    "層4  検証・共有（オンチェーン / DA層）",
])
y = bullets(s, y + 0.12, [
    (0, "フレームワークは層2〜3を実装する乗り物。先に手法を決める"),
])

# S6 集約の手法
s = add_slide(); title(s, "集約の手法（層3）")
y = table(s, TOP, [
    ["手法", "オンチェーン", "現状"],
    ["オンチェーン集計(K-of-N)", "台数分 O(N)", "実装済 M1"],
    ["再帰的証明合成", "1回・定数", "実装済 M2"],
    ["Folding(Nova系)", "最終1回", "未（端末寄せ候補）"],
], col_w=[3.4, 2.4, 2.8], fs=13, row_h=0.55)
y = bullets(s, y + 0.15, [
    (0, "集計・再帰は実装済。未検討で価値ありは Folding（端末側で省メモリ集約）"),
])

# S7 フレームワーク早見表
s = add_slide(); title(s, "フレームワーク早見表")
y = table(s, TOP, [
    ["フレームワーク", "エンジン", "事前準備", "モバイル", "一言"],
    ["circom+rapidsnark", "Groth16", "回路別", "○", "現行の定番・安い検証"],
    ["Noir+Barretenberg", "Honk", "不要", "◎", "準備不要・速い・gas高"],
    ["gnark", "Groth16/PLONK", "回路別", "✕", "集約(サーバ)"],
    ["Nova/Sonobe", "Folding", "ほぼ不要", "◎", "端末側集約向き"],
    ["Mopro", "(包む)", "—", "◎", "証明系でなく橋渡し"],
], col_w=[2.5, 1.9, 1.3, 1.3, 1.9], fs=12.5, row_h=0.5)
y = bullets(s, y + 0.1, [
    (0, "主軸 = 端末は Mopro＋circom/Noir、集約は gnark or Folding、EVM前提"),
], size0=15.5)

# S8 モバイル
s = add_slide(); title(s, "モバイルで動かすには")
y = table(s, TOP, [
    ["FW", "難易度", "理由"],
    ["circom / Noir", "★☆☆ 易", "Mopro公式Flutter対応"],
    ["halo2 / Cairo", "★★☆ 中", "回路が難しい / 土台がStarknet"],
    ["Plonky2 / Nova", "★★★ やや難", "自前FFIが必要"],
    ["gnark / RISC Zero", "★★★ 難", "端末証明に不向き"],
], col_w=[2.6, 1.6, 4.4], fs=12.5, row_h=0.52)
y = bullets(s, y + 0.12, [
    (0, "Mopro公式対応は circom / halo2 / Noir → 現行もNoirも「易」でリスク低"),
], size0=15.5)

# S9 決定
s = add_slide(); title(s, "決定 — 段階的アプローチ")
bullets(s, TOP, [
    (0, "フェーズ1（すぐ）= Mopro でモバイル標準化（現行 circom のまま）"),
    (0, "フェーズ2（並行・研究）= 集約の端末寄せを Nova/Folding で検証"),
    (0, "フェーズ3（条件付き）= ★1根治のため Noir 評価（gas増を許容できる場合のみ）"),
])

# S10 実装検証① 実測
s = add_slide(); title(s, "実装検証① — circom vs Noir（暫定比較）")
y = table(s, TOP, [
    ["項目", "circom（Groth16）", "Noir（UltraHonk）"],
    ["Poseidon 1回（同機能・公平）", "415制約", "404ゲート ＝ ほぼ同等"],
    ["セットアップ", "回路別セレモニー要", "不要（universal）"],
    ["オンチェーン検証", "≈348k gas", "≈2.4M gas（文献）"],
    ["証明生成 ※規模が違う", "≈1.4s（フル11.8k）", "0.11s（小PoC・署名なし）"],
], col_w=[2.9, 2.9, 2.8], fs=12, row_h=0.52)
y = bullets(s, y + 0.1, [
    (0, "公平比較は Poseidon(同機能)のみ＝ほぼ同等。0.11s vs 1.4s は規模が違い直接比較不可"),
    (0, "EdDSAは Noir 未実測 → 同条件の完全比較は今後"),
], size0=14)

# S11 実装検証② Mopro
s = add_slide(); title(s, "実装検証② — Mopro（実機ビルド確認済み）")
bullets(s, TOP, [
    (0, "確認済み = circom プローバを Flutter/Android の APK（53MB）までビルド"),
    (1, "arm64ネイティブ証明器(.so 3MB) / generateCircomProof を呼ぶ Flutterアプリ"),
    (0, "未達（次段）= 実機 flutter run でオンデバイス証明の時間を実測"),
    (0, "＝“実機で証明が回った”ではなく“アプリまで作れた”段階と区別"),
    (0, "教訓 = AndroidでNoirはZig必須 → Androidはcircomが楽"),
])

# S12 信頼モデル
s = add_slide(); title(s, "信頼モデル — 何を替えると何が変わるか")
y = code(s, TOP, [
    "① セットアップ  … 証明系で変わる（Groth16=回路別 / STARK=不要）",
    "② プローバ      … 集約手法で変わる（再帰/Foldingは分散）",
    "③ 集約者(検閲)  … 変わらない → 網羅性(#3b) or 合意",
    "④ 入力の真正性  … 変わらない → アテステーション/登録",
])
y = bullets(s, y + 0.12, [
    (0, "改ざんは暗号で不可。③検閲・④入力はフレームワークを替えても消えない"),
])

# S13 まとめ・今後
s = add_slide(); title(s, "まとめ・今後")
bullets(s, TOP, [
    (0, "まとめ = 端末は Mopro、集約は gnark継続 or Nova、★1消すなら Noir 段階導入"),
    (1, "検知91%(合成)・Mopro で circom を APK までビルド・Poseidon 同等 を実証"),
    (0, "今後"),
    (1, "実機 DJI 較正（最重要）／ Folding で集約の端末寄せ ／ DA層接続 ／ Noir 評価"),
])

OUT = os.path.join(os.path.dirname(__file__), "..", "week19", "slides_統合_week19_シンプル.pptx")
prs.save(OUT)
print(f"saved: {os.path.abspath(OUT)}  ({len(prs.slides._sldIdLst)} slides)")
