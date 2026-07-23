#!/usr/bin/env python3
"""第16回 進捗報告スライド（4:3 / 進捗第11回スタイル）。

内容:
  - 実機ドローンを実環境で検知できたこと（フィールドテスト / WiFi Remote ID 受信 / OpenDroneID 解析）
  - アプリの UI/UX（5タブ構成）と検知処理フロー
  - まとめ・今後

デザイン（進捗第11回スタイル / ミニマル）:
  - 背景 白 / 黒文字（1A1A1A）、補助グレー（555555）。色は使わない。
  - フォント Yu Gothic（和文・英数とも）/ コードは Courier New。
  - 文章は四角で囲まない。枠はコード/ログの抜粋のみ（F7F7F7 + CCCCCC）。
  - タイトル直下に細い CCCCCC の横罫線。
  - 4:3 (10 x 7.5 inch)

素材は week16/ のスクショ・写真・動画から切り出した静止画。
"""

import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn

# ─── 配色・フォント ─────────────────────────────────
INK = RGBColor(0x1A, 0x1A, 0x1A)
GRAY = RGBColor(0x55, 0x55, 0x55)
RULE = RGBColor(0xCC, 0xCC, 0xCC)
CODEBG = RGBColor(0xF7, 0xF7, 0xF7)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

FONT = "Yu Gothic"
MONO = "Courier New"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, "week16")

prs = Presentation()
prs.slide_width = Inches(10)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
_page = [0]


# ─── ヘルパー（generate_acoustic_zk_slides.py より流用）──────
def _set_font(r, font=FONT):
    r.font.name = font
    rPr = r._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {})
            rPr.append(el)
        el.set("typeface", font)


def run(p, text, size, color=INK, bold=False, font=FONT):
    r = p.add_run(); r.text = text
    r.font.size = Pt(size); r.font.color.rgb = color; r.font.bold = bold
    _set_font(r, font)
    return r


def add_slide(number=True):
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = WHITE
    if number:
        _page[0] += 1
        tf = s.shapes.add_textbox(Inches(9.2), Inches(7.05), Inches(0.55), Inches(0.35)).text_frame
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.RIGHT
        run(p, str(_page[0]), 10, GRAY)
    return s


def tbox(s, l, t, w, h):
    tf = s.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h)).text_frame
    tf.word_wrap = True
    return tf


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
    run(p, text, 15, INK, bold=True)
    return p


def bullet(tf, text, size=13.5, space_before=7, indent=False, bold=False, first=False):
    p = tf.add_paragraph(); p.space_before = Pt(2 if first else space_before)
    run(p, ("   ・ " if indent else "・ "), size, INK)
    run(p, text, size, INK, bold=bold)
    return p


def sub(tf, text, size=11.5, space_before=2):
    p = tf.add_paragraph(); p.space_before = Pt(space_before)
    run(p, "      " + text, size, GRAY)
    return p


def codebox(s, l, t, w, h, lines, size=11.5, mtitle=None):
    box = s.shapes.add_shape(1, Inches(l), Inches(t), Inches(w), Inches(h))
    box.fill.solid(); box.fill.fore_color.rgb = CODEBG
    box.line.color.rgb = RULE; box.line.width = Pt(0.75); box.shadow.inherit = False
    tf = box.text_frame; tf.word_wrap = True
    tf.margin_left = Pt(10); tf.margin_right = Pt(8)
    tf.margin_top = Pt(7); tf.margin_bottom = Pt(7)
    idx = 0
    if mtitle:
        run(tf.paragraphs[0], mtitle, size - 0.5, GRAY, font=MONO)
        idx = 1
    for i, item in enumerate(lines):
        text, gray = item if isinstance(item, tuple) else (item, False)
        p = tf.paragraphs[0] if (i == 0 and idx == 0) else tf.add_paragraph()
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
        fill.append(clr); ln.append(fill)
        tcPr.append(ln)


