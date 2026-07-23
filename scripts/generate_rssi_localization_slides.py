#!/usr/bin/env python3
"""RSSI による位置詐称検知（全21枚・改訂版）。

構成元: week18/SLIDES_rssi_localization.md（教授レビュー反映版）
方針: 主役 = K-of-N 合意 / 補助 = 多辺測量。実装→評価の順。評価結果はグラフ。
デザイン（進捗第11回スタイル）: 白背景・黒文字・Yu Gothic / Courier New、4:3。
  箇条書き ■=第1階層 / ・=第2階層。式・コードは薄グレー枠。結果ページは「シミュレーション」明示。
評価数値は scripts/rssi/eval_spoof_detection.py の実行結果（合成データ, 試行3000）。
"""

import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION

INK = RGBColor(0x1A, 0x1A, 0x1A)
GRAY = RGBColor(0x55, 0x55, 0x55)
RULE = RGBColor(0xCC, 0xCC, 0xCC)
CODEBG = RGBColor(0xF7, 0xF7, 0xF7)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BLUE = RGBColor(0x33, 0x3E, 0x6E)
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


def simnote(s, y, text="※ シミュレーション結果（合成データ・試行3000回・A=−40dBm, n=2.5）"):
    tf = s.shapes.add_textbox(Inches(L), Inches(y), Inches(W), Inches(0.3)).text_frame
    tf.word_wrap = True
    run(tf.paragraphs[0], text, 12, GRAY)
    return y + 0.34


def _vlen(text):
    return int(sum(0.5 if ord(c) < 0x3000 else 1.0 for c in text))


def bullets(s, y, items, size0=16.5, size1=14.5):
    tf = s.shapes.add_textbox(Inches(L), Inches(y), Inches(W), Inches(0.4)).text_frame
    tf.word_wrap = True
    h = 0.0
    for i, (lv, text) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_before = Pt(0 if i == 0 else (6 if lv == 0 else 3))
        size = size0 if lv == 0 else size1
        marker = "■ " if lv == 0 else "　　・ "
        run(p, marker, size, INK); run(p, text, size, INK)
        cpl = max(14, int(590 / size))          # 1行あたり全角文字数（サイズ依存）
        lh = size * 1.5 / 72.0                   # 行高[inch]
        h += max(1, -(-_vlen(text) // cpl)) * lh + (0.08 if i else 0)
    return y + h + 0.12


def code(s, y, lines, w=W, fs=13):
    lh = fs * 1.7 / 72.0
    bh = lh * len(lines) + 0.26
    box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(L), Inches(y), Inches(w), Inches(bh))
    box.fill.solid(); box.fill.fore_color.rgb = CODEBG
    box.line.color.rgb = RULE; box.line.width = Pt(0.75); box.shadow.inherit = False
    tf = box.text_frame; tf.word_wrap = True
    tf.margin_left = Pt(10); tf.margin_right = Pt(8); tf.margin_top = Pt(7); tf.margin_bottom = Pt(7)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_before = Pt(0 if i == 0 else 2)
        run(p, ln, fs, INK, font=MONO)
    return y + bh + 0.14


def callout(s, x, y, w, h, head, body, head_color=BLUE, emph=False):
    box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    box.fill.solid(); box.fill.fore_color.rgb = WHITE
    box.line.color.rgb = (head_color if emph else RULE)
    box.line.width = Pt(1.5 if emph else 0.75); box.shadow.inherit = False
    tf = box.text_frame; tf.word_wrap = True
    tf.margin_left = Pt(10); tf.margin_right = Pt(10); tf.margin_top = Pt(8)
    run(tf.paragraphs[0], head, 15, head_color, bold=True)
    p = tf.add_paragraph(); p.space_before = Pt(6)
    run(p, body, 16 if emph else 14, INK, bold=emph)


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


def table(s, y, rows, col_w, fs=13, row_h=0.42):
    nr, nc = len(rows), len(rows[0])
    gtbl = s.shapes.add_table(nr, nc, Inches(L), Inches(y), Inches(sum(col_w)), Inches(row_h * nr))
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
            run(p, str(val), fs, INK, bold=(ri == 0))
    return y + row_h * nr + 0.14


def _style_chart(chart, legend=False, ymax=100, dlabels=False):
    chart.font.size = Pt(12); chart.font.name = FONT
    chart.has_title = False
    chart.has_legend = legend
    if legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(12)
    va = chart.value_axis
    va.minimum_scale = 0; va.maximum_scale = ymax
    va.has_major_gridlines = True
    va.tick_labels.font.size = Pt(11)
    ca = chart.category_axis
    ca.tick_labels.font.size = Pt(12)
    if dlabels:
        pl = chart.plots[0]; pl.has_data_labels = True
        pl.data_labels.font.size = Pt(11); pl.data_labels.number_format = '0"%"'
        pl.data_labels.number_format_is_linked = False


def line_chart(s, x, y, cx, cy, cats, series, ymax=100, legend=False):
    cd = CategoryChartData(); cd.categories = cats
    for name, vals in series.items():
        cd.add_series(name, vals)
    gf = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(x), Inches(y),
                            Inches(cx), Inches(cy), cd)
    _style_chart(gf.chart, legend=legend, ymax=ymax)
    return gf.chart


