#!/usr/bin/env python3
"""プロジェクト総まとめスライド（現状の完全版）。

全体像 → 実装済み一覧 → 主要実測値 → 耐改竄の到達点 → アーキテクチャ → 残課題 → 設計思想。

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
    hrule(s, 1.08)


def subhead(tf, text, space_before=13):
    p = tf.add_paragraph(); p.space_before = Pt(space_before)
    run(p, text, 14, ACCENT, bold=True); return p


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
tf = tbox(s, 0.9, 2.05, 8.2, 0.5)
run(tf.paragraphs[0], "プロジェクト総まとめ（2026-07）", 15, GRAY)
tf = tbox(s, 0.88, 2.6, 8.4, 1.9)
run(tf.paragraphs[0], "UAV RemoteID 検証システム", 30, INK, bold=True)
p = tf.add_paragraph(); p.space_before = Pt(4)
run(p, "多端末 × ZK × ブロックチェーン ＋ 耐改竄", 22, INK, bold=True)
hrule(s, 4.6, l=0.92, w=5.8, color=ACCENT)
tf = tbox(s, 0.92, 4.78, 8.2, 1.4)
run(tf.paragraphs[0], "RemoteIDの自己申告を、改造なしで裏取りし、改ざん・検閲・偽装に耐える", 13.5, INK)

# 2 全体像
s = add_slide()
title(s, "全体像 — 3層 + 真正性")
codebox(s, 0.7, 1.4, 8.6, 3.9, [
    "[端末] rapidsnark で Groth16 証明（座標は秘匿、条件の成否だけ公開）",
    "   ・within30 / consistency(放送vs実測RSSI) / drone_auth / device署名",
    "      │  同一drone_id を共有する N 証明",
    "      ▼",
    "[集約] gnark 再帰集約: N証明を1つに + 関係強制",
    "   ・同一ドローン / 端末相異 / 整合集計 / 登録メンバーシップ / 網羅性",
    "      │  集約proof 1個",
    "      ▼",
    "[チェーン] Groth16検証 + M3検査 + K台集計 → trusted / spoof",
])
tf = tbox(s, 0.7, 5.55, 8.7, 1.0)
bullet(tf, "軸: 「接近の証明」ではなく「なりすまし検出の証明」", size=13, first=True, bold=True)

# 3 実装済み一覧
s = add_slide()
title(s, "実装済み — 機能")
table(s, 0.7, 1.4, 8.6, [
    ["領域", "内容", "状態"],
    ["検知", "RSSI整合(相対許容/中央値) + 映像/音響回路", "✅"],
    ["合意基盤(M1)", "AttestationRegistry + Groth16検証", "✅ 20/21テスト"],
    ["集約(M2)", "gnark再帰集約 + 関係強制 + membership", "✅ gas354k定数"],
    ["真正性(M3)", "ドローン署名/新鮮さ/端末アテステーション", "✅"],
    ["アプリ", "実機Pixel8で起動・RSSI判定・権限修正", "✅"],
    ["許可型チェーン", "Besu QBFT構成 + M1直接提出 実演", "✅"],
], col_w=[1.8, 4.9, 1.9], fs=10.5, row_h=0.5)

# 4 主要実測値
s = add_slide()
title(s, "主要な実測値")
tf = tbox(s, 0.7, 1.35, 8.7, 2.6)
subhead(tf, "検知（RSSIなりすまし・合成ROC）", 0)
bullet(tf, "位置詐称30mを N=5 で 91% / 単独64%→8台98% / 較正ズレで崩壊(91→7.7%)", first=True)
subhead(tf, "集約（gnark 再帰・emulated BN254）")
bullet(tf, "1証明 2.16M制約 20s / N=3 6.4M 59s / +membership 7.2M 62s / verify 8ms", first=True)
bullet(tf, "オンチェーン集約検証 gas 354k（N非依存）← M1のO(N)に優位")
tf = tbox(s, 0.7, 4.2, 8.7, 2.3)
subhead(tf, "回路 / テスト", 0)
bullet(tf, "witness回路 public18・約18k制約・セレモニー(ZKey Ok)", first=True)
bullet(tf, "Hardhat 21/21 / 端末アテステーション検証 8/8 / membership・completeness OK")

# 5 耐改竄の到達点
s = add_slide()
title(s, "耐改竄の到達点")
table(s, 0.7, 1.4, 8.6, [
    ["攻撃面", "対策", "状態"],
    ["★1 セットアップ偽造", "多者セレモニー(真乱数+ビーコン+監査)", "✅"],
    ["★2 入力真正性", "ドローン署名RemoteID + 端末アテステーション", "✅"],
    ["3a Sybil", "M2に登録メンバーシップ(Merkle)", "✅ 集約統合"],
    ["3b 検閲(間引き)", "包含性=提出集合ルートの一致証明", "✅ 核"],
    ["4 owner集権", "Ownable2Step + Timelock", "✅"],
    ["中継/物理層", "RSSIでは限界 → TDoA/実測(将来)", "△ 限界明示"],
], col_w=[2.5, 4.6, 1.5], fs=10.5, row_h=0.5)
tf = tbox(s, 0.7, 5.5, 8.7, 1.0)
bullet(tf, "改ざんは暗号で不可 / 検閲は網羅性で不可 / 入力は真正性で裏取り / 鍵は正規セレモニー",
       size=11.5, first=True, bold=True)

# 6 残課題
s = add_slide()
title(s, "残課題（本統合・実接続）")
tf = tbox(s, 0.7, 1.45, 8.7, 3.2)
bullet(tf, "3a/3b 機構の emulated 集約回路への本統合（各 ~16分の setup 再実行）", first=True)
sub(tf, "membership は統合済。completeness は核をテスト済で統合手順を明記")
bullet(tf, "DA層(Ethereum blob / Celestia)の実接続（提出集合コミット）")
bullet(tf, "端末アテステーションの実機(StrongBox)での動作確認")
bullet(tf, "実機DJIでのRSSI較正（A/n/σ確定）→ 閾値・K の実データ化")
bullet(tf, "M2集約の submitAggregate 契約経路（deviceRoot/SubmissionRoot 照合）")
tf = tbox(s, 0.7, 5.0, 8.7, 1.5)
subhead(tf, "本質的な前提", 0)
bullet(tf, "署名付きRemoteID(DRIP)の普及 / 正直クォーラム or 1-of-N の信頼", first=True)

# 7 設計思想
s = add_slide()
title(s, "一貫した設計思想")
tf = tbox(s, 0.7, 1.5, 8.7, 4.8)
bullet(tf, "座標や特徴は隠し、条件の成否(0/1)だけ公開（プライバシー）", first=True)
bullet(tf, "各層は前の層の穴を埋める必然として積み上がる（機能の寄せ集めでない）")
bullet(tf, "重い計算は端末(rapidsnark)、繋ぐのは集約(gnark)、記録はチェーン、で分業")
bullet(tf, "耐改竄は多層: 暗号(すり替え) + 合意/網羅性(検閲) + 真正性(入力) + 分散(集権)")
bullet(tf, "正直に限界を明示: 中継攻撃・DRIP普及・信頼前提は設計に記載")
tf = tbox(s, 0.7, 5.4, 8.7, 1.0)
run(tf.paragraphs[0], "机上・PoCで可能な範囲を網羅。残るは本統合・実機・DA実接続。", 13, INK, bold=True)

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "week18")
os.makedirs(OUT_DIR, exist_ok=True)
out_path = os.path.join(OUT_DIR, "final_summary.pptx")
prs.save(out_path)
print(f"saved: {os.path.abspath(out_path)}  ({len(prs.slides._sldIdLst)} slides)")