def table(s, l, t, w, rows, col_w, header=True, fs=12, row_h=0.34):
    nr = len(rows); nc = len(rows[0])
    gtbl = s.shapes.add_table(nr, nc, Inches(l), Inches(t), Inches(w), Inches(row_h * nr))
    tbl = gtbl.table
    tbl.first_row = False; tbl.horz_banding = False
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
            bold = header and ri == 0
            run(p, str(val), fs, INK, bold=bold)
    return tbl


def picture(s, name, l, t, h=None, w=None):
    """画像を高さ(または幅)指定で配置。指定しない側はアスペクト比保持で自動。"""
    kw = {}
    if h is not None:
        kw["height"] = Inches(h)
    if w is not None:
        kw["width"] = Inches(w)
    return s.shapes.add_picture(os.path.join(IMG, name), Inches(l), Inches(t), **kw)


def caption(s, l, t, w, text):
    tf = tbox(s, l, t, w, 0.3)
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    run(p, text, 10, GRAY)


# ════════════════════════════════════════════════════
# 1. 表紙
# ════════════════════════════════════════════════════
s = add_slide(number=False)
tf = tbox(s, 0.9, 2.0, 8.2, 0.5)
run(tf.paragraphs[0], "第16回 進捗報告（2026-06-29）", 15, GRAY)

tf = tbox(s, 0.88, 2.6, 8.4, 1.9)
run(tf.paragraphs[0], "実機ドローン検知の達成", 33, INK, bold=True)
p = tf.add_paragraph(); p.space_before = Pt(6)
run(p, "アプリ UI/UX・処理フローの整理", 33, INK, bold=True)

hrule(s, 4.55, l=0.92, w=4.4)

tf = tbox(s, 0.92, 4.75, 8.2, 0.5)
run(tf.paragraphs[0], "UAV Safety ZK — WiFi Remote ID / OpenDroneID 受信検証", 14, GRAY)

tf = tbox(s, 0.92, 6.5, 8.2, 0.5)
run(tf.paragraphs[0], "吉岡龍佑　／　2026-06-29", 13, INK)


# ════════════════════════════════════════════════════
# 2. 目次
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "目次")
tf = tbox(s, 0.9, 1.45, 8.4, 5.6)
items = [
    "今回の進捗サマリ",
    "フィールドテスト概要",
    "実機検知の証跡 ①：Remote ID 受信",
    "実機検知の証跡 ②：OpenDroneID 解析",
    "クロスチェック（参照アプリとの照合）",
    "アプリ UI/UX：メイン画面の見方とステップ判定",
    "アプリ UI/UX：5タブ構成と詳細タブ",
    "検知処理フロー",
    "まとめ・今後",
]
for i, t in enumerate(items):
    p = tf.add_paragraph(); p.space_before = Pt(9 if i else 4)
    run(p, f"{i+1:02d}   ", 17, GRAY, font=MONO)
    run(p, t, 17, INK, bold=True)


# ════════════════════════════════════════════════════
# 3. 今回の進捗サマリ
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "今回の進捗サマリ")
tf = tbox(s, 0.9, 1.4, 8.5, 3.5)
bullet(tf, "実環境で実機ドローン（DJI Matrice 系）を WiFi Remote ID により検知できた",
       size=18, bold=True, first=True)
sub(tf, "機体が送信する Remote ID ビーコンを端末アプリで受信し、画面上に機体を表示した。", size=13.5)
bullet(tf, "OpenDroneID を自前実装でパースし、識別情報と位置情報のデコードに成功した", size=18, bold=True)
sub(tf, "当初は解析できなかった位置メッセージも、境界補正により取得できるようになった。", size=13.5)
bullet(tf, "参照アプリ（Drone Scanner）でも同一機体を検出し、受信・識別の正しさを裏付けた", size=18)
bullet(tf, "アプリの UI/UX（メイン画面のステップ表示・5タブ構成）と検知処理フローを整理した", size=18)

