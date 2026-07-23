#!/usr/bin/env python3
"""
選考応募資料 PDF 生成スクリプト
Q6. 企画概要 + アーキテクチャ概要 + UIキャプチャ
A4 サイズ
"""

import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, PageBreak, HRFlowable
)
from reportlab.platypus.flowables import Flowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage

# ── フォント登録 ─────────────────────────────────────────────────────────────
FONT_PATH = "/Library/Fonts/Arial Unicode.ttf"
pdfmetrics.registerFont(TTFont("JA", FONT_PATH))
pdfmetrics.registerFont(TTFont("JA-Bold", FONT_PATH))  # Arial Unicode に Bold 無いため同一

# ── カラーパレット（2色 + グレー系に絞る）────────────────────────────────────
C_PRIMARY  = colors.HexColor("#1C2B4A")   # ダークネイビー（タイトル・アクセント）
C_ACCENT   = colors.HexColor("#2C5282")   # ミッドブルー（左ボーダー・リンク色）
C_TEXT     = colors.HexColor("#1A1A1A")   # 本文
C_SUBTEXT  = colors.HexColor("#666666")   # 補足テキスト
C_RULE     = colors.HexColor("#CCCCCC")   # 罫線
C_ROW      = colors.HexColor("#F7F8FA")   # テーブル偶数行
C_WHITE    = colors.white
C_LIGHT    = colors.HexColor("#EEF2F7")   # 薄い背景
# 後方互換（アーキテクチャ図で参照）
C_CYAN     = colors.HexColor("#1A5276")
C_GREEN    = colors.HexColor("#1E5631")
C_ORANGE   = colors.HexColor("#7D3C00")
C_GRAY     = colors.HexColor("#F0F0F0")

# ── スタイル定義 ─────────────────────────────────────────────────────────────
def make_styles():
    return {
        "body": ParagraphStyle("body", fontName="JA", fontSize=9, textColor=C_TEXT,
                               leading=15, spaceAfter=5),
        "body_sm": ParagraphStyle("body_sm", fontName="JA", fontSize=8.5,
                                  textColor=C_TEXT, leading=14, spaceAfter=3),
        "caption": ParagraphStyle("caption", fontName="JA", fontSize=8,
                                  textColor=C_SUBTEXT, alignment=1, leading=11),
        "meta_label": ParagraphStyle("meta_label", fontName="JA", fontSize=7.5,
                                     textColor=C_SUBTEXT, leading=11),
        "meta_value": ParagraphStyle("meta_value", fontName="JA", fontSize=9,
                                     textColor=C_TEXT, leading=13),
    }

S = make_styles()


# ── ページタイトル Flowable ──────────────────────────────────────────────────
class PageTitle(Flowable):
    """ページ上部タイトルブロック：左ボーダー＋タイポグラフィのみ"""
    def __init__(self, title, subtitle, page_label, width):
        super().__init__()
        self._title    = title
        self._subtitle = subtitle
        self._page     = page_label
        self._width    = width
        self._height   = 58

    def wrap(self, aw, ah):
        return self._width, self._height

    def draw(self):
        c = self.canv
        # 細い上線
        c.setStrokeColor(C_PRIMARY)
        c.setLineWidth(2)
        c.line(0, self._height, self._width, self._height)
        # ページラベル（右寄せ・小文字）
        c.setFillColor(C_SUBTEXT)
        c.setFont("JA", 7.5)
        c.drawRightString(self._width, self._height - 13, self._page)
        # タイトル
        c.setFillColor(C_PRIMARY)
        c.setFont("JA", 17)
        c.drawString(0, self._height - 32, self._title)
        # サブタイトル
        c.setFillColor(C_SUBTEXT)
        c.setFont("JA", 8.5)
        c.drawString(0, self._height - 46, self._subtitle)
        # 下線
        c.setStrokeColor(C_RULE)
        c.setLineWidth(0.5)
        c.line(0, 0, self._width, 0)


# ── セクション見出し Flowable ────────────────────────────────────────────────
class SectionHead(Flowable):
    """左3ptボーダー＋テキストのみ。背景色なし。"""
    def __init__(self, text, width):
        super().__init__()
        self._text  = text
        self._width = width
        self._height = 18

    def wrap(self, aw, ah):
        return self._width, self._height

    def draw(self):
        c = self.canv
        c.setFillColor(C_ACCENT)
        c.rect(0, 1, 3, 14, fill=1, stroke=0)
        c.setFillColor(C_PRIMARY)
        c.setFont("JA", 10)
        c.drawString(9, 4, self._text)