def bar_chart(s, x, y, cx, cy, cats, series, ymax=100, legend=False, dlabels=True):
    cd = CategoryChartData(); cd.categories = cats
    for name, vals in series.items():
        cd.add_series(name, vals)
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(x), Inches(y),
                            Inches(cx), Inches(cy), cd)
    _style_chart(gf.chart, legend=legend, ymax=ymax, dlabels=dlabels)
    return gf.chart


def label(s, x, y, w, text, size=12.5, color=GRAY, bold=False, align=PP_ALIGN.CENTER):
    tf = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(0.3)).text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]; p.alignment = align
    run(p, text, size, color, bold=bold)


# ════════════════════════════════════════════════════════════════════════════
# S1 表紙
s = add_slide(number=False)
tf = s.shapes.add_textbox(Inches(0.9), Inches(2.5), Inches(8.2), Inches(1.4)).text_frame
tf.word_wrap = True
run(tf.paragraphs[0], "RSSI による位置詐称検知", 30, INK, bold=True)
hrule(s, 3.9, l=0.92, w=5.2)
tf = s.shapes.add_textbox(Inches(0.92), Inches(4.05), Inches(8.2), Inches(0.9)).text_frame
tf.word_wrap = True
run(tf.paragraphs[0], "― ドローン無改造で、受信側だけで放送位置の真偽を検知 ―", 15, GRAY)
p = tf.add_paragraph(); p.space_before = Pt(6)
run(p, "主役: K-of-N 合意 ／ 補助: 多辺測量", 13, BLUE, bold=True)
tf = s.shapes.add_textbox(Inches(0.92), Inches(6.4), Inches(8.0), Inches(0.5)).text_frame
run(tf.paragraphs[0], "week18 / RSSI spoof detection", 12, GRAY)

# S2 背景・攻撃例（左右図）
s = add_slide(); title(s, "背景 — 放送される位置は「自己申告」")
# 左：攻撃の図
label(s, 0.7, 1.35, 4.3, "受信端末が見るのは放送位置だけ", 12, INK, bold=True, align=PP_ALIGN.LEFT)
a = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(1.15), Inches(2.55), Inches(0.28), Inches(0.28))
a.fill.solid(); a.fill.fore_color.rgb = INK; a.line.fill.background(); a.shadow.inherit = False
label(s, 1.5, 2.5, 3.2, "実際の発信位置 A", 11.5, INK, align=PP_ALIGN.LEFT)
b = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(3.15), Inches(3.75), Inches(0.28), Inches(0.28))
b.fill.solid(); b.fill.fore_color.rgb = WHITE; b.line.color.rgb = INK; b.line.width = Pt(1.5)
b.shadow.inherit = False
label(s, 3.5, 3.7, 1.7, "放送位置 B", 11.5, INK, align=PP_ALIGN.LEFT)
arr = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(1.55), Inches(3.02), Inches(1.5), Inches(0.3))
arr.rotation = 30; arr.fill.solid(); arr.fill.fore_color.rgb = RULE
arr.line.fill.background(); arr.shadow.inherit = False
label(s, 0.7, 4.5, 4.3, "攻撃者が位置フィールドを A→B に書換\n端末は B を表示（実際は A）",
      11.5, GRAY, align=PP_ALIGN.LEFT)
