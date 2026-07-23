"""Flutter アプリ UI 説明スライド
スクリーンショットを右側に配置するレイアウト。
スクショは後から PowerPoint 上で差し替える。

使い方:
  python3 scripts/generate_ui_slides.py
"""

from pathlib import Path
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

OUTPUT_PATH = Path("flutter_ui_guide.pptx")

W = Inches(10)
H = Inches(7.5)
M = Inches(0.45)

# レイアウト幅
L_W = Inches(5.30)   # 左ペイン（説明）幅
R_X = Inches(5.85)   # 右ペイン（スクショ）開始 X
R_W = Inches(3.80)   # 右ペイン幅
R_H = Inches(6.30)   # 右ペイン高さ（スマホ縦向き）
R_Y = Inches(0.62)   # 右ペイン Y

TOTAL = 17

C_BG    = RGBColor(0xFF, 0xFF, 0xFF)
C_BLACK = RGBColor(0x00, 0x00, 0x00)
C_TEXT  = RGBColor(0x1A, 0x1A, 0x1A)
C_SUB   = RGBColor(0x55, 0x55, 0x55)
C_RULE  = RGBColor(0xCC, 0xCC, 0xCC)
C_LIGHT = RGBColor(0xF0, 0xF0, 0xF0)
C_BOX   = RGBColor(0xF5, 0xF5, 0xF5)
C_PH    = RGBColor(0xE0, 0xE0, 0xE0)   # プレースホルダー背景
C_PHBR  = RGBColor(0xB0, 0xB0, 0xB0)   # プレースホルダー枠
C_TH    = RGBColor(0x11, 0x11, 0x11)
C_THFG  = RGBColor(0xFF, 0xFF, 0xFF)
C_TR1   = RGBColor(0xFF, 0xFF, 0xFF)
C_TR2   = RGBColor(0xF2, 0xF2, 0xF2)
C_TAG   = RGBColor(0xE8, 0xF0, 0xFE)
C_TAGBR = RGBColor(0x9E, 0xBC, 0xF5)

FONT = "Hiragino Sans"
MONO = "Courier New"


# ── ヘルパー ──────────────────────────────────────────────────────────────────

def set_bg(s):
    bg = s.background
    bg.fill.solid()
    bg.fill.fore_color.rgb = C_BG

def rect(s, l, t, w, h, c, border=False, bc=None, bw=0.75):
    sh = s.shapes.add_shape(1, l, t, w, h)
    sh.fill.solid()
    sh.fill.fore_color.rgb = c
    if border:
        sh.line.width = Pt(bw)
        sh.line.color.rgb = bc or C_RULE
    else:
        sh.line.fill.background()
    return sh

def txb(s, text, l, t, w, h, size=12, bold=False, color=C_TEXT,
        align=PP_ALIGN.LEFT, italic=False, mono=False):
    b = s.shapes.add_textbox(l, t, w, h)
    tf = b.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.color.rgb = color
    r.font.name = MONO if mono else FONT
    return b

def mline(s, lines, l, t, w, h, size=12, color=C_TEXT, gap=5,
          mono=False, bold_idx=None):
    b = s.shapes.add_textbox(l, t, w, h)
    tf = b.text_frame
    tf.word_wrap = True
    first = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        r = p.add_run()
        r.text = line
        r.font.size = Pt(size)
        r.font.color.rgb = color
        r.font.name = MONO if mono else FONT
        r.font.bold = (bold_idx is not None and i in bold_idx)
        p.space_after = Pt(gap)

def bullet(s, items, l, t, w, size=12, gap=7, dot="•  "):
    """箇条書きを縦に並べる"""
    b = s.shapes.add_textbox(l, t, w, Inches(0.38) * len(items))
    tf = b.text_frame
    tf.word_wrap = True
    first = True
    for item in items:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        if isinstance(item, tuple):
            text, clr = item
        else:
            text, clr = item, C_TEXT
        r = p.add_run()
        r.text = dot + text
        r.font.size = Pt(size)
        r.font.color.rgb = clr
        r.font.name = FONT
        p.space_after = Pt(gap)

def code(s, lines, l, t, w, h, size=9):
    rect(s, l, t, w, h, C_BOX, border=True)
    mline(s, lines, l + Inches(0.12), t + Inches(0.09),
          w - Inches(0.24), h - Inches(0.18),
          size=size, color=C_TEXT, gap=2, mono=True)

def pnum(s, n):
    txb(s, f"{n} / {TOTAL}", W - Inches(0.75), H - Inches(0.30),
        Inches(0.65), Inches(0.25), size=9, color=C_SUB,
        align=PP_ALIGN.RIGHT)

def placeholder(s, label="スクショをここに配置",
                x=R_X, y=R_Y, w=R_W, h=R_H):
    """スクリーンショット配置用プレースホルダー"""
    rect(s, x, y, w, h, C_PH, border=True, bc=C_PHBR, bw=1.5)
    # スマホ角丸イメージ（内枠）
    rect(s, x + Inches(0.08), y + Inches(0.08),
         w - Inches(0.16), h - Inches(0.16),
         C_PH, border=True, bc=C_PHBR, bw=0.5)
    # ラベル
    txb(s, label,
        x, y + h / 2 - Inches(0.25), w, Inches(0.50),
        size=11, color=C_SUB, align=PP_ALIGN.CENTER)

