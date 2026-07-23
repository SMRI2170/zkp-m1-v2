#!/usr/bin/env python3
"""攻撃面 / 耐改竄の評価まとめスライド。

結果を『変えられない所（暗号的に堅い）』と『変えられる所（要対策）』に分け、
深刻度順に穴と対策を示す。

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
run(tf.paragraphs[0], "セキュリティ評価", 15, GRAY)
tf = tbox(s, 0.88, 2.75, 8.4, 1.4)
run(tf.paragraphs[0], "攻撃面と耐改竄", 30, INK, bold=True)
hrule(s, 4.2, l=0.92, w=4.8, color=ACCENT)
tf = tbox(s, 0.92, 4.38, 8.2, 1.6)
run(tf.paragraphs[0], "結果を『変えられない所』と『変えられる所』を正直に洗い出す", 14, INK)
p = tf.add_paragraph(); p.space_before = Pt(6)
run(p, "結論: 中身のすり替えは堅い。入力真正性と信頼の置き所に穴", 12, GRAY, font=MONO)

# 2 変えられない
s = add_slide()
title(s, "変えられない（暗号的に堅い）")
tf = tbox(s, 0.7, 1.5, 8.7, 3.2)
bullet(tf, "偽の public signals に対する proof の偽造（Groth16健全性・正直な設定前提）", first=True)
bullet(tf, "輸送中の public signal 改ざん → 検証で落ちる（Spike A 実証）")
bullet(tf, "集約カウントの捏造（入力集合を固定すれば集約proofが強制）")
bullet(tf, "チェーン記録の不変性（正直な合意前提）")
codebox(s, 0.7, 4.7, 8.6, 1.4, [
    "中身のすり替え … ✕ 不可能（暗号）",
    "但し前提: 『正直なトラステッドセットアップ』『正直な合意』",
])
tf = tbox(s, 0.7, 6.3, 8.7, 0.5)
run(tf.paragraphs[0], "→ 前提が崩れると堅さも崩れる（次ページ）", 12, GRAY)

# 3 変えられる一覧
s = add_slide()
title(s, "変えられる（要対策）— 深刻度順")
table(s, 0.7, 1.45, 8.6, [
    ["#", "穴", "深刻度"],
    ["1", "トラステッドセットアップが単一・決定論的 → 誰でも偽造可", "★最重要"],
    ["2", "入力真正性: 端末がRSSI/GPS/検知を偽って入力できる", "★高"],
    ["3", "Sybil: K台の登録端末結託で偽合意（M2は登録未検証）", "高"],
    ["4", "検閲: 集約者の間引き / バリデータ共謀", "中"],
    ["5", "Owner集権: 登録・freshnessを全掌握", "中"],
    ["6", "物理層: 中継/協調端末/GPS詐称", "中(一部限界)"],
    ["7", "freshnessが下限のみ / zkML不在", "低〜中"],
], col_w=[0.5, 6.3, 1.8], fs=10.5, row_h=0.5)

# 4 ★1 トラステッドセットアップ
s = add_slide()
title(s, "★1 トラステッドセットアップ（最重要）")
tf = tbox(s, 0.7, 1.4, 8.7, 1.6)
bullet(tf, "ビルドは powersoftau new + 決定論的 contribute で zkey を生成", first=True)
bullet(tf, "エントロピーがスクリプトに書かれている＝トラップドアが復元可能", bold=True)
bullet(tf, "→ 誰でも任意の proof を偽造できる（＝全体が無意味になりうる）", bold=True)
codebox(s, 0.7, 3.35, 8.6, 1.3, [
    'snarkjs zkey contribute ... -e="...deterministic..."   # ← 秘密が既知',
    "gnark 集約回路の setup も同様（単一）",
])
tf = tbox(s, 0.7, 4.9, 8.7, 1.6)
subhead(tf, "対策", 0)
bullet(tf, "本番は多人数MPCセレモニー（Powers of Tau + phase2）", first=True, bold=True)
sub(tf, "現状の zkey はデモ専用。最優先で塞ぐべき")

# 5 ★2 入力真正性
s = add_slide()
title(s, "★2 入力の真正性（デバイス側）")
tf = tbox(s, 0.7, 1.4, 8.7, 2.4)
bullet(tf, "measured_range_cm・自端末GPS・映像検知(score) は端末が自由に渡せる private入力", first=True)
sub(tf, "改造アプリで整合/within30/検知を捏造できる")
bullet(tf, "ドローン署名(M3)も drone_auth_enabled=0（未署名RemoteID＝DJI現状）だと自己申告に戻る")
bullet(tf, "映像検知は zkML 不在＝『1』と入れれば通る")
tf = tbox(s, 0.7, 4.1, 8.7, 2.4)
subhead(tf, "対策", 0)
bullet(tf, "端末アテステーション（Android Key Attestation / iOS App Attest）※ネイティブ未実装", first=True, bold=True)
bullet(tf, "署名付きRemoteID（DRIP）/ GNSS認証（OSNMA）/ zkML(ezkl)")
sub(tf, "『K台合意＝真正』を本当に成立させる核。多witnessはこれと組んで初めて効く")

# 6 Sybil / 検閲 / Owner
s = add_slide()
title(s, "3-5 Sybil / 検閲 / Owner集権")
tf = tbox(s, 0.7, 1.4, 8.7, 5.0)
subhead(tf, "Sybil（結託）", 0)
bullet(tf, "K台の登録端末を握れば偽合意。M2集約は登録を検証しない（distinctのみ）", first=True)
sub(tf, "対策: 端末アテステーション / ステーク / M2に登録Merkleメンバーシップ")
subhead(tf, "検閲・選択（結果の間引き）")
bullet(tf, "M2集約者が矛盾票を落とす / 許可型でもバリデータ・クォーラム共謀", first=True)
sub(tf, "対策: 包含性証明 / M1直接フォールバック（実演済） / 正直クォーラム前提")
subhead(tf, "Owner の中央集権")
bullet(tf, "owner が登録・minFreshness を全掌握 → compromise=全制御", first=True)
sub(tf, "対策: multisig / timelock / ガバナンス分散")

# 7 物理層 / freshness / zkML
s = add_slide()
title(s, "6-8 物理層 / 新鮮さ / zkML")
tf = tbox(s, 0.7, 1.4, 8.7, 5.0)
subhead(tf, "物理層（RSSI固有）", 0)
bullet(tf, "中継/ワームホール: 本物信号を中継 → RSSIは中継点を反映、検知不可（原理的限界）", first=True)
bullet(tf, "協調マルチ端末 / witnessのGPSスプーフィング")
sub(tf, "対策: TDoA/実測裏取り / GNSS認証 / 端末アテステーション")
subhead(tf, "新鮮さが下限のみ")
bullet(tf, "freshness >= minFreshness だけ。上限・ブロックハッシュ束縛なし → グラインディング余地", first=True)
sub(tf, "対策: freshness を直近ブロックハッシュに束縛")
subhead(tf, "zkML 不在")
bullet(tf, "検知は推論を証明していない → 対策: ezkl 等でモデル実行を証明", first=True)

# 8 優先順位
s = add_slide()
title(s, "塞ぐ優先順位")
codebox(s, 0.7, 1.5, 8.6, 2.7, [
    "1. MPCセレモニーで本番zkey        ← 最優先（無しでは全体が無意味）",
    "2. 端末アテステーション + 署名RemoteID  ← 入力真正性の核",
    "3. M2に登録メンバーシップ + 包含性証明  ← Sybil + 検閲",
    "4. owner を multisig/timelock,",
    "   freshness をブロックハッシュ束縛      ← 手が届きやすい",
])
tf = tbox(s, 0.7, 4.5, 8.7, 2.0)
subhead(tf, "まとめ", 0)
bullet(tf, "すり替え（暗号）＝不可。だが①セットアップ ②入力真正性 が結果を変えられる最大の穴",
       first=True, bold=True)
bullet(tf, "耐改竄を名乗るには ①MPC化 と ②真正性(M3) が必須")
sub(tf, "多witness・M2・許可型チェーンは、これらが揃って初めて意味を持つ")

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "week18")
os.makedirs(OUT_DIR, exist_ok=True)
out_path = os.path.join(OUT_DIR, "security_attack_surface.pptx")
prs.save(out_path)
print(f"saved: {os.path.abspath(out_path)}  ({len(prs.slides._sldIdLst)} slides)")