# 右：課題・目標
callout(s, 5.3, 1.6, 4.0, 1.5, "課題",
        "受信した位置情報だけでは、実際の電波発信位置との一致を確認できない。")
callout(s, 5.3, 3.4, 4.0, 1.6, "目標",
        "既存ドローンを改造せず、受信側だけで位置詐称を検知する。", emph=True)
label(s, 5.3, 5.3, 4.0, "手掛かり = 受信電波強度 RSSI と 自端末の GPS", 12, INK,
      bold=True, align=PP_ALIGN.LEFT)

# S3 提案方式の全体像
s = add_slide(); title(s, "提案方式の全体像 — 主役と補助")
y = bullets(s, TOP, [
    (0, "主役: K-of-N 合意 — 各端末の整合/矛盾判定を集約し、K 台一致で結論"),
    (0, "補助: 多辺測量 — 複数端末の距離から発信源位置を推定（好条件でのみ上乗せ）"),
    (0, "基盤: ゼロ知識証明＋ブロックチェーン — 座標を秘匿したまま合意を記録"),
])
y = code(s, y + 0.05, [
    "各端末: RSSI → 距離 d_meas ┐",
    "        放送位置 → 距離 d_claim ┘→ 整合/矛盾（単端末判定）",
    "                                   │",
    "   [主役] K-of-N 合意 ←─ 分散した複数端末の判定を集約",
    "   [補助] 多辺測量   ←─ 距離から発信源位置を推定して照合",
    "                                   │",
    "        ZKP 回路 → ブロックチェーンに trusted / spoofAlert を記録",
])
y = bullets(s, y + 0.05, [
    (0, "以降: 距離モデル(4-7) → なぜ複数端末(8) → 2方式(9-10) → 実装(11-14) → 評価(15-18)"),
], size0=14)

# S4 RSSI距離モデル
s = add_slide(); title(s, "RSSI 距離モデル — 電波強度から距離")
y = bullets(s, TOP, [(0, "距離とともに対数的に減衰する電波（log-distance path loss）")])
y = code(s, y, [
    "RSSI(d) = A − 10·n·log10(d)",
    "d_meas  = 10^((A − RSSI) / (10·n))     ← 逆に解けば距離",
])
y = bullets(s, y, [
    (0, "A = 1m 地点の RSSI、n = 伝搬指数（自由空間 2.0 / 市街地 2.5〜4）"),
    (0, "このRSSIならこの距離（A=−40dBm, n=2.5 の目安）"),
])
y = table(s, y, [
    ["受信 RSSI", "推定距離"],
    ["−65 dBm", "約 10 m"],
    ["−77 dBm", "約 30 m"],
    ["−90 dBm", "約 100 m"],
], col_w=[2.6, 2.6])

# S5 RSSI誤差（結論を大きく）
s = add_slide(); title(s, "RSSI 誤差 — 1台の推定は本質的に粗い")
callout(s, 0.7, 1.4, 8.6, 1.15, "結論",
        "RSSIで「30m」と推定しても、実距離は約 14〜63m になり得る", emph=True)
y = code(s, 2.85, [
    "距離の倍率 = 10^(k·σ / 10n) = 10^(2·4/25) ≈ 2.1 倍",
    "→ 30m ÷2.1 〜 30m ×2.1 = 約 14〜63m",
])
y = bullets(s, y, [
    (0, "仮定: RSSI 誤差の標準偏差 σ=4dB、95%区間を ±2σ として計算"),
    (1, "σ は実測前の文献・暫定仮定（実機較正で確定）"),
    (0, "dB 誤差が距離では掛け算的に効く（log スケール）ことが根本原因"),
])

