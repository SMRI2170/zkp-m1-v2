#!/usr/bin/env python3
"""追加機能（WiFi 配信 / WiFi 受信）の解説スライド。

構成図・送受信の技術と仕組み・背景と効果・アプリ実表示（before/after・ログ）・
用いた技術一覧・想定質問（Q&A）・まとめ までを通しでカバーする。

デザイン（進捗第11回スタイル / 手作り感のあるミニマル）:
  - 背景 白 / 黒文字（1A1A1A）、補助はグレー（555555）。色は使わない。
  - フォントは Yu Gothic で統一（和文・英数とも同一）。
  - 文章は四角で囲まない。枠は技術的な抜粋・構成図のみ（細い CCCCCC）。
  - タイトル直下に細い CCCCCC の横罫線。タイトルは内容を表す具体的な文にする。
  - 4:3 (10 x 7.5 inch)
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn

# ── 配色（黒・グレーのみ）─────────────────────────────
INK = RGBColor(0x1A, 0x1A, 0x1A)
GRAY = RGBColor(0x55, 0x55, 0x55)
RULE = RGBColor(0xCC, 0xCC, 0xCC)
CODEBG = RGBColor(0xF7, 0xF7, 0xF7)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

FONT = "Yu Gothic"   # 和文・英数を統一

prs = Presentation()
prs.slide_width = Inches(10)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
_page = [0]


def _set_font(r):
    r.font.name = FONT
    rPr = r._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {})
            rPr.append(el)
        el.set("typeface", FONT)


def run(p, text, size, color=INK, bold=False):
    r = p.add_run(); r.text = text
    r.font.size = Pt(size); r.font.color.rgb = color; r.font.bold = bold
    _set_font(r)


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
    tf = tbox(s, 0.68, 0.45, 8.7, 0.8)
    run(tf.paragraphs[0], text, 25, INK, bold=True)
    hrule(s, 1.18)


def subhead(tf, text, space_before=16):
    p = tf.add_paragraph(); p.space_before = Pt(space_before)
    run(p, text, 16, INK, bold=True)


def bullet(tf, text, size=15, space_before=9, indent=False, bold=False):
    p = tf.add_paragraph(); p.space_before = Pt(space_before)
    run(p, ("   ・ " if indent else "・ "), size, INK)
    run(p, text, size, INK, bold=bold)


def sub(tf, text, size=13, space_before=2):
    p = tf.add_paragraph(); p.space_before = Pt(space_before)
    run(p, "      " + text, size, GRAY)


def codebox(s, l, t, w, h, lines):
    box = s.shapes.add_shape(1, Inches(l), Inches(t), Inches(w), Inches(h))
    box.fill.solid(); box.fill.fore_color.rgb = CODEBG
    box.line.color.rgb = RULE; box.line.width = Pt(0.75); box.shadow.inherit = False
    tf = box.text_frame; tf.word_wrap = True
    tf.margin_left = Pt(10); tf.margin_right = Pt(8)
    tf.margin_top = Pt(7); tf.margin_bottom = Pt(7)
    for i, (text, gray) in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_before = Pt(3)
        run(p, text, 12, GRAY if gray else INK)


def dbox(s, l, t, w, h, head, subs):
    """構成図の箱（白地・細グレー枠・黒文字）。"""
    box = s.shapes.add_shape(1, Inches(l), Inches(t), Inches(w), Inches(h))
    box.fill.solid(); box.fill.fore_color.rgb = WHITE
    box.line.color.rgb = GRAY; box.line.width = Pt(1.0); box.shadow.inherit = False
    tf = box.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    run(p, head, 13.5, INK, bold=True)
    for line in subs:
        pp = tf.add_paragraph(); pp.alignment = PP_ALIGN.CENTER; pp.space_before = Pt(2)
        run(pp, line, 10.5, GRAY)


def arrow(s, l, t, label=None):
    tf = tbox(s, l, t, 0.5, 0.5)
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    run(p, "→", 20, INK, bold=True)
    if label:
        lt = tbox(s, l - 0.35, t - 0.45, 1.2, 0.4)
        lp = lt.paragraphs[0]; lp.alignment = PP_ALIGN.CENTER
        run(lp, label, 9.5, GRAY)


def qa(tf, q, a, first=False):
    p = tf.add_paragraph(); p.space_before = Pt(4 if first else 15)
    run(p, "Q. ", 15, INK, bold=True); run(p, q, 15, INK, bold=True)
    p2 = tf.add_paragraph(); p2.space_before = Pt(3)
    run(p2, "A. ", 13.5, GRAY); run(p2, a, 13.5, INK)


# ════════════════════════════════════════════════════
# 1 表紙
# ════════════════════════════════════════════════════
s = add_slide(number=False)
tf = tbox(s, 0.9, 2.55, 8.2, 0.5)
run(tf.paragraphs[0], "追加機能の説明", 16, GRAY)
tf = tbox(s, 0.88, 3.05, 8.4, 1.4)
run(tf.paragraphs[0], "WiFi 経由のドローン検知", 34, INK, bold=True)
hrule(s, 4.25, l=0.92, w=5.2)
tf = tbox(s, 0.92, 4.4, 8.2, 1.0)
run(tf.paragraphs[0], "ラズパイで電波を「発信」、アプリで「受信」", 16, INK)
p = tf.add_paragraph(); p.space_before = Pt(6)
run(p, "送信側（Raspberry Pi）と 受信側（スマホアプリ）の2つを追加", 14, GRAY)

# ════════════════════════════════════════════════════
# 2 構成図（全体像）
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "全体の構成")
tf = tbox(s, 0.7, 1.35, 8.6, 0.6)
run(tf.paragraphs[0],
    "電波を出すラズパイ（送信側）と、受け取って表示・証明するアプリ（受信側）の構成",
    14, INK)
y = 2.7
dbox(s, 0.6, y, 1.95, 1.45, "ラズパイ", ["疑似ドローン", "電波を発信"])
dbox(s, 2.95, y, 1.95, 1.45, "スマホアプリ", ["電波を受信", "中身を解読"])
dbox(s, 5.3, y, 1.95, 1.45, "画面表示", ["ドローンの", "位置を表示"])
dbox(s, 7.5, y, 1.9, 1.45, "近接の証明", ["位置を明かさず", "近接を証明"])
arrow(s, 2.5, y + 0.45, "WiFi電波")
arrow(s, 4.85, y + 0.45)
arrow(s, 7.15, y + 0.45)
# 送信/受信の帯
tf = tbox(s, 0.6, y + 1.5, 1.95, 0.35)
p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
run(p, "今回：送信側（新規）", 10.5, GRAY)
tf = tbox(s, 2.95, y + 1.5, 6.45, 0.35)
p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
run(p, "受信側（アプリに WiFi 検知を追加）", 10.5, GRAY)
hrule(s, 5.0)
tf = tbox(s, 0.7, 5.15, 8.6, 2.0)
bullet(tf, "送信側は実機が無いため新規構築、受信側は既存の解析・証明処理を再利用", space_before=8)
bullet(tf, "最後の「証明」は、位置を明かさず“近くにいた”ことだけ示す仕組み（ゼロ知識証明）", space_before=8)
bullet(tf, "リモートID自体は誰でも出せる公開情報、証明はなりすまし対策ではなく近接の事実を位置非開示で示すもの", space_before=8)

# ════════════════════════════════════════════════════
# 3 送信側：用いた技術
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "送信側｜ラズパイを疑似ドローンにする")
tf = tbox(s, 0.7, 1.4, 8.6, 5.6)
bullet(tf, "Raspberry Pi の内蔵WiFi", bold=True, space_before=7)
sub(tf, "Linuxが動く小型コンピュータで、内蔵WiFi（Broadcom）はアクセスポイント動作に対応。外付け機器なしで電波の発信源にできる点が利点")
bullet(tf, "hostapd（WiFiの電波を出す標準ソフト）", bold=True, space_before=7)
sub(tf, "Linux標準のAP化ソフトで、ビーコン等の管理フレームを生成・送出。設定項目で任意のベンダ固有情報（追加の枠）をビーコンに足せる")
bullet(tf, "opendroneid-core-c（国際標準の公式ツール）", bold=True, space_before=7)
sub(tf, "OpenDroneID（ASTM F3411）の公式リファレンス実装で、ID・位置を規格どおりのバイト列に符号化。自作せず公式を使うことで本物と同じ形式を担保")
bullet(tf, "ネット接続と発信の同時動作", bold=True, space_before=7)
sub(tf, "1枚のWiFiで「ネット接続」と「発信」を同一チャンネルで両立する構成。SSH操作を保ったまま発信でき、遠隔のラズパイでも運用可")

# ════════════════════════════════════════════════════
# 4 送信側：仕組み（電波にデータを埋め込む）
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "送信側｜WiFi電波にID・位置を埋め込む")
tf = tbox(s, 0.7, 1.4, 8.6, 1.0)
run(tf.paragraphs[0],
    "WiFiの電波にある“追加情報の枠”に、ドローンの身分証データを入れて発信",
    15, INK)
tf = tbox(s, 0.7, 2.5, 8.6, 4.2)
subhead(tf, "どのように使ったか", space_before=4)
bullet(tf, "ラズパイのWiFiを電波を出す状態（アクセスポイント）として起動", indent=True)
bullet(tf, "公式ツールでID・緯度経度・高度を“標準形式”のデータに変換", indent=True)
bullet(tf, "そのデータを電波の“追加情報の枠”に載せて発信", indent=True)
bullet(tf, "緯度経度はコマンドで指定可能、変えれば移動するドローンも再現", indent=True)
subhead(tf, "補足")
bullet(tf, "通常のWiFiアクセスポイントの電波に規格で認められた枠を足すだけ、微弱で自分のLAN内のため特別な装置や無理な操作は不要", indent=True)

# ════════════════════════════════════════════════════
# 5 送信側：背景と効果（＋発信中の証拠）
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "送信側｜実機なしで電波を再現する")
tf = tbox(s, 0.7, 1.4, 8.6, 5.5)
subhead(tf, "背景", space_before=4)
bullet(tf, "本物のドローン（DJI等）は高価で準備の手間も大", indent=True)
bullet(tf, "受信アプリは完成済みでも、試す相手がおらず動作確認が不可", indent=True)
subhead(tf, "効果")
bullet(tf, "実機なしで、いつでも“本物そっくりの電波”を発信できる環境を構築", indent=True)
bullet(tf, "電波の受信からアプリ内の証明までを通した検証が可能", indent=True)
subhead(tf, "補足")
bullet(tf, "電波の細かな種類やチャンネルは本物と完全同一ではないが、スマホが読む中身（ID・位置の形式）は公式と一致し検知に影響なし", indent=True)
bullet(tf, "現在も疑似ドローンとして発信を継続中（ID：RPI-ODID-TEST）", indent=True)

# ════════════════════════════════════════════════════
# 6 受信側：用いた技術
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "受信側｜AndroidのWiFiスキャンで読み取る")
tf = tbox(s, 0.7, 1.4, 8.6, 5.6)
bullet(tf, "Android の WiFi スキャン（情報枠の読み取り）", bold=True, space_before=7)
sub(tf, "OSのWiFiスキャンAPIで、Android 11以降は各APの生の枠（IE）まで取得可。接続せずビーコン内のリモートIDを読める（iOSは非対応）")
bullet(tf, "ネイティブ受信部（Kotlin）＋ アプリへの橋渡し", bold=True, space_before=7)
sub(tf, "スキャン結果からドローン用の枠だけ抽出し、アプリ本体へ受け渡す部分。OS依存処理をネイティブに閉じ込め、アプリ側は経路を問わず同じデータを扱える")
bullet(tf, "既存の解析処理を再利用", bold=True, space_before=7)
sub(tf, "25バイト単位のメッセージからID・緯度経度・高度を復元する処理で、BLEで実績のあるものを流用。送信元が変わっても解析は共通で二重実装を回避")
bullet(tf, "既存の証明フローに合流", bold=True, space_before=7)
sub(tf, "受信した位置を、位置を明かさず近接だけ示す既存の証明パイプラインへ接続。WiFi対応のために証明側を作り直す必要なし")

# ════════════════════════════════════════════════════
# 7 受信側：仕組み（取り出す流れ）
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "受信側｜電波からドローン情報を取り出す")
tf = tbox(s, 0.7, 1.4, 8.6, 0.6)
p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
run(p, "WiFiをスキャン  →  情報枠を抽出  →  中身を解読  →  位置を表示", 15, INK, bold=True)
tf = tbox(s, 0.7, 2.5, 8.6, 4.2)
subhead(tf, "どのように使ったか", space_before=4)
bullet(tf, "周囲のWiFiを定期的にスキャン", indent=True)
bullet(tf, "各電波の“追加情報の枠”を調べ、ドローン用の目印（標準の識別）が付いたものだけを抽出", indent=True)
bullet(tf, "その枠からドローン情報の本体を取り出し、既存の解析処理へ受け渡し", indent=True)
bullet(tf, "解析結果（ID・緯度経度・高度）を画面表示と近接証明にそのまま反映", indent=True)

# ════════════════════════════════════════════════════
# 8 受信側：背景と効果（DJI 写真つき）
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "受信側｜WiFi発信のドローンに対応する")
tf = tbox(s, 0.7, 1.45, 5.0, 5.4)
subhead(tf, "背景", space_before=4)
bullet(tf, "市販ドローン（DJI等）の多くはWiFiの電波でID・位置を発信", indent=True)
bullet(tf, "従来のままではこれらのドローンが検知不可", indent=True)
subhead(tf, "効果")
bullet(tf, "WiFi経由でもドローンを検知でき、対応機体の幅が拡大", indent=True)
bullet(tf, "従来方式と並行動作し、片方が不調でも受信を継続", indent=True)
subhead(tf, "補足")
bullet(tf, "DJI等の標準リモートIDは同じ“枠”で発信するため原理的に対応（実機での最終確認は今後）", indent=True)
# DJI 実機写真
pic_w = 3.5
s.shapes.add_picture("images/experimental-drone.jpg", Inches(5.85), Inches(2.2), width=Inches(pic_w))
tf = tbox(s, 5.85, 2.2 + pic_w * 1536 / 2730 + 0.05, pic_w, 0.4)
p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
run(p, "検知対象の例：市販ドローン（DJI）", 11.5, GRAY)

# ════════════════════════════════════════════════════
# 9 アプリでの表示（before / after）
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "アプリでの表示｜未受信から位置表示へ")
tf = tbox(s, 0.7, 1.35, 8.6, 0.6)
run(tf.paragraphs[0],
    "電波の受信で、ドローンのカードが「未受信」から緯度・経度・距離の表示へ切替",
    14, INK)
img_h = 4.15
img_w = img_h * 864 / 1920
y = 2.1
lx, rx = 2.05, 6.05
s.shapes.add_picture("images/before-remoteID-detection.jpg", Inches(lx), Inches(y), height=Inches(img_h))
s.shapes.add_picture("images/after-remoteID-detection.jpg", Inches(rx), Inches(y), height=Inches(img_h))
tf = tbox(s, 4.0, 3.9, 2.0, 0.6)
p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
run(p, "→", 30, INK, bold=True)
for cx, label in ((lx + img_w / 2 - 1.0, "受信前：未受信"),
                  (rx + img_w / 2 - 1.0, "受信後：緯度・経度・距離を表示")):
    tf = tbox(s, cx, y + img_h + 0.05, 2.0, 0.4)
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    run(p, label, 12.5, INK, bold=True)
tf = tbox(s, 0.7, 6.85, 8.6, 0.4)
p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
run(p, "受信後は推定距離・時刻差も表示、そのまま近接証明に利用可", 12, GRAY)

# ════════════════════════════════════════════════════
# 10 アプリでの表示（WiFi Raw 一覧で識別）
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "アプリでの表示｜WiFi一覧でドローンを識別")
tf = tbox(s, 0.7, 1.35, 8.6, 0.6)
run(tf.paragraphs[0],
    "周囲のWiFi一覧の中で、ドローン（ODID-RPI-TEST）だけ「Remote ID」として強調表示",
    14, INK)
s.shapes.add_picture("images/app-wifi-raw-list.png", Inches(0.85), Inches(1.95), height=Inches(4.6))
tf = tbox(s, 3.6, 2.4, 5.7, 4.4)
subhead(tf, "一覧から分かること", space_before=4)
bullet(tf, "ODID-RPI-TEST に「Remote ID」バッジが付き、ドローンと判別", indent=True)
bullet(tf, "電波強度 -60 dBm・チャンネル9 も同時に表示", indent=True)
bullet(tf, "周囲の一般WiFi（Buffalo 等）とは別物として識別", indent=True)
subhead(tf, "補足")
bullet(tf, "ラズパイが疑似ドローンとして実際に検知できている証拠", indent=True)
bullet(tf, "ID名ではなく標準の目印（OUI・type）で検知＝DJI等の標準リモートID機にも同様に反応", indent=True)

# ════════════════════════════════════════════════════
# 11 アプリでの表示（電波の中身を解析）
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "アプリでの表示｜電波の中身を解析")
tf = tbox(s, 0.7, 1.35, 8.6, 0.6)
run(tf.paragraphs[0],
    "電波内の枠（Vendor IE）から OpenDroneID を取り出し、ID・位置にデコード",
    14, INK)
ih = 4.35
iw = ih * 864 / 1920
y = 1.95
lx, rx = 1.6, 5.7
s.shapes.add_picture("images/app-wifi-ie-detail.png", Inches(lx), Inches(y), height=Inches(ih))
s.shapes.add_picture("images/app-wifi-decoded.png", Inches(rx), Inches(y), height=Inches(ih))
tf = tbox(s, 3.95, 3.7, 1.8, 0.6)
p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
run(p, "→", 28, INK, bold=True)
for cx, label in ((lx + iw / 2 - 1.1, "電波内の枠（OpenDroneID）"),
                  (rx + iw / 2 - 1.1, "解析結果：ID・位置")):
    tf = tbox(s, cx, y + ih + 0.05, 2.2, 0.4)
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    run(p, label, 12, INK, bold=True)
tf = tbox(s, 0.7, 6.85, 8.6, 0.4)
p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
run(p, "BasicID＝RPI-ODID-TEST／Location＝35.658600, 139.745400・Alt 80.0m AIRBORNE を正しく取得", 11.5, GRAY)

# ════════════════════════════════════════════════════
# 12 アプリでの表示（WiFi受信の記録＝ログ）
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "アプリでの表示｜WiFi受信の記録（ログ）")
tf = tbox(s, 0.7, 1.35, 8.6, 0.6)
run(tf.paragraphs[0],
    "WiFiで受信した1件ごとに、ID・緯度経度・電波強度を時刻つきで記録（受信できている証拠）",
    14, INK)
s.shapes.add_picture("images/app-wifi-log.png", Inches(0.85), Inches(1.95), height=Inches(4.6))
tf = tbox(s, 3.6, 2.4, 5.7, 4.4)
subhead(tf, "ログから分かること", space_before=4)
bullet(tf, "[WiFi/Beacon Location] として緯度経度・高度を連続受信", indent=True)
bullet(tf, "ssid＝ODID-RPI-TEST・UAS_ID＝RPI-ODID-TEST を確認", indent=True)
bullet(tf, "電波強度（RSSI）も記録し距離推定に活用", indent=True)
subhead(tf, "補足")
bullet(tf, "検知できる距離は数十m程度、WiFiスキャンはOSが頻度を制限するため受信の鮮度表示などで補完", indent=True)

# ════════════════════════════════════════════════════
# 13 用いた技術の一覧
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "用いた技術の一覧")
tf = tbox(s, 0.7, 1.45, 4.2, 5.0)
subhead(tf, "送信側（ラズパイ）", space_before=4)
for it in ["Raspberry Pi 内蔵WiFi", "hostapd（発信機能）",
           "opendroneid-core-c（公式）", "ネット接続＋発信の同時動作"]:
    bullet(tf, it, size=14, indent=True)
tf = tbox(s, 5.2, 1.45, 4.1, 5.0)
subhead(tf, "受信側（アプリ）", space_before=4)
for it in ["Android WiFiスキャン", "ネイティブ受信部（Kotlin）",
           "既存の解析処理を再利用", "既存の証明フローに合流"]:
    bullet(tf, it, size=14, indent=True)
vl = s.shapes.add_shape(1, Inches(5.0), Inches(1.6), Pt(1.0), Inches(4.2))
vl.fill.solid(); vl.fill.fore_color.rgb = RULE
vl.line.fill.background(); vl.shadow.inherit = False

# ════════════════════════════════════════════════════
# 14 まとめ
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "まとめ")
tf = tbox(s, 0.7, 1.5, 8.6, 5.4)
bullet(tf, "送信側：ラズパイを疑似ドローン化し、標準形式の電波を発信", space_before=14)
bullet(tf, "受信側：アプリがWiFi経由でもドローンを検知し、既存の証明まで通す連携を実現", space_before=14)
bullet(tf, "実測：受信後に推定距離・時刻差（例：7.6m / 2s）まで取得", space_before=14)
bullet(tf, "効果：対応機体の幅が拡大、実機を待たない通し検証が可能", space_before=14)

# ════════════════════════════════════════════════════
# 15 今後
# ════════════════════════════════════════════════════
s = add_slide()
title(s, "今後｜実機ドローンでの実装")
tf = tbox(s, 0.7, 1.4, 8.6, 1.0)
run(tf.paragraphs[0],
    "次の段階は、疑似ドローンではなく本物のドローン（実機）での実装・検証",
    15, INK, bold=True)
tf = tbox(s, 0.7, 2.5, 8.6, 4.4)
subhead(tf, "やること", space_before=4)
bullet(tf, "DJI等の市販ドローンが実際に発信するWiFiリモートIDを本アプリで直接受信", indent=True)
bullet(tf, "機種・ファームウェアによる電波の差異を確認", indent=True)
bullet(tf, "屋外・実距離での検知範囲と距離推定の精度を確認", indent=True)
bullet(tf, "実機から受け取ったデータで近接証明（ゼロ知識証明）まで実行", indent=True)
subhead(tf, "ねらい")
bullet(tf, "疑似環境で確認した一連の流れが、実運用でもそのまま成立することの実証", indent=True)

# ── 保存 ─────────────────────────────────────────────
out = "wifi_feature_slides.pptx"
prs.save(out)
print(f"saved: {out}  slides: {len(prs.slides._sldIdLst)}")