# ── メタ情報ブロック Flowable ────────────────────────────────────────────────
class MetaStrip(Flowable):
    """4項目を横一列に並べるシンプルな帯"""
    def __init__(self, items, width):
        super().__init__()
        self._items  = items   # list of (label, value)
        self._width  = width
        self._height = 30

    def wrap(self, aw, ah):
        return self._width, self._height

    def draw(self):
        c = self.canv
        # 薄い背景帯
        c.setFillColor(C_LIGHT)
        c.roundRect(0, 0, self._width, self._height, 3, fill=1, stroke=0)
        col_w = self._width / len(self._items)
        for i, (label, value) in enumerate(self._items):
            x = i * col_w + 10
            # 区切り縦線（最初以外）
            if i > 0:
                c.setStrokeColor(C_RULE)
                c.setLineWidth(0.5)
                c.line(i * col_w, 5, i * col_w, 25)
            c.setFillColor(C_SUBTEXT)
            c.setFont("JA", 6.5)
            c.drawString(x, 19, label)
            c.setFillColor(C_TEXT)
            max_w = col_w - 14
            for fs in (8.5, 8, 7.5, 7, 6.5):
                c.setFont("JA", fs)
                if c.stringWidth(value, "JA", fs) <= max_w:
                    break
            c.drawString(x, 6, value)


# 旧名エイリアス（ArchDiagram内で参照される HeaderBanner / SectionLabel は使わない）
HeaderBanner = PageTitle   # ArchDiagramは独自描画のみ
SectionLabel = SectionHead


class InfoBox(Flowable):
    """後方互換のみ。MetaStripを使うこと。"""
    def __init__(self, items, width, bg=C_GRAY):
        super().__init__()
        self._items = [(l, v) for l, v, _ in items]
        self._inner = MetaStrip(self._items, width)
        self._width = width
        self._height = 30

    def wrap(self, aw, ah):
        return self._width, self._height

    def draw(self):
        self._inner.canv = self.canv
        self._inner.draw()