codebox(s, 0.9, 5.35, 8.2, 1.75,
        [
            "RID-1ZNBK9600C00HV   Remote ID   -34 dBm  ch6",
            "[Type0] BasicID : 1ZNBK9600C00HV / JA.JU32331C3464",
            "[Type1] Location: 34.808617, 135.561736  Alt=22.5m",
        ],
        size=12.5, mtitle="# 実機から受信・デコードできた Remote ID（抜粋）")


# ════════════════════════════════════════════════════
# 4. フィールドテスト概要
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "フィールドテスト概要")
tf = tbox(s, 0.7, 1.45, 4.45, 5.4)
bullet(tf, "機体：DJI Matrice 系。Remote ID（リモート識別）の送信に対応した実機を使用", size=16, first=True)
bullet(tf, "方法：機体を実際に飛行させ、送信される Remote ID を端末アプリで同時に受信・記録", size=16)
bullet(tf, "場所：屋外の開けた区域。緯度 34.8086 / 経度 135.5617 付近で実施", size=16)
bullet(tf, "送信機の GEO 区域マップで飛行可否（規制エリア）と自機位置をあわせて確認", size=16)
sub(tf, "「機体を飛ばす」「アプリで受信する」を同じ場所・同じ時刻に行い、結果を突き合わせた。", size=13)

picture(s, "37452_0.jpg", 5.35, 1.5, w=4.2)
caption(s, 5.35, 3.92, 4.2, "実機ドローン（DJI Matrice 系）")
picture(s, "37453_0.jpg", 5.35, 4.45, w=4.2)
caption(s, 5.35, 6.87, 4.2, "送信機の GEO 区域マップ画面")


# ════════════════════════════════════════════════════
# 5. 実機検知の証跡 ①：Remote ID 受信
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "実機検知の証跡 ①：Remote ID 受信")
tf = tbox(s, 0.7, 1.45, 5.7, 5.4)
bullet(tf, "WiFi Raw スキャンで周囲のビーコンを一覧表示し、その中から Remote ID を抽出する", size=16, first=True)
bullet(tf, "機体の Remote ID を RID-1ZNBK9600C00HV として識別できた", size=16)
sub(tf, "電波強度 -34 dBm／チャンネル 6。受信時刻・MAC アドレスもあわせて記録する。", size=13)
bullet(tf, "Remote ID は WiFi ビーコンの Vendor IE（メーカー固有領域）として送信される", size=16)
bullet(tf, "通常の WiFi アクセスポイントも同じ画面に並ぶが、ドローンだけを区別して表示", size=16)
sub(tf, "電波強度が近いほど機体が近いことを示し、接近の目安として使える。", size=13)

picture(s, "37450_0.jpg", 6.75, 1.5, h=5.4)
caption(s, 6.45, 6.95, 3.3, "WiFi Raw：Remote ID を捕捉")


# ════════════════════════════════════════════════════
# 6. 実機検知の証跡 ②：OpenDroneID 解析
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "実機検知の証跡 ②：OpenDroneID 解析")
tf = tbox(s, 0.55, 1.42, 4.4, 3.0)
bullet(tf, "Vendor IE（OUI FA0BBC）から OpenDroneID のデータを取り出す", size=15, first=True)
bullet(tf, "25 バイト単位のメッセージを Type 別に分解してパースする", size=15)
sub(tf, "識別情報（BasicID）はすぐに取得できた。", size=12.5)
sub(tf, "位置（Location）は当初「パース不可」だったが、境界補正で取得に成功した。", size=12.5)

codebox(s, 0.55, 4.45, 4.4, 2.45,
        [
            "OpenDroneID 解析結果",
            "[OK] Type0 BasicID : 1ZNBK9600C00HV",
            "[OK] Type0 BasicID : JA.JU32331C3464",
            "[OK] Type1 Location :",
            "       34.808617, 135.561736",
            "       Alt = 22.5 m  (GROUND)",
            "[--] Type2          : 未解析",
        ], size=11)

picture(s, "37451_0.jpg", 5.2, 1.5, h=4.9)
caption(s, 5.0, 6.5, 2.6, "解析前：Location パース不可")
picture(s, "37454_0.jpg", 7.55, 1.5, h=4.9)
caption(s, 7.4, 6.5, 2.4, "解析後：Location 取得成功")