def hdr_left(s, title, sub=None, badge=None):
    """左ペイン用ヘッダー（上部バー + タイトル）"""
    set_bg(s)
    rect(s, 0, 0, W, Inches(0.07), C_BLACK)
    rect(s, 0, Inches(0.07), Inches(0.06), H - Inches(0.07), C_BLACK)
    if badge:
        rect(s, M, Inches(0.10), Inches(1.10), Inches(0.26),
             C_TAG, border=True, bc=C_TAGBR)
        txb(s, badge, M + Inches(0.06), Inches(0.12),
            Inches(1.0), Inches(0.22), size=9, color=C_TEXT)
        txb(s, title, M, Inches(0.40), L_W - M, Inches(0.60),
            size=20, bold=True, color=C_BLACK)
    else:
        txb(s, title, M, Inches(0.13), L_W - M, Inches(0.55),
            size=21, bold=True, color=C_BLACK)
    if sub:
        y = Inches(0.75) if badge else Inches(0.68)
        txb(s, sub, M, y, L_W - M, Inches(0.28),
            size=10, color=C_SUB)
    rect(s, M, Inches(1.04), L_W - M, Pt(1), C_RULE)

def sec(s, text, t, size=12):
    txb(s, text, M, t, L_W - M, Inches(0.30),
        size=size, bold=True, color=C_BLACK)
    rect(s, M, t + Inches(0.30), L_W - M, Pt(1), C_RULE)

def divider(s, part_title, subtitle):
    set_bg(s)
    rect(s, 0, 0, W, H, C_BLACK)
    txb(s, part_title, M, Inches(2.90), W - M * 2, Inches(1.0),
        size=34, bold=True, color=C_BG, align=PP_ALIGN.CENTER)
    txb(s, subtitle, M, Inches(4.05), W - M * 2, Inches(0.50),
        size=14, color=RGBColor(0xBB, 0xBB, 0xBB), align=PP_ALIGN.CENTER)

def tbl(s, headers, rows, l, t, w, cw=None, fs=10, rh=0.38):
    nr = len(rows) + 1
    nc = len(headers)
    tb = s.shapes.add_table(nr, nc, l, t, w, Inches(rh) * nr).table
    if cw:
        for i, v in enumerate(cw):
            tb.columns[i].width = v
    else:
        for col in tb.columns:
            col.width = w // nc

    def cs(cell, text, hd=False, ev=False):
        cell.fill.solid()
        cell.fill.fore_color.rgb = C_TH if hd else (C_TR2 if ev else C_TR1)
        tf = cell.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        r = p.add_run()
        r.text = text
        r.font.size = Pt(fs)
        r.font.bold = hd
        r.font.color.rgb = C_THFG if hd else C_TEXT
        r.font.name = FONT

    for ci, h in enumerate(headers):
        cs(tb.cell(0, ci), h, hd=True)
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cs(tb.cell(ri + 1, ci), val, ev=(ri % 2 == 1))