# S6 距離比による単端末判定
s = add_slide(); title(s, "単端末判定 — 距離の「比」で照合")
y = bullets(s, TOP, [
    (0, "固定幅（±3m など）の破綻（近距離で緩く遠距離で厳しい）"),
    (0, "掛け算的な誤差ゆえ、ずれは比（倍率）で評価"),
])
y = code(s, y, [
    "ずれ = | log10(d_claim / d_meas) |",
    "整合 ⇔ d_meas / r ≤ d_claim ≤ d_meas × r     r = 2.1（暫定）",
])
y = bullets(s, y, [
    (0, "許容 r = 2.1 = 基準距離の 約48%〜210%（±2σ 由来、恣意的でない）"),
    (0, "回路では log を避け、この倍率帯の二乗比較で判定"),
])

# S7 時系列中央値集約
s = add_slide(); title(s, "時系列の中央値集約 — 単発ノイズをならす")
y = bullets(s, TOP, [
    (0, "マルチパス（反射）による単発 RSSI の飛び"),
    (0, "同一 UAS_ID の RSSI を M サンプル集め、中央値を採用"),
    (1, "外れ値へのロバスト性（平均は外れ値1つで引きずられる）"),
    (1, "実効的な標準偏差の縮小"),
    (0, "集約後の値を距離 d_meas に変換（M = 5〜10 を推奨）"),
])

# S8 複数端末が必要な理由
s = add_slide(); title(s, "なぜ複数端末が必要か — 小さな詐称はノイズ以下")
y = bullets(s, TOP, [(0, "30m 地点で放送位置を 5m ずらしても、電波強度の変化はごく小さい")])
y = code(s, y, ["ΔRSSI = 10·n·log10(30/25) = 25·log10(1.2) ≈ 2 dB   （< σ=4dB）"])
y = bullets(s, y, [
    (0, "嘘の信号 2dB < 雑音 4dB → 1台では埋もれる"),
    (0, "分散した複数端末で平均すると SNR が √N で改善（理論値）"),
])
y = table(s, y, [
    ["端末数 N", "SNR = √N·(2dB)/(4dB)"],
    ["1 台", "0.5"],
    ["5 台", "約 1.1"],
    ["12 台", "約 1.7"],
], col_w=[2.2, 4.0], row_h=0.34)
y = simnote(s, y, "※ 端末ごとの RSSI 誤差が独立・較正済みと仮定した理想条件での目安")
y = bullets(s, y, [(0, "小さな位置ずれの検知には、空間的に分散した複数端末が必要")])

# S9 K-of-N 合意方式（主役）
s = add_slide(); title(s, "主役方式 — K-of-N 合意")
y = bullets(s, TOP, [
    (0, "各端末が単端末判定で consistent / suspicious を出力"),
    (0, "分散した N 台の判定を集約し、しきい値 K で結論"),
])
y = code(s, y, [
    "consistent（整合）が K 台以上 → trusted",
    "suspicious（矛盾）が K 台以上 → spoofAlert",
])
y = bullets(s, y, [
    (0, "位置を明示的に解かず、判定の多数決で頑健に結論（本方式の主役）"),
    (0, "評価では連続版として「整合スコアの中央値」を指標に用いる"),
])

# S10 多辺測量方式（補助）
s = add_slide(); title(s, "補助方式 — 多辺測量による位置推定")
y = bullets(s, TOP, [
    (0, "複数端末の距離の連立で、発信源の水平位置 (x,y) を直接推定"),
    (0, "基準式との差で 2乗項（h² 含む）が消え、(x,y) の1次式に帰着"),
])
y = code(s, y, [
    "d_i² = (x−x_i)² + (y−y_i)² + h²",
    "d_i² − d_0² = (x_i²+y_i²−x_0²−y_0²) − 2[x(x_i−x_0)+y(y_i−y_0)]   ← 線形",
])
y = bullets(s, y, [
    (0, "推定位置 P_hat と放送位置 P_claim の残差 > 閾値 → 位置詐称"),
    (0, "閾値は正常データに対する FPR=5% を基準に決定"),
])