# ════════════════════════════════════════════════════
# 7. クロスチェック（参照アプリとの照合）
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "クロスチェック：参照アプリとの照合")
tf = tbox(s, 0.7, 1.45, 5.7, 5.4)
bullet(tf, "第三者アプリ Drone Scanner（OpenDroneID 対応の一般アプリ）でも同一機体を検出", size=16, first=True)
bullet(tf, "シリアル番号 1ZNBK9600C00HV が双方のアプリで一致した", size=16)
sub(tf, "独立した 2 つのアプリが同じ機体を受信 → 自作アプリの受信・識別が正しいと確認できる。", size=13)
bullet(tf, "地図上に検知したドローンと自機位置を表示し、「1 機検出」を確認", size=16)
bullet(tf, "運用者 ID が未送信の機体は「Unknown drone or RID module」と表示される", size=16)
sub(tf, "識別情報の一部が欠けていても、シリアル番号で機体を特定できる。", size=13)

picture(s, "37449_0.jpg", 6.75, 1.5, h=5.4)
caption(s, 6.45, 6.95, 3.3, "参照アプリ（同一 SN を検出）")


# ════════════════════════════════════════════════════
# 8. アプリ UI/UX：メイン画面の見方とステップ判定
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "アプリ UI/UX：メイン画面の見方")
tf = tbox(s, 0.7, 1.35, 5.8, 5.7)
p = tf.paragraphs[0]
run(p, "上部の4つの丸＝「受信→証明」までの進捗判定", 15, INK, bold=True)
bullet(tf, "① BLE/WiFi … Remote ID を受信できたか", size=14)
bullet(tf, "② GPS … 自分（端末）の位置を測位できたか", size=14)
bullet(tf, "③ 録画 … ドローンを動画に収め証拠を取得したか", size=14)
bullet(tf, "④ 証明 … ZK 証明を実行・完了したか", size=14)
sub(tf, "未達=薄いグレー／実行中=白／完了=チェック で状態を表し、左から順に点灯する。", size=12)
subhead(tf, "中央・下部の表示", space_before=11)
bullet(tf, "カメラに映る対象を「UAV をプレビューで検知中」と表示", size=14)
bullet(tf, "「ドローン」「あなた」のカードに受信状態・緯度経度・距離を表示", size=14)
bullet(tf, "「録画開始」で映像の証拠を取得し、続けて ZK 証明へ進む", size=14)

picture(s, "37456.jpg", 6.95, 1.45, h=5.5)
caption(s, 6.7, 7.0, 3.0, "メイン画面（実機をプレビュー検知中）")


# ════════════════════════════════════════════════════
# 9. アプリ UI/UX：5タブ構成と詳細タブ
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "アプリ UI/UX：5タブ構成と詳細タブ")
rows = [
    ["タブ", "役割"],
    ["メイン", "ステップ式の検知フロー・カメラ検知・録画"],
    ["詳細", "ZK 証明回路の選択・証明/検証結果・接近判定"],
    ["ログ", "受信イベントの時系列ログ"],
    ["BLE Raw", "BLE 広告の生データ可視化"],
    ["WiFi Raw", "WiFi ビーコン一覧・OpenDroneID 解析結果"],
]
table(s, 0.6, 1.5, 4.8, rows, [1.3, 3.5], fs=12, row_h=0.66)
tf = tbox(s, 0.6, 5.95, 4.9, 1.4)
bullet(tf, "「検知→記録→証明」を一連で実施できるよう各タブを役割分担", size=14, first=True)
sub(tf, "右図の詳細タブでは距離 30m 以内・時刻差 5 秒以内の「接近あり」を ZK 証明し 1.3 秒で完了。", size=12)

picture(s, "demo_frame.jpg", 5.9, 1.5, h=5.4)
caption(s, 5.6, 6.95, 4.2, "詳細タブ：ZK 証明 完了・接近判定の表示")