# =============================================================================
def build():
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H
    blank = prs.slide_layouts[6]

    # =========================================================================
    # 1. 表紙
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    set_bg(sl)
    rect(sl, 0, 0, W, Inches(0.12), C_BLACK)
    rect(sl, 0, H - Inches(0.12), W, Inches(0.12), C_BLACK)
    txb(sl, "Flutter アプリ UI ガイド",
        M, Inches(1.0), W - M * 2, Inches(1.0),
        size=40, bold=True, color=C_BLACK, align=PP_ALIGN.CENTER)
    txb(sl, "UAV Safety ZK — 各画面の役割と操作フロー",
        M, Inches(2.15), W - M * 2, Inches(0.60),
        size=17, color=C_SUB, align=PP_ALIGN.CENTER)
    rect(sl, Inches(1.5), Inches(2.95), Inches(7.0), Pt(1.5), C_BLACK)

    mline(sl, [
        "対象アプリ: rapidsnark_app  (Flutter SDK ^3.8.1 / Android)",
        "画面構成:   BottomNavigationBar 3 タブ + カメラ検知サブページ",
        "主な機能:   BLE 受信 / GPS 収集 / YOLO ドローン検知 / ZK 証明",
    ], Inches(1.8), Inches(3.15), Inches(6.4), Inches(1.2),
        size=13, color=C_TEXT, gap=9)

    txb(sl, f"{TOTAL} スライド構成  ／  各スライドの右側にスクショを配置",
        M, H - Inches(0.42), W - M * 2, Inches(0.28),
        size=10, color=C_SUB, align=PP_ALIGN.CENTER)
    pnum(sl, 1)

    # =========================================================================
    # 2. アプリ全体構成（3タブ + サブ画面）
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr_left(sl, "アプリ全体の画面構成",
             "BottomNavigationBar で 3 つのタブを切り替える")
    pnum(sl, 2)
    placeholder(sl, "アプリ全体\n（タブバー表示中）")

    txb(sl, "3 タブ構成", M, Inches(1.18), L_W - M, Inches(0.30),
        size=13, bold=True, color=C_BLACK)

    tabs = [
        ("メイン", "Icons.home",
         "カメラ全画面プレビュー\nドローン受信データ・自分の位置情報を\nオーバーレイ表示。録画→証明のメインフロー。"),
        ("詳細", "Icons.data_object",
         "証明回路の選択 (5 種類)、\nWitness Inputs・Public Signals・\nProof JSON の確認パネル。"),
        ("ログ", "Icons.terminal",
         "BLE スキャン・GPS・ZK 証明の\nデバッグログをリアルタイム表示。\n黒背景のコンソール風 UI。"),
    ]
    for i, (name, icon, desc) in enumerate(tabs):
        y = Inches(1.55) + Inches(1.65) * i
        rect(sl, M, y, L_W - M, Inches(1.50), C_BOX, border=True)
        rect(sl, M, y, Inches(0.38), Inches(1.50), C_BLACK)
        txb(sl, str(i + 1), M + Inches(0.04), y + Inches(0.50),
            Inches(0.30), Inches(0.50), size=18, bold=True,
            color=C_BG, align=PP_ALIGN.CENTER)
        txb(sl, name, M + Inches(0.48), y + Inches(0.06),
            L_W - M - Inches(0.52), Inches(0.34),
            size=14, bold=True, color=C_BLACK)
        txb(sl, f"({icon})", M + Inches(0.48), y + Inches(0.40),
            Inches(1.60), Inches(0.26), size=9, color=C_SUB, mono=True)
        txb(sl, desc, M + Inches(0.48), y + Inches(0.68),
            L_W - M - Inches(0.52), Inches(0.76),
            size=11, color=C_TEXT)

    txb(sl, "＋ UavLiveDetectionPage（リアルタイム YOLO 検知）— メインタブから遷移",
        M, H - Inches(0.42), L_W - M, Inches(0.30),
        size=10, italic=True, color=C_SUB)

    # =========================================================================
    # 3. メインタブ — 全体レイアウト
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr_left(sl, "メインタブ — 画面レイアウト",
             "カメラプレビューを背景に、上下オーバーレイで情報を表示する",
             badge="タブ 1 / メイン")
    pnum(sl, 3)
    placeholder(sl, "メインタブ\n（カメラ起動中）")

    sec(sl, "レイヤー構成（Z 軸方向）", Inches(1.12))
    layers = [
        ("① 最背面", "カメラプレビュー（全画面）",
         "CameraPreview ウィジェットが全画面を占有。\n起動前は黒背景＋ Icons.videocam_off を表示。"),
        ("② 上部オーバーレイ",
         "アプリ名 + REC インジケーター",
         '"UAV Safety ZK" テキスト。録画中は赤丸＋時刻。\n黒→透明のグラデーション帯。'),
        ("③ 録画プログレスバー",
         "上端の細いライン（録画中のみ）",
         "20 秒が最大。赤=録画中、緑=録画完了。"),
        ("④ 下部オーバーレイ",
         "データカード + ボタン類",
         "黒→透明のグラデーション。ドローン・自分の\nデータカード、距離・時刻差チップ、各種ボタン。"),
    ]
    for i, (layer, title, desc) in enumerate(layers):
        y = Inches(1.52) + Inches(1.32) * i
        rect(sl, M, y, L_W - M, Inches(1.20), C_BOX, border=True)
        txb(sl, layer, M + Inches(0.12), y + Inches(0.07),
            Inches(1.55), Inches(0.26), size=10, bold=True, color=C_SUB)
        txb(sl, title, M + Inches(0.12), y + Inches(0.35),
            L_W - M - Inches(0.24), Inches(0.30),
            size=12, bold=True, color=C_BLACK)
        txb(sl, desc, M + Inches(0.12), y + Inches(0.68),
            L_W - M - Inches(0.24), Inches(0.48),
            size=10, color=C_TEXT)

    # =========================================================================
    # 4. メインタブ — ドローン・自分のデータカード
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr_left(sl, "メインタブ — データカード",
             "ドローン（BLE 受信）と自分（GPS）の情報を並べて表示する",
             badge="タブ 1 / メイン")
    pnum(sl, 4)
    placeholder(sl, "メインタブ\n（下部データカード拡大）")

    sec(sl, "ドローン情報カード（左）", Inches(1.12))
    tbl(sl,
        ["項目", "値の出所", "表示例"],
        [
            ["緯度", "UavTelemetryPacket.latitude", "35.6891°"],
            ["経度", "UavTelemetryPacket.longitude", "139.6917°"],
            ["高度", "altitudeMeters（気圧/BME280）", "12.0m"],
            ["受信件数", "_droneHistory.length", "件数バッジ"],
            ["アイコン", "Icons.airplanemode_active", "グレー=未受信\n緑=受信済み"],
        ],
        M, Inches(1.50), L_W - M,
        cw=[Inches(1.30), Inches(2.30), Inches(1.38)], fs=10)

    sec(sl, "あなたの情報カード（右）", Inches(3.50))
    tbl(sl,
        ["項目", "値の出所", "表示例"],
        [
            ["緯度", "geolocator (GPS)", "35.6895°"],
            ["経度", "geolocator (GPS)", "139.6921°"],
            ["高度", "BME280 QFE 気圧高度 (m)", "2.1m"],
            ["受信件数", "_locationHistory.length", "件数バッジ"],
            ["アイコン", "Icons.person_pin_circle", "グレー=取得中\n緑=取得済み"],
        ],
        M, Inches(3.88), L_W - M,
        cw=[Inches(1.30), Inches(2.30), Inches(1.38)], fs=10)

    sec(sl, "距離・時刻差チップ（両データが揃ったとき表示）", Inches(5.88))
    mline(sl, [
        "推定距離: Haversine 近似（cm 単位整数演算） → 30m 以内なら緑、超過なら橙",
        "時刻差: ドローン受信時刻 vs GPS 取得時刻の差 → 5 秒以内なら緑、超過なら橙",
        "この 2 値が緑になると「証明可能」状態になる",
    ], M, Inches(6.25), L_W - M, Inches(1.0),
        size=11, color=C_TEXT, gap=6)

    # =========================================================================
    # 5. メインタブ — 録画と証明ボタン
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr_left(sl, "メインタブ — 録画 → 証明のフロー",
             "ボタン状態が自動的に切り替わり、ユーザーを次のステップへ誘導する",
             badge="タブ 1 / メイン")
    pnum(sl, 5)
    placeholder(sl, "メインタブ\n（ボタンエリア拡大）")

    sec(sl, "ボタンの状態遷移", Inches(1.12))
    states = [
        ("① データ未受信", "ドローン or GPS が未取得",
         "証明ボタン: グレー・無効\n「ドローン情報を受信してください」"),
        ("② データ揃い・録画前", "両データ green → 録画可能",
         "録画ボタン: 白枠「録画を開始」\n証明ボタン: 録画完了後に有効化"),
        ("③ 録画中", "CameraController.startVideoRecording()",
         "録画ボタン → 赤「録画停止」\nプログレスバーが伸びる（最大 20s）"),
        ("④ 録画完了", "_videoEvidence に XFile が入る",
         "「撮り直す」＋「▶ 証明を実行」の 2 ボタン表示"),
        ("⑤ 証明実行中", "circom_witnesscalc + flutter_rapidsnark",
         "CircularProgressIndicator + 経過時間\n「処理中... 00:12」"),
        ("⑥ 証明完了", "_proofValid = true", "詳細タブの Public Signals に結果が表示される"),
    ]
    for i, (state, trigger, ui) in enumerate(states):
        y = Inches(1.50) + Inches(0.98) * i
        rect(sl, M, y, L_W - M, Inches(0.90), C_BOX, border=True)
        txb(sl, state, M + Inches(0.10), y + Inches(0.06),
            Inches(1.60), Inches(0.26), size=11, bold=True, color=C_BLACK)
        txb(sl, trigger, M + Inches(0.10), y + Inches(0.34),
            Inches(2.10), Inches(0.52), size=9, color=C_SUB)
        rect(sl, M + Inches(2.30), y + Inches(0.10),
             Pt(1), Inches(0.70), C_RULE)
        txb(sl, ui, M + Inches(2.45), y + Inches(0.08),
            L_W - M - Inches(2.50), Inches(0.78),
            size=10, color=C_TEXT)

    # =========================================================================
    # 6. 詳細タブ — 証明回路セレクター
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr_left(sl, "詳細タブ — 証明回路の選択",
             "5 種類の Circom 回路プロファイルを ChoiceChip で切り替える",
             badge="タブ 2 / 詳細")
    pnum(sl, 6)
    placeholder(sl, "詳細タブ\n（回路セレクター）")

    sec(sl, "5 つの回路プロファイル", Inches(1.12))
    tbl(sl,
        ["プロファイル", "回路ファイル", "追加入力", "説明"],
        [
            ["Base",
             "distance_30m_time.circom",
             "なし",
             "距離・時刻のみを検証する最小構成"],
            ["DetectionFlag",
             "distance_detection_flag.circom",
             "検知フラグ (0/1)",
             "動画でドローン検知した場合のみ証明可"],
            ["Commitment",
             "distance_commitment.circom",
             "コミットメント値",
             "フレームデータのハッシュ値を証明に含める"],
            ["Classifier",
             "distance_feature_classifier.circom",
             "信頼度スコア (bps)",
             "YOLO スコアを整数変換して回路に入力"],
            ["TimeSeries",
             "distance_30m_time_series.circom",
             "最大 20 点の履歴",
             "複数時刻の位置履歴で時系列的に接近を証明"],
        ],
        M, Inches(1.50), L_W - M,
        cw=[Inches(1.25), Inches(2.10), Inches(1.15), Inches(0.98)], fs=9, rh=0.42)

    sec(sl, "UI の挙動", Inches(5.05))
    mline(sl, [
        "・選択中のチップは背景色が変わる (ChoiceChip selected=true)",
        "・証明実行中 (_isBusy=true) はチップが無効化される",
        "・プロファイルに応じて追加入力フィールドの表示が切り替わる",
        "・requiresVideo=true の場合、録画完了まで証明ボタンが無効のまま",
    ], M, Inches(5.42), L_W - M, Inches(1.68),
        size=11, color=C_TEXT, gap=7)

    # =========================================================================
    # 7. 詳細タブ — 証明結果パネル
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr_left(sl, "詳細タブ — 証明結果パネル",
             "Witness Inputs・Public Signals・Proof JSON を折りたたみパネルで表示する",
             badge="タブ 2 / 詳細")
    pnum(sl, 7)
    placeholder(sl, "詳細タブ\n（Public Signals 表示中）")

    sec(sl, "3 つの結果パネル", Inches(1.12))
    panels = [
        ("Witness Inputs",
         "ZK 回路に渡した全入力値（JSON）",
         "lat_drone, lon_drone, lat_target, lon_target,\n"
         "time_drone, time_target, detection_score 等"),
        ("Public Signals",
         "証明が成立した場合に公開される出力",
         "within30: '1' なら 30m 以内を証明\n"
         "time_ok:  '1' なら 5 秒以内を証明\n"
         "proof_ok: '1' なら全条件を満たす"),
        ("Proof JSON",
         "Groth16 証明データ（flutter_rapidsnark 出力）",
         "pi_a, pi_b, pi_c のカーブ上の点\n"
         "検証者が snarkjs verifyProof() で確認可能"),
    ]
    for i, (title, sub, detail) in enumerate(panels):
        y = Inches(1.50) + Inches(1.72) * i
        rect(sl, M, y, L_W - M, Inches(1.60), C_BOX, border=True)
        rect(sl, M, y, L_W - M, Inches(0.38), C_BLACK)
        txb(sl, title, M + Inches(0.12), y + Inches(0.05),
            L_W - M - Inches(0.24), Inches(0.28),
            size=13, bold=True, color=C_BG)
        txb(sl, sub, M + Inches(0.12), y + Inches(0.44),
            L_W - M - Inches(0.24), Inches(0.28),
            size=11, bold=True, color=C_BLACK)
        txb(sl, detail, M + Inches(0.12), y + Inches(0.75),
            L_W - M - Inches(0.24), Inches(0.80),
            size=10, color=C_TEXT, mono=True)

    txb(sl, "公開情報と秘密情報の分離",
        M, H - Inches(0.58), L_W - M, Inches(0.26),
        size=11, bold=True, color=C_BLACK)
    txb(sl,
        "Witness Inputs は完全非公開。Public Signals のみ第三者に渡し、"
        "位置情報を明かさずに「接近を証明できる」ことが ZK の核心。",
        M, H - Inches(0.32), L_W - M, Inches(0.28),
        size=10, italic=True, color=C_SUB)

    # =========================================================================
    # 8. ログタブ
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr_left(sl, "ログタブ — コンソールログ",
             "BLE・GPS・ZK 証明の動作をリアルタイムで確認する",
             badge="タブ 3 / ログ")
    pnum(sl, 8)
    placeholder(sl, "ログタブ\n（ログ流れている状態）")

    sec(sl, "画面の特徴", Inches(1.12))
    mline(sl, [
        "・背景色: #0D1117（GitHub ダークモードに近い黒）",
        "・ヘッダー: Icons.terminal + 「コンソールログ」（青色）",
        "・ログ本文: ListView で最新エントリが下に追加される",
        "・フォント: 等幅系、文字色 #CCCCCC（淡い白）",
        "・クリア機能: 「ログを消去」ボタン（赤アイコン）",
    ], M, Inches(1.50), L_W - M, Inches(1.80),
        size=12, color=C_TEXT, gap=8)

    sec(sl, "出力されるログの種類", Inches(3.48))
    tbl(sl,
        ["プレフィックス", "内容"],
        [
            ["[BLE BasicID]", "UAS_ID・RSSI（機体識別子の受信）"],
            ["[BLE Location]", "lat/lon/alt/airborne/seq/rssi"],
            ["[GPS]", "緯度・経度・精度"],
            ["[気圧]", "hPa 値・QFE 高度 m"],
            ["[ZK]", "回路名・witness 計算・proof 生成の各ステップと所要時間"],
            ["[YOLO]", "モデル読み込み・検知結果・スコア"],
            ["[BLE スキャン]", "スキャン開始・停止・エラー"],
        ],
        M, Inches(3.85), L_W - M,
        cw=[Inches(1.70), Inches(3.18)], fs=10)

    txb(sl,
        "→ BLE パケットを受信するたびに 1 行追加される。"
        "Message Pack の場合は含まれるメッセージ数ぶん出力される。",
        M, H - Inches(0.42), L_W - M, Inches(0.30),
        size=10, italic=True, color=C_SUB)

    # =========================================================================
    # 9. リアルタイム YOLO 検知画面（UavLiveDetectionPage）
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr_left(sl, "リアルタイム YOLO 検知画面",
             "カメラ映像にバウンディングボックスをリアルタイムでオーバーレイする",
             badge="サブページ / UavLiveDetectionPage")
    pnum(sl, 9)
    placeholder(sl, "YOLO 検知画面\n（バウンディングボックス表示中）")

    sec(sl, "画面の構成", Inches(1.12))
    mline(sl, [
        "・CameraPreview を全画面表示",
        "・CustomPaint (_DetectionOverlayPainter) でバウンディングボックスを描画",
        "・ボックス内にラベル名＋スコア（例: \"drone 0.82\"）を表示",
        "・350ms のクールダウンで推論頻度を制御（UI スレッドを詰まらせない）",
        "・YUV420 → RGB 変換を手動で行い TFLite 入力テンソルを作成",
    ], M, Inches(1.50), L_W - M, Inches(1.85),
        size=12, color=C_TEXT, gap=8)

    sec(sl, "モデルの優先順位", Inches(3.52))
    tbl(sl,
        ["優先度", "モデル", "説明"],
        [
            ["1st", "uav_visdrone_finetuned_config.json",
             "VisDrone データセットでファインチューニング済み YOLO"],
            ["2nd", "uav_roboflow_drone_config.json",
             "Roboflow の公開ドローン検知モデル"],
            ["3rd", "uav_yolo_config.json",
             "デフォルト YOLO（一般物体検知）"],
            ["Fallback", "Google ML Kit ImageLabeling",
             "TFLite が全て使えない場合のフォールバック"],
        ],
        M, Inches(3.88), L_W - M,
        cw=[Inches(0.72), Inches(2.30), Inches(1.86)], fs=10)

    sec(sl, "YOLO 推論パイプライン", Inches(5.82))
    mline(sl, [
        "① CameraImage (YUV420) → RGB 変換 → Float32List テンソル生成",
        "② IsolateInterpreter.run() でバックグラウンド推論（UI をブロックしない）",
        "③ 出力テンソル解析 → NMS → UavYoloDetection リスト",
        "④ CustomPainter でボックスを canvas に描画",
    ], M, Inches(6.18), L_W - M, Inches(1.12),
        size=11, color=C_TEXT, gap=6)

    # =========================================================================
    # 10. OpenDroneID 検出フロー — 全体像
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr_left(sl, "OpenDroneID 検出フロー — 全体像",
             "Pi の BLE 送信から Flutter での UI 反映まで",
             badge="OpenDroneID 検出 / 概要")
    pnum(sl, 10)
    placeholder(sl, "ログタブ\n（BLE Location 受信ログ）")

    sec(sl, "検出パイプラインの 5 ステップ", Inches(1.12))
    steps = [
        ("① Pi 送信",
         "ADV_NONCONN_IND / Extended Advertising",
         "remote_id.py が 1 秒ごとに BLE アドバタイズを発信。\n"
         "AD type 0x16（Service Data）＋ UUID 0xFFFA＋ 25B ODID メッセージ。"),
        ("② Android BLE スキャン",
         "FlutterBluePlus.startScan(timeout: 20s)",
         "withServices フィルターなし で全広告を受信。\n"
         "22 秒周期の自動再スキャンタイマーで継続監視。"),
        ("③ UUID 検索",
         "extractFromServiceData(serviceData)",
         "flutter_blue_plus の serviceData マップを走査し\n"
         "キーに 'fffa' を含むエントリを取り出す。"),
        ("④ メッセージ展開",
         "extractAllMessages(odidBytes)",
         "先頭バイトを見て単一 or Message Pack を判別。\n"
         "Pack なら 25B ずつ切り出してリストに積む。"),
        ("⑤ パース → UI 反映",
         "tryParseLocation / tryParseUasId",
         "Location → UavTelemetryPacket に変換し\n"
         "_droneHistory に追加 + フォームフィールドに反映。"),
    ]
    for i, (num, trigger, desc) in enumerate(steps):
        y = Inches(1.50) + Inches(1.12) * i
        rect(sl, M, y, L_W - M, Inches(1.02), C_BOX, border=True)
        rect(sl, M, y, Inches(0.38), Inches(1.02), C_BLACK)
        txb(sl, str(i + 1), M + Inches(0.04), y + Inches(0.28),
            Inches(0.30), Inches(0.45), size=16, bold=True,
            color=C_BG, align=PP_ALIGN.CENTER)
        txb(sl, num, M + Inches(0.48), y + Inches(0.05),
            L_W - M - Inches(0.52), Inches(0.26),
            size=12, bold=True, color=C_BLACK)
        txb(sl, trigger, M + Inches(0.48), y + Inches(0.32),
            Inches(2.40), Inches(0.24), size=9, color=C_SUB, mono=True)
        txb(sl, desc, M + Inches(0.48), y + Inches(0.56),
            L_W - M - Inches(0.52), Inches(0.44),
            size=10, color=C_TEXT)

    # =========================================================================
    # 11. BLE スキャン設定 — withServices を使わない理由
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr_left(sl, "BLE スキャン — withServices を使わない理由",
             "Pi の送信フォーマットと Android のフィルター仕様の衝突",
             badge="OpenDroneID 検出 / BLE スキャン")
    pnum(sl, 11)
    placeholder(sl, "ログタブ\n（スキャン開始ログ）")

    sec(sl, "問題: Android の withServices フィルター", Inches(1.12))
    mline(sl, [
        "android は BLE アドバタイズの AD type 0x03（Complete List of 16-bit UUIDs）を見て",
        "withServices フィルターを適用する。",
        "remote_id.py は Service Data（0x16）のみ送信し、0x03 の UUID リストを含まない。",
        "→ withServices: [0xFFFA] を指定すると、Pi のパケットが全て破棄される。",
    ], M, Inches(1.50), L_W - M, Inches(1.38),
        size=11, color=C_TEXT, gap=7)

    sec(sl, "解決策: 全受信 + 手動 UUID 検索", Inches(3.05))
    code(sl, [
        "// withServices を空にして全アドバタイズを受信",
        "await FlutterBluePlus.startScan(",
        "  timeout: const Duration(seconds: 20),",
        "  // withServices: [Guid('0000fffa-...')] ← 使わない",
        ");",
        "",
        "// serviceData マップを走査して 'fffa' を含むキーを探す",
        "static List<int>? extractFromServiceData(",
        "    Map<dynamic, List<int>> serviceData) {",
        "  for (final entry in serviceData.entries) {",
        "    final key = entry.key.toString().toLowerCase();",
        "    if (key.contains('fffa')) return entry.value;",
        "  }",
        "  return null;",
        "}",
    ], M, Inches(3.42), L_W - M, Inches(3.82), size=9)

    txb(sl,
        "flutter_blue_plus は UUID キーを 128-bit GUID 文字列で返す。\n"
        "大文字・小文字の揺れを toLowerCase() で吸収してから contains('fffa') で判定する。",
        M, H - Inches(0.50), L_W - M, Inches(0.40),
        size=10, italic=True, color=C_SUB)

    # =========================================================================
    # 12. extractAllMessages — 単一 vs Message Pack の振り分け
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr_left(sl, "extractAllMessages — パケット種別の振り分け",
             "先頭バイトで単一メッセージか Message Pack かを判別する",
             badge="OpenDroneID 検出 / メッセージ展開")
    pnum(sl, 12)
    placeholder(sl, "ログタブ\n（BasicID + Location\n同時受信の例）")

    sec(sl, "先頭バイト（Byte 0）の判定ロジック", Inches(1.12))
    code(sl, [
        "static List<List<int>> extractAllMessages(List<int> payload) {",
        "  if (payload.isEmpty) return [];",
        "  final type = (payload[0] >> 4) & 0xF;  // 上位ニブルを取る",
        "",
        "  if (type != 0xF) {",
        "    return [payload];         // 単一メッセージ → そのまま返す",
        "  }",
        "",
        "  // Message Pack (type = 0xF)",
        "  //   Byte 1 : SingleMessageSize (常に 25)",
        "  //   Byte 2 : MsgPackSize (1〜9)",
        "  //   Byte 3〜: 25B × count のメッセージ列",
        "  if (payload.length < 3) return [];",
        "  final count = payload[2];",
        "  final messages = <List<int>>[];",
        "  for (var i = 0; i < count; i++) {",
        "    final start = 3 + i * 25;",
        "    if (start + 25 > payload.length) break;",
        "    messages.add(payload.sublist(start, start + 25));",
        "  }",
        "  return messages;",
        "}",
    ], M, Inches(1.50), L_W - M, Inches(5.42), size=9)

    txb(sl, "type 値と対応するメッセージ種別",
        M, H - Inches(0.65), L_W - M, Inches(0.26),
        size=11, bold=True, color=C_BLACK)
    mline(sl, [
        "type=0x0 → BasicID（機体 ID）　type=0x1 → Location（位置・速度）　type=0xF → Message Pack",
    ], M, H - Inches(0.40), L_W - M, Inches(0.36),
        size=10, color=C_TEXT, mono=True)

    # =========================================================================
    # 13. tryParseLocation — バイトレベルのデコード
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr_left(sl, "tryParseLocation — バイトレベルのデコード",
             "25B の Location メッセージを Dart オブジェクトに変換する",
             badge="OpenDroneID 検出 / パース処理")
    pnum(sl, 13)
    placeholder(sl, "メインタブ\n（ドローンデータカード\n受信済み状態）")

    sec(sl, "Byte 0 / Byte 1 の判定", Inches(1.12))
    code(sl, [
        "final msgType = (rawBytes[0] >> 4) & 0x0F;  // type=1 なら Location",
        "if (msgType != 1) return null;               // BasicID 等は無視",
        "",
        "final byte1     = rawBytes[1] & 0xFF;",
        "final status    = (byte1 >> 4) & 0x0F; // bits 7-4: AIRBORNE=2",
        "final ewDir     = (byte1 >> 1) & 0x01; // bit  1  : 方向補正フラグ",
        "final speedMult = byte1 & 0x01;         // bit  0  : 速度スケールフラグ",
    ], M, Inches(1.50), L_W - M, Inches(2.0), size=9)

    sec(sl, "座標・高度・タイムスタンプの読み出し", Inches(3.68))
    code(sl, [
        "final data   = ByteData.sublistView(Uint8List.fromList(rawBytes));",
        "final latI32 = data.getInt32(5,  Endian.little); // bytes 5-8",
        "final lonI32 = data.getInt32(9,  Endian.little); // bytes 9-12",
        "final altBaro= data.getUint16(13,Endian.little); // bytes 13-14",
        "final altGeo = data.getUint16(15,Endian.little); // bytes 15-16",
        "final tsRaw  = data.getUint16(21,Endian.little); // bytes 21-22",
        "",
        "// デコード",
        "latitude  = latI32 / 1e7;               // 1e-7 度 → 度",
        "altitude  = altBaro * 0.5 - 1000.0;     // raw → メートル",
        "speedH    = speedMult==1 ? raw*0.75      // 高速域",
        "                        : raw*0.25;      // 低速域",
        "direction = ewDir==1 ? raw+180.0 : raw;  // 西半球補正",
        "unixTime  = hourStart + tsRaw ~/ 10;     // 時間境界＋秒内経過",
    ], M, Inches(4.05), L_W - M, Inches(3.38), size=9)

    txb(sl, "latI32 == 0 && lonI32 == 0 のときは無効座標として null を返す",
        M, H - Inches(0.32), L_W - M, Inches(0.26),
        size=10, italic=True, color=C_SUB)

    # =========================================================================
    # 14. 追加対応の動機 — Pi と実機ドローンの違い
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr_left(sl, "なぜ追加対応が必要だったか",
             "Pi（開発用）と市販ドローンでは BLE 送信の仕様が異なる",
             badge="検出強化 / 動機")
    pnum(sl, 14)
    placeholder(sl, "ログタブ\n（Pi と実機の\n受信ログ比較）")

    sec(sl, "Pi（remote_id.py）と実機ドローンの BLE 送信の違い", Inches(1.12))
    tbl(sl,
        ["項目", "Pi（remote_id.py）", "市販ドローン（DJI 等）"],
        [
            ["AD 種別",
             "Service Data (0x16)\nUUID 0xFFFA",
             "Service Data (0x16) UUID 0xFFFA\n+ 旧機種は Manufacturer Data (0x2005)"],
            ["メッセージ構造",
             "BasicID と Location を\n1 件ずつ交互に送信",
             "Message Pack (type=0xF) で\nBasicID + Location + System を\n1 パケットにまとめて送信"],
            ["メッセージ種別",
             "BasicID (0) / Location (1) のみ",
             "BasicID (0) / Location (1) /\nSystem (4) / SelfID (3) 等 全種別"],
            ["BLE 規格",
             "Legacy Advertising (BT4)\nADV_NONCONN_IND",
             "Extended Advertising (BT5)\n255B まで拡張可能"],
            ["スキャン空白",
             "（共通の問題）",
             "20s タイムアウト後 2s 空白\n→ パケットを逃す可能性"],
        ],
        M, Inches(1.50), L_W - M,
        cw=[Inches(1.40), Inches(1.75), Inches(2.43)], fs=10)

    txb(sl, "→ Pi だけでテストしていると上記の差異が見えないため、実機ドローンを受信できない実装になりやすい。",
        M, Inches(6.45), L_W - M, Inches(0.38),
        size=11, italic=True, color=C_SUB)

    rect(sl, M, Inches(6.90), L_W - M, Pt(1), C_RULE)
    txb(sl, "以降のスライドで各問題への対策コードを示す",
        M, Inches(6.97), L_W - M, Inches(0.26),
        size=10, color=C_SUB)

    # =========================================================================
    # 15. Message Pack 対応
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr_left(sl, "追加①  Message Pack 対応",
             "実機ドローンが送る「複数メッセージ束」を解析できるようにする",
             badge="検出強化 / Message Pack")
    pnum(sl, 15)
    placeholder(sl, "ログタブ\n（BasicID + Location\n同時受信の例）")

    sec(sl, "なぜ必要か", Inches(1.12))
    mline(sl, [
        "市販ドローンはほぼ必ず Message Pack（type=0xF）形式で送信する。",
        "追加前は Byte 0 の上位ニブルが 0xF のパケットを全て無視していたため、",
        "実機ドローンを受信しても UI に何も表示されなかった。",
    ], M, Inches(1.50), L_W - M, Inches(0.95), size=12, color=C_TEXT, gap=7)

    sec(sl, "追加したコード — extractAllMessages()", Inches(2.60))
    code(sl, [
        "static List<List<int>> extractAllMessages(List<int> payload) {",
        "  final type = (payload[0] >> 4) & 0xF;",
        "  if (type != 0xF) return [payload]; // 単一メッセージはそのまま返す",
        "",
        "  final count = payload[2];           // Byte 2 = メッセージ数 (1〜9)",
        "  final messages = <List<int>>[];",
        "  for (var i = 0; i < count; i++) {",
        "    final start = 3 + i * 25;         // ヘッダー 3B + 25B × i",
        "    messages.add(payload.sublist(start, start + 25));",
        "  }",
        "  return messages;",
        "}",
    ], M, Inches(2.97), L_W - M, Inches(3.22), size=9)

    sec(sl, "効果", Inches(6.32))
    mline(sl, [
        "✓  Pi（単一メッセージ）→ 従来通り動作",
        "✓  実機ドローン（Pack 3件）→ BasicID + Location + System を同一ループで取得",
        "✓  呼び出し側のコードは変更不要（戻り値をループするだけ）",
    ], M, Inches(6.65), L_W - M, Inches(0.82), size=11, color=C_TEXT, gap=5)

    # =========================================================================
    # 16. System メッセージ + DJI 旧機種 + スキャン空白
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr_left(sl, "追加②③  System メッセージ / DJI 旧機種 / スキャン空白",
             "規格完全準拠・旧機種受信・検出漏れ防止の 3 つを同時に対応",
             badge="検出強化 / 規格準拠・旧機種・空白")
    pnum(sl, 16)
    placeholder(sl, "ログタブ\n（System ログ +\nDJI 旧機種ログ）")

    # ─ System メッセージ ─
    sec(sl, "② System メッセージ (type=4) のパース", Inches(1.12))
    mline(sl, [
        "なぜ必要: 追加前は type が 0 でも 1 でもなければ全て捨てていた。",
        "ASTM F3411-22a では System（オペレーター位置）が必須メッセージだが未パースのまま。",
    ], M, Inches(1.50), L_W - M, Inches(0.70), size=11, color=C_TEXT, gap=6)
    code(sl, [
        "// 新クラス UavSystemPacket のフィールド（ZK 証明には使わない）",
        "operatorLatitude / operatorLongitude  // オペレーター位置 (int32 ÷ 1e7)",
        "operatorAltitudeGeo                   // float32 LE, m",
        "areaCount / areaRadiusMeters          // 飛行エリア件数・半径",
        "areaCeiling / areaFloor               // エリア上下限高度",
        "",
        "// スキャンハンドラで type=4 をディスパッチ",
        "if (msgType == 4) {",
        "  final sys = UavTelemetryPacket.tryParseSystem(msg);",
        "  if (sys != null) _log('[BLE System] $sys');",
        "}",
    ], M, Inches(2.27), L_W - M, Inches(2.85), size=9)

    # ─ DJI 旧機種 ─
    sec(sl, "③ DJI 旧機種  Manufacturer Data (company ID 0x2005)", Inches(5.28))
    mline(sl, [
        "なぜ必要: 旧 DJI 機は Service Data ではなく Manufacturer Data に ODID を格納する。",
        "serviceData だけ見ていると旧機種は完全にスルーされる。",
    ], M, Inches(5.65), L_W - M, Inches(0.70), size=11, color=C_TEXT, gap=6)
    code(sl, [
        "// フォールバックチェーン（スキャンハンドラ内）",
        "final odidBytes =",
        "    extractFromServiceData(ad.serviceData)   // ①標準 0xFFFA",
        " ?? extractFromManufacturerData(ad.manufacturerData); // ②旧 DJI 0x2005",
    ], M, Inches(6.42), L_W - M, Inches(1.05), size=9)

    # =========================================================================
    # 17. スキャン空白の修正 + 残存ギャップ
    # =========================================================================
    sl = prs.slides.add_slide(blank)
    hdr_left(sl, "追加④  スキャン空白の修正 と 残存ギャップ",
             "BLE 検出の限界と、コードで対処できないハード制約を整理する",
             badge="検出強化 / スキャン空白・残存課題")
    pnum(sl, 17)
    placeholder(sl, "ログタブ\n（スキャン再開ログ）")

    sec(sl, "④ スキャン空白の修正（2 秒 → 約 1 秒）", Inches(1.12))
    mline(sl, [
        "なぜ必要: 20s スキャン → 22s タイマー再発火 → 最大 2s の検出空白が生じていた。",
        "ドローンが短時間だけ BLE 圏内に入った場合にパケットを逃す恐れがある。",
    ], M, Inches(1.50), L_W - M, Inches(0.70), size=11, color=C_TEXT, gap=6)
    code(sl, [
        "// 修正前: 22 秒固定タイマー（最大 2 秒空白）",
        "Timer.periodic(Duration(seconds: 22), (_) {",
        "  if (!_isScanningDrone) _restartBleScan();",
        "});",
        "",
        "// 修正後: 1 秒ポーリングでスキャン終了を即検知",
        "Timer.periodic(Duration(seconds: 1), (_) {",
        "  if (!FlutterBluePlus.isScanningNow && !_isScanningDrone)",
        "    _restartBleScan();",
        "});",
    ], M, Inches(2.27), L_W - M, Inches(2.72), size=9)

    sec(sl, "修正後の対応状況まとめ", Inches(5.15))
    tbl(sl,
        ["ケース", "対応状況", "理由"],
        [
            ["標準 BLE (0xFFFA) 単一 / Pack", "✅ 対応済み",
             "extractAllMessages で吸収"],
            ["全メッセージ型 (type 0-5, 0xF)", "✅ ログ・パース済み",
             "type 別ディスパッチで対応"],
            ["DJI 旧機種 (0x2005 標準 ODID)", "✅ 対応済み",
             "extractFromManufacturerData"],
            ["DJI 旧機種 (0x2005 独自形式)", "⚠️ パース失敗・安全に無視",
             "実機確認が必要"],
            ["BT5 非対応 Android 端末", "❌ ハード制約",
             "コードでは解決不可"],
            ["Wi-Fi NAN / Wi-Fi Beacon", "❌ Flutter 範囲外",
             "Android NDK が必要"],
        ],
        M, Inches(5.50), L_W - M,
        cw=[Inches(2.10), Inches(1.25), Inches(1.73)], fs=9, rh=0.38)

    # =========================================================================
    prs.save(str(OUTPUT_PATH))
    print(f"保存完了: {OUTPUT_PATH}  ({TOTAL} スライド)")


if __name__ == "__main__":
    build()