# ── アーキテクチャ図 Flowable ────────────────────────────────────────────────
class ArchDiagram(Flowable):
    def __init__(self, width, height=340):
        super().__init__()
        self._w = width
        self._h = height

    def wrap(self, aw, ah):
        return self._w, self._h

    # ── 描画ヘルパー ──────────────────────────────────────────────────────────

    def _box(self, c, x, y, bw, bh, bg, label, sub=None, text_color=C_WHITE, r=5):
        c.setFillColor(bg)
        c.setStrokeColor(colors.HexColor("#37474F"))
        c.setLineWidth(0.6)
        c.roundRect(x, y, bw, bh, r, fill=1, stroke=1)
        label_y = y + bh / 2 + (4 if sub else 0)
        c.setFillColor(text_color)
        c.setFont("JA", 8)
        c.drawCentredString(x + bw / 2, label_y, label)
        if sub:
            c.setFont("JA", 6)
            c.setFillColor(colors.HexColor("#B0BEC5") if text_color == C_WHITE
                           else C_SUBTEXT)
            c.drawCentredString(x + bw / 2, y + bh / 2 - 7, sub)

    def _arrowhead(self, c, x, y, dx, dy, color, size=5):
        import math
        length = math.sqrt(dx * dx + dy * dy)
        if length < 0.1:
            return
        ux, uy = dx / length, dy / length
        c.setFillColor(color)
        p = c.beginPath()
        p.moveTo(x, y)
        p.lineTo(x - size * ux + size * 0.35 * (-uy),
                 y - size * uy + size * 0.35 * ux)
        p.lineTo(x - size * ux - size * 0.35 * (-uy),
                 y - size * uy - size * 0.35 * ux)
        p.close()
        c.drawPath(p, fill=1, stroke=0)

    def _arrow_h(self, c, x1, y, x2, label="", color=C_SUBTEXT, dashed=False):
        """水平矢印 (x1,y) → (x2,y)"""
        c.setStrokeColor(color)
        c.setLineWidth(1)
        if dashed:
            c.setDash(4, 3)
        c.line(x1, y, x2, y)
        c.setDash()
        self._arrowhead(c, x2, y, x2 - x1, 0, color)
        if label:
            self._arrow_label(c, (x1 + x2) / 2, y + 3, label)

    def _arrow_v(self, c, x, y1, y2, label="", color=C_SUBTEXT):
        """垂直矢印 (x,y1) → (x,y2)"""
        c.setStrokeColor(color)
        c.setLineWidth(1)
        c.line(x, y1, x, y2)
        self._arrowhead(c, x, y2, 0, y2 - y1, color)
        if label:
            self._arrow_label(c, x + 3, (y1 + y2) / 2, label, align="left")

    def _arrow_elbow(self, c, x1, y1, x2, y2, via_x=None, via_y=None,
                     label="", color=C_SUBTEXT):
        """エルボー矢印: (x1,y1) → (via,) → (x2,y2)
           via_y 指定: 垂直→水平→垂直 (Z字)
           via_x 指定: 水平→垂直 (L字)
        """
        c.setStrokeColor(color)
        c.setLineWidth(1)
        if via_y is not None:
            # 縦 → 横 → 縦
            c.line(x1, y1, x1, via_y)
            c.line(x1, via_y, x2, via_y)
            c.line(x2, via_y, x2, y2)
            self._arrowhead(c, x2, y2, 0, y2 - via_y, color)
            if label:
                self._arrow_label(c, (x1 + x2) / 2, via_y + 3, label)
        elif via_x is not None:
            # 横 → 縦
            c.line(x1, y1, via_x, y1)
            c.line(via_x, y1, via_x, y2)
            self._arrowhead(c, via_x, y2, 0, y2 - y1, color)
            if label:
                self._arrow_label(c, (x1 + via_x) / 2, y1 + 3, label)

    def _arrow_label(self, c, x, y, text, align="center"):
        """矢印ラベル（背景付き）"""
        c.setFont("JA", 6)
        tw = c.stringWidth(text, "JA", 6)
        pad = 2
        lx = x - tw / 2 - pad if align == "center" else x - pad
        c.setFillColor(colors.HexColor("#FAFAFA"))
        c.rect(lx, y - 1, tw + pad * 2, 8, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#455A64"))
        if align == "center":
            c.drawCentredString(x, y, text)
        else:
            c.drawString(x, y, text)

    def _layer_bg(self, c, x, y, lw, lh, bg, label, label_color=None):
        c.setFillColor(bg)
        c.setStrokeColor(colors.HexColor("#B0BEC5"))
        c.setLineWidth(0.5)
        c.roundRect(x, y, lw, lh, 5, fill=1, stroke=1)
        c.setFillColor(label_color or C_SUBTEXT)
        c.setFont("JA", 7)
        c.drawString(x + 8, y + lh - 12, label)

    # ── メイン描画 ────────────────────────────────────────────────────────────
    def draw(self):
        import math
        c = self.canv
        W, H = self._w, self._h

        # ── グリッド定義 (3列) ──────────────────────────────────────────────
        GAP = 8          # 列間ギャップ
        COL_W = (W - GAP * 4) / 3   # 各列幅 ≈ 159
        C1X = GAP                    # 列1 left
        C2X = C1X + COL_W + GAP     # 列2 left
        C3X = C2X + COL_W + GAP     # 列3 left
        C1CX = C1X + COL_W / 2      # 列1 center x
        C2CX = C2X + COL_W / 2      # 列2 center x
        C3CX = C3X + COL_W / 2      # 列3 center x

        # ── レイヤーY定義 (下から上) ─────────────────────────────────────────
        #  出力:   y=8,   h=66  → top=74
        #  ZKP:    y=82,  h=84  → top=166
        #  Flutter:y=174, h=84  → top=258
        #  物理:   y=266, h=70  → top=336 (≈H)
        L_OUT_Y,  L_OUT_H  = 8,   66
        L_ZKP_Y,  L_ZKP_H  = 82,  84
        L_FL_Y,   L_FL_H   = 174, 84
        L_PHY_Y,  L_PHY_H  = 266, 70

        BOX_H = 32   # 共通ボックス高さ

        # ── レイヤー背景 ─────────────────────────────────────────────────────
        self._layer_bg(c, 0, L_PHY_Y,  W, L_PHY_H,
                       colors.HexColor("#E8F5E9"), "① 物理層 / デバイス",
                       colors.HexColor("#2E7D32"))
        self._layer_bg(c, 0, L_FL_Y,   W, L_FL_H,
                       colors.HexColor("#E3F2FD"), "② Flutter App（Android 端末上）",
                       colors.HexColor("#1565C0"))
        self._layer_bg(c, 0, L_ZKP_Y,  W, L_ZKP_H,
                       colors.HexColor("#F3E5F5"), "③ ZKP 処理層（端末内・クラウドなし）",
                       colors.HexColor("#6A1B9A"))
        self._layer_bg(c, 0, L_OUT_Y,  W, L_OUT_H,
                       colors.HexColor("#FFF8E1"), "④ 出力 / 検証",
                       colors.HexColor("#E65100"))

        # ── ボックスY座標（各レイヤー内の中央揃え） ─────────────────────────
        phy_box_y  = L_PHY_Y + (L_PHY_H  - BOX_H) // 2 - 6
        fl_box_y   = L_FL_Y  + (L_FL_H   - BOX_H) // 2
        zkp_box_y  = L_ZKP_Y + (L_ZKP_H  - BOX_H) // 2
        out_box_y  = L_OUT_Y + (L_OUT_H  - BOX_H) // 2

        # 物理層は2列: Pi (列1+部分), Android (列3+部分)
        PHY_W = COL_W + GAP + COL_W * 0.3  # Pi幅: 列1幅＋少し
        self._box(c, C1X, phy_box_y, PHY_W, BOX_H,
                  colors.HexColor("#1B5E20"),
                  "Raspberry Pi 4", "GPS・BME280 → BLE 送信")

        AND_X = C2X + COL_W * 0.7 + GAP
        AND_W = W - AND_X - GAP
        self._box(c, AND_X, phy_box_y, AND_W, BOX_H,
                  colors.HexColor("#0D47A1"),
                  "Android 端末", "GPS・気圧・Camera")

        # BLE 信号矢印（Pi右端 → Android左端、水平点線）
        pi_right = C1X + PHY_W
        and_left = AND_X
        ble_y = phy_box_y + BOX_H / 2
        self._arrow_h(c, pi_right, ble_y, and_left, "BLE OpenDroneID (0xFFFA)",
                      colors.HexColor("#388E3C"), dashed=True)

        # ── Flutter App ボックス ─────────────────────────────────────────────
        self._box(c, C1X, fl_box_y, COL_W, BOX_H,
                  colors.HexColor("#1565C0"), "BLE Receiver", "FlutterBluePlus")
        self._box(c, C2X, fl_box_y, COL_W, BOX_H,
                  colors.HexColor("#00695C"), "YOLO Detector", "tflite_flutter + Camera")
        self._box(c, C3X, fl_box_y, COL_W, BOX_H,
                  colors.HexColor("#0D47A1"), "Sensor Logger", "geolocator + sensors_plus")

        # ── ZKP ボックス ─────────────────────────────────────────────────────
        self._box(c, C1X, zkp_box_y, COL_W, BOX_H,
                  colors.HexColor("#6A1B9A"), "Witness Calc", "circom-witnesscalc (Rust)")
        self._box(c, C2X, zkp_box_y, COL_W, BOX_H,
                  colors.HexColor("#7B1FA2"), "Circom Circuit", "distance_30m_time.circom")
        self._box(c, C3X, zkp_box_y, COL_W, BOX_H,
                  colors.HexColor("#880E4F"), "Proof Generator", "rapidsnark (Groth16)")

        # ── 出力ボックス ─────────────────────────────────────────────────────
        self._box(c, C1X, out_box_y, COL_W, BOX_H,
                  colors.HexColor("#BF360C"), "Proof JSON", "π_A / π_B / π_C + public")
        self._box(c, C2X, out_box_y, COL_W, BOX_H,
                  colors.HexColor("#2E7D32"), "Verifier", "snarkjs (On-device)")
        self._box(c, C3X, out_box_y, COL_W, BOX_H,
                  colors.HexColor("#1A237E"), "UI 結果表示", "Riverpod / within30m+5s")

        # ────────────────────────────────────────────────────────────────────
        # 矢印 （各コネクション）
        # ────────────────────────────────────────────────────────────────────
        BLE_ARROW  = colors.HexColor("#388E3C")
        YOLO_ARROW = colors.HexColor("#006064")
        SNS_ARROW  = colors.HexColor("#0D47A1")
        ZKP_ARROW  = colors.HexColor("#6A1B9A")
        OUT_ARROW  = colors.HexColor("#E65100")

        phy_top  = phy_box_y + BOX_H   # 物理ボックス上端
        phy_bot  = phy_box_y           # 物理ボックス下端
        fl_top   = fl_box_y  + BOX_H
        fl_bot   = fl_box_y
        zkp_top  = zkp_box_y + BOX_H
        zkp_bot  = zkp_box_y
        out_top  = out_box_y + BOX_H

        # ① Pi → BLE Receiver（列1、垂直下向き）
        # Pi下端から BLE Receiver上端まで x=C1CX でまっすぐ
        self._arrow_v(c, C1CX, phy_bot, fl_top, "BLE受信", BLE_ARROW)

        # ② Android → YOLO Detector（列2へ、エルボー: Androidは右側）
        # Android center は (AND_X + AND_W/2)
        and_cx = AND_X + AND_W / 2
        # and_cx から C2CX へエルボー (垂直下→水平左→垂直下)
        via_y_yolo = (phy_bot + fl_top) / 2
        self._arrow_elbow(c, and_cx, phy_bot, C2CX, fl_top,
                          via_y=via_y_yolo, label="Camera映像", color=YOLO_ARROW)

        # ③ Android → Sensor Logger（列3、ほぼ垂直）
        # C3CX と and_cx が近い場合はほぼ真っすぐ
        via_y_sns = via_y_yolo - 8   # YOLO矢印と重ならないようY少しずらす
        self._arrow_elbow(c, and_cx + 18, phy_bot, C3CX, fl_top,
                          via_y=via_y_sns, label="GPS/気圧", color=SNS_ARROW)

        # ④ BLE Receiver → Witness Calc（列1、垂直）
        self._arrow_v(c, C1CX, fl_bot, zkp_top, "ドローン位置/時刻", BLE_ARROW)

        # ⑤ YOLO Detector → Witness Calc（列2→列1、エルボー）
        # 列2下端 → 中間Y → 列1上端　（横移動してから縦）
        via_y_wc = (fl_bot + zkp_top) / 2
        self._arrow_elbow(c, C2CX, fl_bot, C1CX + 18, zkp_top,
                          via_y=via_y_wc, label="検知フラグ", color=YOLO_ARROW)

        # ⑥ Sensor Logger → Witness Calc（列3→列1、エルボー）
        via_y_sl = via_y_wc - 9   # YOLO矢印と重ならないようY少しずらす
        self._arrow_elbow(c, C3CX, fl_bot, C1CX + 36, zkp_top,
                          via_y=via_y_sl, label="ユーザー位置/時刻", color=SNS_ARROW)

        # ⑦ Witness Calc → Circom（列1右端 → 列2左端、水平）
        self._arrow_h(c, C1X + COL_W, zkp_box_y + BOX_H / 2,
                      C2X, label="witness", color=ZKP_ARROW)

        # ⑧ Circom → Proof Generator（列2右端 → 列3左端、水平）
        self._arrow_h(c, C2X + COL_W, zkp_box_y + BOX_H / 2,
                      C3X, label=".zkey", color=ZKP_ARROW)

        # ⑨ Proof Generator → Proof JSON（列3下端 → 列1上端、エルボー）
        pg_bot_x = C3CX
        pj_top_x = C1CX
        via_y_out = (zkp_bot + out_top) / 2
        self._arrow_elbow(c, pg_bot_x, zkp_bot, pj_top_x, out_top,
                          via_y=via_y_out, label="proof.json", color=OUT_ARROW)

        # ⑩ Proof JSON → Verifier（列1右端 → 列2左端、水平）
        self._arrow_h(c, C1X + COL_W, out_box_y + BOX_H / 2,
                      C2X, label="verify(vk, pub, π)", color=OUT_ARROW)

        # ⑪ Verifier → UI（列2右端 → 列3左端、水平）
        self._arrow_h(c, C2X + COL_W, out_box_y + BOX_H / 2,
                      C3X, label="true/false", color=colors.HexColor("#2E7D32"))


# ── ページビルダー ────────────────────────────────────────────────────────────

def _p(text, fs=7.5, color=C_TEXT, bold=False):
    """テーブルセル用 Paragraph（自動折り返し）"""
    fn = "JA"
    return Paragraph(text, ParagraphStyle(
        "cell", fontName=fn, fontSize=fs, textColor=color,
        leading=fs * 1.5, spaceAfter=0,
    ))


def _ph(text, fs=8):
    """テーブルヘッダー用 Paragraph"""
    return Paragraph(text, ParagraphStyle(
        "hdr", fontName="JA", fontSize=fs, textColor=C_WHITE,
        leading=fs * 1.5, spaceAfter=0,
    ))


def build_pdf(out_path: str):
    img_dir = os.path.join(os.path.dirname(__file__), "..", "images")
    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=14*mm, bottomMargin=12*mm,
    )
    pw = A4[0] - 30*mm  # 使用可能幅
    story = []

    # ═══════════════════════════════════════════════════════════════════════════
    # PAGE 1 : 企画概要
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(PageTitle(
        "zk-UAV-Proximity-Proof",
        "ゼロ知識証明によるプライバシー保護型ドローン近接検知システム",
        "企画概要  /  1 of 3",
        pw,
    ))
    story.append(Spacer(1, 10))

    # ── メタ情報 ──
    meta = MetaStrip([
        ("到達フェーズ",  "PoC（実機デモ完成）"),
        ("開発体制",      "個人開発"),
        ("開発期間",      "約3ヶ月（2026年2月〜5月）"),
        ("担当",          "企画・設計・実装"),
    ], pw)
    story.append(meta)
    story.append(Spacer(1, 8))

    # ── GitHub リポジトリ ──
    story.append(Paragraph(
        "GitHub: <font color='#2C5282'><b>https://github.com/SMRI2170/zerosky-opendroneid</b></font>"
        "　　Dart 52.9% / Python 32.3% / Circom 8.3% / Shell 5.8%",
        ParagraphStyle("repo", fontName="JA", fontSize=8, textColor=C_SUBTEXT,
                       leading=12, leftIndent=6,
                       backColor=C_LIGHT, borderPad=5,
                       borderColor=C_RULE, borderWidth=0.5),
    ))
    story.append(Spacer(1, 12))

    # ── 背景・課題 ──
    story.append(SectionHead("背景と課題", pw))
    story.append(Spacer(1, 6))
    bg_text = [
        "2022年施行の改正航空法によりドローンの機体登録・リモートIDが義務化され、機体ID・位置情報の"
        "リアルタイム配信（BLE/Wi-Fi）が始まった。空の安全管理は一歩前進したが、同時に新たな問題が浮上した。",
        "特定のドローンが「自分の周囲30m以内に5秒以上滞空していた」という事実を、<b>自分の位置情報を"
        "一切開示せずに第三者へ証明する手段がない</b>という点だ。",
        "証明者の実座標を秘匿したまま近接の事実だけを数学的に証明できれば、セキュリティ・損害保険・"
        "民事訴訟など、各場面での信頼できる根拠として機能する。これがプロジェクトの出発点となった。",
    ]
    for t in bg_text:
        story.append(Paragraph(t, S["body"]))
    story.append(Spacer(1, 6))

    # ── アプローチ ──
    story.append(SectionHead("解決アプローチ", pw))
    story.append(Spacer(1, 6))

    TBL = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  C_PRIMARY),
        ("BACKGROUND",    (0, 1), (-1, 1),  C_LIGHT),
        ("ROWBACKGROUNDS",(0, 2), (-1, -1), [C_WHITE, C_ROW]),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.4, C_RULE),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
    ])
    aw1, aw2, aw3 = pw*0.22, pw*0.24, pw*0.54
    approach_data = [
        [_ph("アプローチ"), _ph("採用技術"), _ph("要点")],
        [_p("完全エッジ完結型 ZKP", color=colors.HexColor("#4A148C"), fs=8),
         _p("Circom + Groth16\nrapidsnark (Rust)\ncircom-witnesscalc"),
         _p("クラウドを一切使わず、Android端末上でWitness計算・Groth16証明生成・"
            "検証まで完結させた。30m以内かつ5秒以内という条件を専用回路で判定し、"
            "実座標は証明に含めない。")],
        [_p("【通信】\nドローン位置の取得"),
         _p("OpenDroneID\n(ASTM F3411-22a)"),
         _p("公開BLE放送から機体ID・位置を受信。opendroneid-core-c参照実装で"
            "バイトレイアウトを照合し、規格準拠を確認済み。")],
        [_p("【空間】\n3D位置の取得"),
         _p("Android GPS +\n気圧センサー"),
         _p("GPSに加え気圧センサーで相対高度を算出し、平面だけでなく高度差も考慮した"
            "3D近接判定を実現。")],
        [_p("【視覚】\nエッジAI検知"),
         _p("YOLOv8-tiny TFLite\n(VisDrone転移学習\n→drone fine-tuning)"),
         _p("VisDrone（空撮小物体検知）で転移学習後、drone単一クラスにfine-tuning。"
            "証明前にリアルタイムでドローンを検知し視覚的証拠として記録する。")],
    ]
    approach_table = Table(approach_data, colWidths=[aw1, aw2, aw3])
    approach_table.setStyle(TBL)
    story.append(approach_table)
    story.append(Spacer(1, 8))

    # ── 成果 ──
    story.append(SectionHead("主な成果", pw))
    story.append(Spacer(1, 6))

    ACH_TBL = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  C_PRIMARY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_ROW]),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.4, C_RULE),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
    ])
    ach_data = [
        [_ph("項目"), _ph("内容")],
        [_p("ZKP回路の最適化"),
         _p("距離と時間を同時判定するCircom回路を自作。--O2最適化でconstraint数を削減し、"
            "モバイル端末での実行速度を改善（最適化比較レポート付き）。")],
        [_p("Androidでの証明生成"),
         _p("rapidsnark（Rustネイティブ）をFlutterに直接組み込み、Android実機上で"
            "Groth16証明パイプライン全体を動作させることに成功した。")],
        [_p("実機PoC完了"),
         _p("Raspberry Pi（GPS+BME280）からBLE送信、Android端末で受信・AI検知・"
            "ZKP生成まで繋がるフルパイプラインを屋外環境で実証した。")],
        [_p("OpenDroneID準拠"),
         _p("ASTM F3411-22a のByte1 nibble順・EWDirection・SpeedMult等を"
            "opendroneid-core-c照合で修正し、実機との通信を確認済み。")],
    ]
    ach_table = Table(ach_data, colWidths=[pw*0.2, pw*0.8])
    ach_table.setStyle(ACH_TBL)
    story.append(ach_table)
    story.append(Spacer(1, 8))

    # ── 今後の展望 ──
    story.append(SectionHead("今後の展望", pw))
    story.append(Spacer(1, 6))

    ISS_TBL = TableStyle([
        ("ROWBACKGROUNDS",(0, 0), (-1, -1), [C_WHITE, C_ROW]),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.4, C_RULE),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
    ])
    issues_data = [
        [_p("本番化", color=C_SUBTEXT),
         _p("MPC（Multi-Party Computation）セレモニーによる Trusted Setup の実施を計画している。")],
        [_p("検知強化", color=C_SUBTEXT),
         _p("独自データの継続収集と再 Fine-tuning により、より多様な機体・環境への対応を進める。")],
        [_p("iOS 展開", color=C_SUBTEXT),
         _p("rapidsnark の iOS ビルドを整備し、Android・iOS 両プラットフォームへの対応を目指す。")],
    ]
    issues_table = Table(issues_data, colWidths=[pw*0.18, pw*0.82])
    issues_table.setStyle(ISS_TBL)
    story.append(issues_table)

    # ═══════════════════════════════════════════════════════════════════════════
    # PAGE 2 : アーキテクチャ概要
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(PageTitle(
        "システムアーキテクチャ概要",
        "処理フロー・コンポーネント構成・セキュリティ／運用の工夫",
        "アーキテクチャ  /  2 of 3",
        pw,
    ))
    story.append(Spacer(1, 10))

    # ── 構成図 ──
    story.append(SectionHead("システム構成図（完全エッジ完結・クラウドなし）", pw))
    story.append(Spacer(1, 6))
    story.append(ArchDiagram(pw, 340))
    story.append(Spacer(1, 8))

    # ── コンポーネント表 ──
    story.append(SectionHead("コンポーネント一覧", pw))
    story.append(Spacer(1, 6))
    COMP_TBL = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  C_PRIMARY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_ROW]),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.4, C_RULE),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
    ])
    comp_data = [
        [_ph("レイヤー"), _ph("コンポーネント"), _ph("技術"), _ph("役割")],
        [_p("物理"), _p("Raspberry Pi 4"),   _p("Python / BlueZ"),        _p("GPS・BME280取得 → BLE OpenDroneID配信")],
        [_p("物理"), _p("Android 実機"),      _p("Flutter / Android SDK"), _p("BLE受信・カメラ・GPS・気圧センサーのホスト")],
        [_p("Edge"), _p("BLE Receiver"),      _p("flutter_blue_plus"),     _p("OpenDroneID (0xFFFA) / Mfr AD (0x02E5) の解析")],
        [_p("Edge"), _p("YOLO Detector"),     _p("tflite_flutter\nIsolateInterpreter"), _p("YUV420→RGB変換・YOLOv8-tiny推論・Riverpod状態管理")],
        [_p("Edge"), _p("Sensor Logger"),     _p("geolocator\nsensors_plus"), _p("GPS 3D位置 + 気圧センサーによる相対高度取得")],
        [_p("ZKP"),  _p("Witness Calc"),      _p("circom-witnesscalc\n(Rust FFI)"), _p("回路入力からwitnessファイルを生成")],
        [_p("ZKP"),  _p("Circom Circuit"),    _p("Circom 2.x"),            _p("30m以内 & 5秒以内 判定回路（--O2最適化）")],
        [_p("ZKP"),  _p("Proof Generator"),   _p("rapidsnark\n(Rust Native)"), _p("Groth16証明生成をモバイル端末上で実行")],
        [_p("出力"), _p("Verifier"),          _p("snarkjs (Dart FFI)"),    _p("vk.json と public signals を照合して真偽を返す")],
        [_p("出力"), _p("UI (Riverpod)"),     _p("flutter_riverpod 3.x"), _p("NotifierProvider で状態管理、証明結果を表示")],
    ]
    comp_table = Table(comp_data, colWidths=[pw*0.08, pw*0.16, pw*0.22, pw*0.54])
    comp_table.setStyle(COMP_TBL)
    story.append(comp_table)
    story.append(Spacer(1, 8))

    # ── セキュリティ / 運用 ──
    story.append(SectionHead("セキュリティ・運用面の工夫", pw))
    story.append(Spacer(1, 6))
    SEC_TBL = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  C_PRIMARY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_ROW]),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.4, C_RULE),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
    ])
    sec_data = [
        [_ph("観点"), _ph("内容")],
        [_p("プライバシー"),  _p("ZKPにより実座標を一切開示せず近接事実のみを証明。vk.jsonを公開すれば誰でも検証できる。")],
        [_p("証明の健全性"),  _p("Groth16の soundness により、不正な witnessから有効な証明は生成不能。回路内でassertにより入力範囲を強制。")],
        [_p("BLE信頼性"),     _p("Service UUID 0xFFFA + ASTM F3411-22aのバイト仕様に準拠。opendroneid-core-cで照合済み。")],
        [_p("完全オフライン"),_p("クラウド不要で端末完結。外部通信が発生しないため通信傍受・サーバー障害リスクがない。")],
        [_p("リソース管理"),  _p("Riverpod autoDispose + IsolateInterpreterで画面離脱時にTFLite・BLEを即解放。メモリリーク対策済み。")],
        [_p("Pi安定起動"),    _p("hciconfig hci0 upはアダプタ起動済みでも exit code 1 を返すため、check=Trueを外して冪等化。")],
    ]
    sec_table = Table(sec_data, colWidths=[pw*0.18, pw*0.82])
    sec_table.setStyle(SEC_TBL)
    story.append(sec_table)
    story.append(Spacer(1, 10))

    # ── 機械学習モデル・データセット ──────────────────────────────────────────
    story.append(SectionHead("機械学習モデルとデータセット", pw))
    story.append(Spacer(1, 6))

    story.append(Paragraph(
        "ドローン検知モデルは2段階の転移学習で構築している。"
        "直接ドローンを検知するデータで学習する前に、まず「小さな物体を検知する能力」自体を習得させる"
        "ことが精度向上の鍵となった。",
        S["body"]
    ))
    story.append(Spacer(1, 6))

    ML_TBL = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  C_PRIMARY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_ROW]),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.4, C_RULE),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
    ])

    ml_data = [
        [_ph("ステップ"), _ph("データセット"), _ph("役割と詳細"), _ph("設定")],
        [_p("① 転移学習\n（小物体検知）", color=C_ACCENT),
         _p("VisDrone2019-DET\n（天津大学公開）"),
         _p("ドローン搭載カメラが上空から地上を撮影した映像に歩行者・自転車・車両など"
            "10クラスをアノテーションした空撮ベンチマーク。"
            "画面上で非常に小さく映る物体を正確に検知する能力をモデルに習得させることが目的で、"
            "この「小物体検知のベースライン」をYOLOv8 Nanoに転移させるために採用した。"),
         _p("base: yolov8n.pt\nsize: 640px\nepochs: 80\nbatch: 8")],
        [_p("② Fine-tuning\n（ドローン検知）", color=C_ACCENT),
         _p("カスタムUAVデータ\n+ Roboflow\nDrone Detection\n（代替・現在無効）"),
         _p("①で習得した「小物体を見つける目」を、ドローン1クラスのデータで上書き学習。"
            "ここで初めてドローンそのものを検知する能力を付与する。"
            "Roboflow Universe の Drone Detection データセットも"
            "代替候補として設定に組み込んでいる。"),
         _p("weights: ①best.pt\nepochs: 60\nbatch: 8\nclasses: 1（drone）")],
        [_p("③ TFLite変換\n＋モバイル統合"),
         _p("—"),
         _p("ultralytics exportでfloat32 TFLiteに変換。"
            "tflite_flutter + IsolateInterpreterで非同期推論、"
            "GPU デリゲート（Android: GpuDelegateV2）で高速化。"
            "YUV420→RGB変換・NMS・スコア閾値0.20はFlutter側で処理。"),
         _p("format: tflite\ndtype: float32\ndelegate: GPU\nNMS IoU: 0.45")],
    ]
    ml_table = Table(ml_data, colWidths=[pw*0.16, pw*0.21, pw*0.43, pw*0.20])
    ml_table.setStyle(ML_TBL)
    story.append(ml_table)

    # ═══════════════════════════════════════════════════════════════════════════
    # PAGE 3 : UIキャプチャ
    # ═══════════════════════════════════════════════════════════════════════════
    story.append(PageBreak())
    story.append(PageTitle(
        "UIキャプチャ",
        "実機スクリーンショット・実験風景",
        "UIキャプチャ  /  3 of 3",
        pw,
    ))
    story.append(Spacer(1, 6))

    # 画像レイアウト定義 (ファイル名, キャプション)
    ui_images = [
        ("tflite-model-drone-detection.jpg",   "TFLite YOLO モデルによるドローン検知\n（バウンディングボックスオーバーレイ表示）"),
        ("opendroneid-detection-log.jpg",      "OpenDroneID BLE パケット受信ログ\n（位置情報・機体ID をリアルタイム表示）"),
        ("google-ml-kit-drone-detection.jpg",  "Google ML Kit フォールバック検知\n（YOLO 無効時の代替検知モード）"),
        ("before-remoteID-detection.jpg",      "BLE 受信前 — 収集タブ\n（手入力モードの入力フォーム）"),
        ("after-remoteID-detection.jpg",       "BLE 受信後 — 収集タブ\n（Pi から受信した位置情報を自動入力）"),
        ("experimental-drone.jpg",             "実験用ドローン（DJI Mini 系）\n（実機 PoC テスト環境）"),
    ]

    # 2列グリッドで配置
    col_w = (pw - 6) / 2
    for i in range(0, len(ui_images), 2):
        row_items = ui_images[i:i+2]
        row_cells = []
        for fname, cap in row_items:
            img_path = os.path.join(img_dir, fname)
            if not os.path.exists(img_path):
                row_cells.append(Paragraph(f"[画像なし: {fname}]", S["caption"]))
                continue
            # アスペクト比を保ちながら最大幅に収める
            pil = PILImage.open(img_path)
            orig_w, orig_h = pil.size
            ratio = orig_h / orig_w
            img_w = col_w - 4
            img_h = min(img_w * ratio, 100)  # 最大高さ制限
            img_w = img_h / ratio
            rl_img = RLImage(img_path, width=img_w, height=img_h)

            cell_content = [
                [rl_img],
                [Paragraph(cap, S["caption"])],
            ]
            cell_table = Table(cell_content, colWidths=[col_w])
            cell_table.setStyle(TableStyle([
                ("ALIGN",       (0,0), (-1,-1), "CENTER"),
                ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
                ("TOPPADDING",  (0,0), (-1,-1), 3),
                ("BOTTOMPADDING", (0,0), (-1,-1), 3),
                ("BOX",         (0,0), (-1,-1), 0.5, colors.HexColor("#CFD8DC")),
                ("BACKGROUND",  (0,0), (-1,-1), C_GRAY),
            ]))
            row_cells.append(cell_table)

        if len(row_cells) == 1:
            row_cells.append(Spacer(col_w, 1))

        row_table = Table([row_cells], colWidths=[col_w + 3, col_w + 3])
        row_table.setStyle(TableStyle([
            ("VALIGN",  (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING",  (0,0), (-1,-1), 0),
            ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ]))
        story.append(row_table)
        story.append(Spacer(1, 6))

    doc.build(story)
    print(f"PDF 生成完了: {out_path}")


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "application_portfolio.pdf")
    build_pdf(os.path.abspath(out))