# ════════════════════════════════════════════════════
# 9. 検知処理フロー
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "検知処理フロー")
tf = tbox(s, 0.7, 1.4, 5.6, 5.6)
bullet(tf, "スキャン → 抽出 → 分解 → 解析 → 出力 の順で Remote ID を処理する", size=16, first=True, bold=True)
sub(tf, "OpenDroneID は WiFi/BLE の Vendor IE（OUI=FA0BBC）として送られてくる。", size=12.5)
subhead(tf, "処理の流れ", space_before=12)
bullet(tf, "① スキャン：周囲のビーコン・広告を収集する", size=15)
bullet(tf, "② Vendor IE 抽出：OUI=FA0BBC を OpenDroneID と判定", size=15)
bullet(tf, "③ メッセージ分解：25 バイト単位の Type 別メッセージに分割", size=15)
bullet(tf, "④ Type 別パース：Type0=識別 / Type1=位置 / Type4=運用者", size=15)
bullet(tf, "⑤ 出力：UI 表示・時系列ログ保存・ZK 証明の特徴量へ", size=15)

codebox(s, 6.45, 1.65, 3.3, 4.6,
        [
            "// 25B を Type で振り分け",
            "final t =",
            "  (bytes[0] >> 4) & 0x0F;",
            "switch (t) {",
            "  case 0:  // 識別",
            "    parseBasicId(bytes);",
            "  case 1:  // 位置",
            "    parseLocation(bytes);",
            "  case 4:  // 運用者",
            "    parseSystem(bytes);",
            "}",
        ], size=11)


# ════════════════════════════════════════════════════
# 10. まとめ
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "まとめ")
tf = tbox(s, 0.9, 1.55, 8.3, 5.5)
p = tf.paragraphs[0]
run(p, "今回、実環境で実機ドローン（DJI Matrice 系）を WiFi の Remote ID により"
       "検知することができた。", 17, INK)

p = tf.add_paragraph(); p.space_before = Pt(14)
run(p, "受信した OpenDroneID を自前実装でパースし、識別情報"
       "（1ZNBK9600C00HV / JA.JU32331C3464）に加え、当初は取得できなかった"
       "位置情報（緯度 34.808617・経度 135.561736・高度 22.5m）の"
       "デコードにも成功した。", 17, INK)

p = tf.add_paragraph(); p.space_before = Pt(14)
run(p, "さらに参照アプリ Drone Scanner でも同一機体を検出し、"
       "受信・識別が正しいことを確認できた。", 17, INK)

p = tf.add_paragraph(); p.space_before = Pt(14)
run(p, "あわせて、メイン画面のステップ表示や5タブ構成といったアプリの UI/UX と、"
       "スキャンから ZK 証明までの検知処理フローを整理した。", 17, INK)


# ════════════════════════════════════════════════════
# 11. 今後の課題
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "今後の課題")
tf = tbox(s, 0.9, 1.45, 8.4, 5.6)
bullet(tf, "【最優先】ZK 証明回路の作成", size=18, bold=True, first=True)
sub(tf, "接近判定（距離・時刻）を証明する回路を実装・最適化し、実機データで証明できるようにする。", size=13)
bullet(tf, "多人数のユーザの申請に対応できる設計を考える", size=18, bold=True)
sub(tf, "複数ユーザが同時に検知・証明を申請しても処理できる仕組み・サーバ構成を検討する。", size=13)
bullet(tf, "Type2 以降のメッセージ（運用者 ID・認証情報など）の解析に対応する", size=18)
bullet(tf, "BLE 経路での受信を安定化させ、WiFi と合わせて確実に受信できるようにする", size=18)
bullet(tf, "複数機の同時検知・追跡、距離推定と ZK 証明の連携、検知精度の継続検証", size=18)


# ─── 保存 ─────────────────────────────────
out = os.path.join(IMG, "week16_progress_4x3.pptx")
prs.save(out)
print(f"saved {out} ({len(prs.slides._sldIdLst)} slides)")