# S11 アプリ実装
s = add_slide(); title(s, "実装① — アプリ（オンデバイス測定・ログ）")
y = bullets(s, TOP, [
    (0, "Flutter アプリで受信 → RSSI 集約 → 単端末判定までを実行、Pixel 8 で動作"),
])
y = code(s, y, [
    "受信 → RSSI 集約（中央値） → d_meas → 整合判定 → CSV/JSON ログ",
])
y = bullets(s, y, [(0, "実機で確認した範囲（現時点）")])
y = table(s, y, [
    ["項目", "現状"],
    ["受信対象", "Wi-Fi ビーコン（OpenDroneID）の受信"],
    ["RSSI 取得", "スキャン結果から取得・集約まで動作"],
    ["整合判定", "アプリ内ロジックまで実装（実機で疎通確認）"],
    ["未実施", "実 DJI 機での較正・距離判定の実測評価"],
], col_w=[2.2, 6.0], fs=12.5, row_h=0.4)
label(s, 0.7, 6.7, 8.6, "ファイル: rssi_ranging.dart / rssi_logger.dart / main.dart",
      10, GRAY, align=PP_ALIGN.RIGHT)

# S12 多辺測量ソルバ実装
s = add_slide(); title(s, "実装② — 多辺測量ソルバの実装と単体検証")
y = bullets(s, TOP, [
    (0, "入力 = 端末座標 (x_i,y_i) と推定距離 d_i、出力 = 推定水平位置 (x,y)"),
    (0, "解法 = 線形化した連立式の最小二乗解（multilaterate2d）"),
])
y = bullets(s, y + 0.05, [
    (0, "単体検証"),
    (1, "ノイズなし = 真の発信源位置を再現（例: 端末を囲む配置で原点を復元）"),
    (1, "ノイズあり = σ 増加とともに位置誤差が増加"),
    (0, "評価ハーネスに組み込み、K-of-N 合意と同一条件で公平比較（→ 16枚目）"),
])
y = simnote(s, y + 0.05, "※ 位置誤差の定量値は評価ハーネスの残差分布で提示（S16 の方式比較）")

# S13 ZKP回路
s = add_slide(); title(s, "実装③ — ゼロ知識証明回路")
y = bullets(s, TOP, [
    (0, "座標・生 RSSI を秘匿したまま「整合の真偽」だけを証明"),
    (0, "remoteid_consistency 回路（相対許容版）"),
    (1, "非公開入力 = d_meas, d_claim（座標は回路の外に出さない）"),
    (1, "倍率帯 d_meas/r ≤ d_claim ≤ d_meas×r（r=2.1）の二乗比較"),
    (1, "公開出力 = consistency_ok（整合1 / 矛盾0）のみ"),
    (0, "回路規模 約650制約、witness 回路へ統合"),
])

# S14 多端末証明の集約
s = add_slide(); title(s, "実装④ — 多端末証明の集約と判定規則")
y = bullets(s, TOP, [(0, "同一 time bucket・同一ドローンの有効証明のみを集約")])
y = code(s, y, [
    "valid = 有効証明数（要件を満たす端末）",
    "suspicious ≥ K            → spoofAlert",
    "else if consistent ≥ K    → trusted",
    "else                      → insufficient（判定保留）",
])
y = bullets(s, y, [
    (0, "有効証明の必要条件（Sybil・重複対策）"),
    (1, "端末アテステーション（正規端末のみ）／ 1端末1票（重複排除）"),
    (1, "同一 time bucket ／ 位置的に分散していること"),
])

# S15 評価条件
s = add_slide(); title(s, "評価 — シミュレーション条件")
y = table(s, TOP, [
    ["項目", "条件"],
    ["真の発信源", "端末配置（半径40m）の中心付近、高度20m"],
    ["端末数 N", "1 / 3 / 5 / 8 / 12（掃引）"],
    ["RSSI ノイズ", "正規分布、σ = 2〜8 dB（暫定 4dB）"],
    ["詐称量 Δ", "5 / 10 / 20 / 30 / 50 / 100 m（掃引）"],
    ["評価指標", "AUC、FPR=5% 時の TPR（検知率）"],
    ["試行回数", "3000 回 / 条件（集約 M=8）"],
], col_w=[2.4, 6.2], fs=12.5, row_h=0.42)
y = simnote(s, y, "※ 実機データ取得前の合成データによる評価（設計値 r・K を決めるための基盤）")

# S16 方式比較結果
s = add_slide(); title(s, "評価結果① — 方式比較（K-of-N 合意 vs 多辺測量）")
bar_chart(s, 0.7, 1.45, 6.2, 4.3,
          ["Δ=10m", "Δ=20m", "Δ=30m", "Δ=50m"],
          {"K-of-N 合意": (31.0, 82.9, 95.4, 99.2),
           "多辺測量": (13.4, 59.8, 95.8, 99.9)},
          ymax=100, legend=True, dlabels=False)
label(s, 0.7, 5.78, 6.2, "縦軸 = 検知率 TPR(%)  / N=6, σ=4dB, FPR=5%", 12, GRAY)
tf = s.shapes.add_textbox(Inches(7.0), Inches(1.7), Inches(2.6), Inches(4.2)).text_frame
tf.word_wrap = True
run(tf.paragraphs[0], "現実ノイズ＋少数端末では K-of-N 合意が優位", 12, INK, bold=True)
for t in ["● 小さな詐称(Δ≤20m)ほど差が大きい",
          "● 多辺測量は低ノイズ/多端末でのみ同等",
          "● ゆえに主役=K-of-N、補助=多辺測量"]:
    p = tf.add_paragraph(); p.space_before = Pt(10); run(p, t, 12, INK)
simnote(s, 6.15)

# S17 Δ・N・σの結果
s = add_slide(); title(s, "評価結果② — 詐称量Δ・端末数N・ノイズσ")
label(s, 0.7, 1.35, 4.3, "検知率 TPR vs 詐称量 Δ（N=5）", 12, INK, bold=True)
line_chart(s, 0.7, 1.7, 4.3, 3.6, ["5", "10", "20", "30", "50", "100"],
           {"TPR": (10.0, 27.7, 74.7, 90.9, 97.8, 100.0)}, ymax=100)
label(s, 0.75, 5.3, 4.2, "横軸 Δ(m) / 縦軸 TPR(%)", 12, GRAY)
label(s, 5.1, 1.35, 4.2, "検知率 TPR vs 端末数 N（Δ=30m）", 12, INK, bold=True)
line_chart(s, 5.1, 1.7, 4.2, 3.6, ["1", "3", "5", "8", "12"],
           {"TPR": (63.6, 82.7, 90.5, 97.8, 99.4)}, ymax=100)
label(s, 5.15, 5.3, 4.2, "横軸 N(台) / 縦軸 TPR(%)", 12, GRAY)
y = bullets(s, 5.7, [
    (0, "ノイズσの影響: σ=2dB→98.9% / 4dB→91.2% / 6dB→68.0% / 8dB→49.1%（N=5,Δ=30m）"),
], size0=14)
simnote(s, 6.7)

# S18 較正誤差の結果（最重要）
s = add_slide(); title(s, "評価結果③ — 較正誤差が最大の弱点")
callout(s, 0.7, 1.35, 8.6, 0.95,
        "結論", "RSSI方式の最大の弱点は、端末数よりも較正誤差", emph=True)
bar_chart(s, 0.7, 2.5, 5.4, 3.4,
          ["較正一致", "n:2.5→2.0", "n:2.5→3.0", "A:+6dB", "A:−6dB"],
          {"TPR": (91.1, 7.7, 72.5, 8.0, 70.1)}, ymax=100, dlabels=True)
label(s, 0.7, 5.9, 5.4, "縦軸 = 検知率 TPR(%) / N=5, Δ=30m", 12, GRAY)
tf = s.shapes.add_textbox(Inches(6.3), Inches(2.6), Inches(3.1), Inches(3.4)).text_frame
tf.word_wrap = True
for t in ["● 真 n=2.5 に対し判定側が n=2.0 を使うと 91%→7.7%",
          "● A を +6dB 誤ると 91%→8%",
          "● 端末数を増やすより較正精度が支配的",
          "● 要求: A は数dB以内、n は ±0.5未満"]:
    p = tf.add_paragraph(); p.space_before = Pt(9); run(p, t, 12, INK)
simnote(s, 6.2)

# S19 脅威モデル・限界
s = add_slide(); title(s, "脅威モデルと限界")
y = table(s, TOP, [
    ["攻撃", "RSSI 方式での可否"],
    ["位置詐称（位置フィールドだけ書換）", "○ 発信源近くの端末が矛盾を検出"],
    ["捏造（偽の機体を電波送信）", "△ 送信すれば RSSI は伴う。位置と強度の不整合で判定"],
    ["送信電力の操作（A を変えて距離を偽装）", "△ 単端末は騙せるが全端末同時充足は困難"],
    ["中継 / ワームホール（遠方信号を再放送）", "✕ RSSI は中継点を反映（原理的限界）"],
    ["ジャミング / DoS", "対象外（可用性の問題）"],
], col_w=[3.9, 4.7], fs=12, row_h=0.44)
y = bullets(s, y, [
    (0, "主眼 = 位置詐称。中継は限界として明示（将来 TDoA / 実測裏取りで補完）"),
    (0, "端末 GPS の信頼はアテステーションで別途担保"),
], size0=14)

# S20 実機実験計画
s = add_slide(); title(s, "今後 — 実機実験計画（パラメータ確定）")
y = table(s, TOP, [
    ["記号", "測定方法", "単位/粒度"],
    ["A", "1m 地点で複数回測定", "端末×機体"],
    ["n", "5/10/20/30/50m で回帰", "環境別"],
    ["σ", "回帰残差の標準偏差", "環境別"],
    ["M", "時系列で応答遅延と分散を比較", "共通/環境別"],
    ["r", "正常データの FPR から決定", "条件別"],
    ["K", "ROC / FPR 制約下で決定", "参加端末数別"],
], col_w=[1.0, 4.8, 2.8], fs=12.5, row_h=0.42)
y = bullets(s, y, [
    (0, "現状の r=2.1・K は暫定値。上記の実機較正で確定する"),
], size0=14)

# S21 まとめ
s = add_slide(); title(s, "まとめ")
y = bullets(s, TOP, [(0, "提案 = K-of-N 合意（主役）＋ 多辺測量（補助）＋ ZKP/チェーン")])
y = bullets(s, y + 0.05, [
    (0, "実装済み"),
    (1, "アプリ（受信〜単端末判定, Pixel 8）／ 多辺測量ソルバ ／ ZKP回路 ／ 集約"),
    (0, "シミュレーション済み"),
    (1, "検知率: Δ=30mでN=5→90.9% ／ K-of-N が多辺測量に優位 ／ 較正誤差が支配的"),
    (0, "今後（未実施）"),
    (1, "実 DJI 機での A/n/σ 較正と実測評価 ／ r・K の確定"),
])
y = bullets(s, y + 0.05, [
    (0, "位置特定（多辺測量）は補助。中心は分散端末の K-of-N 合意による頑健な詐称検知"),
], size0=14)

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "week18")
os.makedirs(OUT_DIR, exist_ok=True)
out_path = os.path.join(OUT_DIR, "rssi_localization.pptx")
prs.save(out_path)
print(f"saved: {os.path.abspath(out_path)}  ({len(prs.slides._sldIdLst)} slides)")
