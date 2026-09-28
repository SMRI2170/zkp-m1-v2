#!/usr/bin/env python3
"""week20 Nova(方式B)実装まとめ — 進捗第11回スタイル・4:3。

構成: なぜNovaか→使用ライブラリ(Sonobe)→技術構成→自作コード→ハマった所→
実測(デスクトップ)→モバイル実装→3スタック比較→まとめ。
参照元: week20/04, 06, 07, 08, 09, 11。
"""

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
prs.slide_width = Inches(10)     # 4:3
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
    run(tf.paragraphs[0], text, 22, INK, bold=True)
    hrule(s, 1.14)


def _vlen(t):
    return int(sum(0.5 if ord(c) < 0x3000 else 1.0 for c in t))


def bullets(s, y, items, size0=16.5, size1=14.5):
    tf = s.shapes.add_textbox(Inches(L), Inches(y), Inches(W), Inches(0.4)).text_frame
    tf.word_wrap = True
    h = 0.0
    for i, (lv, text) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_before = Pt(0 if i == 0 else (6 if lv == 0 else 3))
        size = size0 if lv == 0 else size1
        run(p, ("■ " if lv == 0 else "　　・ "), size, INK); run(p, text, size, INK)
        cpl = max(14, int(590 / size)); lh = size * 1.5 / 72.0
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


def callout(s, y, head, body, w=W, fs=16):
    bh = 0.95
    box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(L), Inches(y), Inches(w), Inches(bh))
    box.fill.solid(); box.fill.fore_color.rgb = CODEBG
    box.line.color.rgb = INK; box.line.width = Pt(1.25); box.shadow.inherit = False
    tf = box.text_frame; tf.word_wrap = True
    tf.margin_left = Pt(12); tf.margin_right = Pt(12); tf.margin_top = Pt(8)
    run(tf.paragraphs[0], head, 13, GRAY, bold=True)
    p = tf.add_paragraph(); p.space_before = Pt(4)
    run(p, body, fs, INK, bold=True)
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


def table(s, y, rows, col_w, fs=12, row_h=0.42):
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


def section(num, text):
    s = add_slide()
    tf = s.shapes.add_textbox(Inches(0.9), Inches(2.9), Inches(8.2), Inches(0.5)).text_frame
    run(tf.paragraphs[0], num, 15, GRAY, bold=True)
    tf = s.shapes.add_textbox(Inches(0.88), Inches(3.35), Inches(8.4), Inches(1.0)).text_frame
    tf.word_wrap = True
    run(tf.paragraphs[0], text, 26, INK, bold=True)
    hrule(s, 4.4, l=0.92, w=4.0, color=INK)
    return s


# ════════════════════════════════════════════════════════════════════════════
# 0. 表紙
s = add_slide(number=False)
tf = s.shapes.add_textbox(Inches(0.9), Inches(2.5), Inches(8.3), Inches(1.5)).text_frame
tf.word_wrap = True
run(tf.paragraphs[0], "Nova（方式B）実装まとめ", 30, INK, bold=True)
p = tf.add_paragraph(); p.space_before = Pt(4)
run(p, "Sonobe（Rust, folding-schemes）による再帰チェーンIVC", 20, INK, bold=True)
hrule(s, 4.5, l=0.92, w=5.6)
tf = s.shapes.add_textbox(Inches(0.92), Inches(4.66), Inches(8.2), Inches(0.6)).text_frame
run(tf.paragraphs[0], "設計 → ライブラリ選定 → 実装 → デスクトップ実測 → モバイル実機実測", 14, INK)
tf = s.shapes.add_textbox(Inches(0.92), Inches(6.5), Inches(8.0), Inches(0.5)).text_frame
run(tf.paragraphs[0], "week20 統合（04・06・07・08・09・11）", 12, GRAY)

# ── 一言まとめ ──
s = add_slide(); title(s, "一言まとめ")
bullets(s, TOP, [
    (0, "Nova = 前の証明を「検証」でなく「折り畳む(fold)」IVC方式（論文名）"),
    (0, "使ったライブラリ = Sonobe（0xPARC + PSE開発、Rust、folding-schemes crate）"),
    (0, "自作したもの = RSSI整合を判定するステップ回路＋モバイル向けUniFFIラッパー"),
    (0, "達成 = デスクトップ実測 → 実機Pixel 8でのAndroidアプリ動作まで完走"),
    (0, "結論 = 方式A（gnark再帰検証）よりメモリ約9分の1・速度約30〜50倍、モバイル実行の本命"),
], size0=15.5)

# 1. なぜNovaか
section("Part 1", "なぜNova（方式B）を検討したか")

s = add_slide(); title(s, "出発点 = 方式A（gnark再帰検証）が主軸だった")
bullets(s, TOP, [
    (0, "再帰チェーン(IVC)設計は当初、方式A（gnark, 再帰検証）を主軸に確定（week20/04）"),
    (1, "各累積が単体で検証可能＝「取ってきて検証」に忠実／BN254のままEVMに着地できる"),
    (0, "方式B（Nova/Sonobe, Folding）は「省メモリな代替」として温存されるだけだった"),
    (0, "Nova特有の弱点として温存: 中間証明が単体検証不可（最後にまとめて検証）"),
])

s = add_slide(); title(s, "転機 = 方式Aのスマホ実行が非現実的と判明（week20/07）")
y = table(s, TOP, [
    ["指標", "方式A（gnark, chainpoc実測）"],
    ["ピークメモリ", "約4.04GB"],
    ["1ステップ証明生成", "7〜9秒（M2 Mac, 8コア）"],
    ["外部WASM実測（参考, 同スタック36分の1規模）", "iPhone 12は4GBメモリ不足で失敗"],
], col_w=[4.4, 4.2], fs=13, row_h=0.55)
y = bullets(s, y + 0.08, [
    (0, "→ 比較のため方式B（Nova/Sonobe）を実装して実測することにした（week20/08）"),
], size0=15)

# 2. ライブラリ選定
section("Part 2", "使用ライブラリ = Sonobe")

s = add_slide(); title(s, "用語整理 — 「Nova」と「Sonobe」は別物")
bullets(s, TOP, [
    (0, "Nova = folding scheme（IVC構成法）という手法の名前（論文, 2021）"),
    (1, "前のインスタンスと新しいインスタンスを1つに折り畳む(fold)ことでIVCを実現"),
    (0, "Sonobe = そのNova（＋HyperNova・ProtoGalaxy・CycleFold）を実装したRustライブラリ"),
    (1, "0xPARC + PSE（Privacy & Scaling Explorations）が共同開発。本プロジェクトが実際に使用"),
    (0, "＝「Sonobeというライブラリで、Novaという折り込み方式を使った」という関係"),
], size0=15.5)

s = add_slide(); title(s, "ライブラリ候補比較（2026-07時点で調査）")
table(s, TOP, [
    ["候補", "最終更新", "判断"],
    ["Nova-Scotia（circom→Nova変換）", "2024-03（2年以上前）", "見送り・事実上メンテ停止"],
    ["microsoft/Nova（原論文の参照実装）", "2026-06-19", "現役だが低レベルAPI"],
    ["arecibo（Novaのfork）", "2025-03-03", "見送り"],
    ["Sonobe（Nova+HyperNova+ProtoGalaxy+CycleFold）", "2026-07-19（4日前）", "採用"],
], col_w=[3.6, 2.0, 3.0], fs=11.5, row_h=0.55)

s = add_slide(); title(s, "採用理由")
bullets(s, TOP, [
    (0, "調査時点でもっとも活発（4日前更新）"),
    (0, "Nova単体でなくCycleFold（曲線サイクルによる折り込み）まで実装済み"),
    (1, "BN254で最終的にEVM verifierを出せる設計＝設計方針「BN254/EVM着地」と整合"),
    (0, "solidity-verifiers crateでオンチェーン検証コントラクト出力まで見据えている"),
    (0, "HyperNova・ProtoGalaxyなど周辺方式も同一ライブラリ内 → 将来の方式変更コストが低い"),
])

s = add_slide(); title(s, "リポジトリ情報")
table(s, TOP, [
    ["項目", "内容"],
    ["リポジトリ", "github.com/privacy-scaling-explorations/sonobe"],
    ["開発元", "0xPARC + PSE（Privacy & Scaling Explorations）"],
    ["ライセンス", "MIT"],
    ["本プロジェクトでの配置", "nova_poc/sonobe/（vendored clone・gitignore対象・再生成可）"],
], col_w=[2.6, 6.0], fs=12, row_h=0.5)

# 3. 技術構成
section("Part 3", "技術構成")

s = add_slide(); title(s, "折り込み方式・曲線・コミットメント")
y = code(s, TOP, [
    "Nova<Projective, Projective2, ChainStepCircuit<Fr>,",
    "     KZG<Bn254>, Pedersen<Projective2>, false>",
])
bullets(s, y + 0.1, [
    (0, "折り込み方式 = Nova + CycleFold（非ネイティブ算術コストを避ける補助折り込み）"),
    (0, "曲線サイクル = 主曲線 BN254 ↔ 副曲線 Grumpkin（CycleFold用）"),
    (1, "BN254が主曲線 = 最終的にEVM（Solidity）検証を視野に入れているため"),
    (0, "コミットメント = 主曲線側KZG（trusted setup要）／副曲線側Pedersen（不要）"),
    (0, "回路記述 = SonobeのFCircuitトレイトを arkworks の R1CS で直接実装（gnarkのfrontend.API相当）"),
], size0=14.5)

s = add_slide(); title(s, "自作したステップ回路 = ChainStepCircuit")
bullets(s, TOP, [
    (0, "circom版(remoteid_consistency_rel)・gnark版(chainpoc)・Noir版と同じ関係を移植"),
    (0, "状態 z = (drone_id, time_bucket, consistent_count, suspicious_count, step_count)"),
])
code(s, 3.0, [
    "impl FCircuit<F> for ChainStepCircuit<F> {",
    "  type ExternalInputs = [F; 7];  // drone/target lat,lon,alt + measured_range_cm",
    "  fn state_len() -> usize { 5 }",
    "  fn generate_step_constraints(z_i, external_inputs) {",
    "    let ok = rssi_consistency_ok(...);           // 相対許容帯±90%判定",
    "    [z_i[0], z_i[1], z_i[2]+ok, z_i[3]+(1-ok), z_i[4]+1]",
    "  }",
    "}",
], fs=12.5)

# 4. 実際の回路コードと実行ファイル
section("Part 4", "実際の回路コードと実行ファイル")

s = add_slide(); title(s, "実際の回路コード① RSSI整合判定（前半）")
code(s, TOP, [
    "// nova_poc/nova-mobile/src/lib.rs",
    "const LAT_CM_NUM: u64 = 11_132_000;",
    "const LON_CM_NUM: u64 = 9_128_800;",
    "const GEO_DEN: u64 = 10_000_000;",
    "const TOL_NUM: u64 = 90;   const TOL_DEN: u64 = 100;",
    "",
    "fn abs_diff<F: PrimeField>(a: &FpVar<F>, b: &FpVar<F>)",
    "    -> Result<FpVar<F>, SynthesisError> {",
    "    let a_lt_b = a.is_cmp(b, Ordering::Less, false)?;",
    "    FpVar::conditionally_select(&a_lt_b, &(b - a), &(a - b))",
    "}",
    "",
    "let d_lat = abs_diff(drone_lat, target_lat)?;",
    "let d_lon = abs_diff(drone_lon, target_lon)?;",
    "let d_alt = abs_diff(drone_alt, target_alt)?;",
    "let lat_scaled = &d_lat * FpVar::constant(F::from(LAT_CM_NUM));",
    "let lon_scaled = &d_lon * FpVar::constant(F::from(LON_CM_NUM));",
    "let alt_scaled = &d_alt * FpVar::constant(F::from(GEO_DEN));",
], fs=11)

s = add_slide(); title(s, "実際の回路コード② RSSI整合判定（後半）")
y = code(s, TOP, [
    "let claimed_dist_sq = &lat_scaled * &lat_scaled",
    "    + &lon_scaled * &lon_scaled + &alt_scaled * &alt_scaled;",
    "let lower = TOL_DEN - TOL_NUM;   // 10",
    "let upper = TOL_DEN + TOL_NUM;   // 190",
    "let base = measured_range_cm * FpVar::constant(F::from(GEO_DEN));",
    "let lower_num = &base * FpVar::constant(F::from(lower));",
    "let upper_num = &base * FpVar::constant(F::from(upper));",
    "let lower_sq = &lower_num * &lower_num;",
    "let upper_sq = &upper_num * &upper_num;",
    "let claimed_scaled = &claimed_dist_sq",
    "    * FpVar::constant(F::from(TOL_DEN * TOL_DEN));",
    "",
    "let ge_lower = lower_sq.is_cmp(&claimed_scaled, Ordering::Less, true)?;",
    "let le_upper = claimed_scaled.is_cmp(&upper_sq, Ordering::Less, true)?;",
    "let ok_bool = Boolean::kary_and(&[ge_lower, le_upper])?;",
], fs=10.5)
bullets(s, y + 0.1, [
    (0, "is_cmp = FpVar専用の比較API（このあとPart 5③で解説する論理バグ修正で辿り着いた実装）"),
], size0=13)

s = add_slide(); title(s, "実際の回路コード③ FCircuit実装（状態遷移）")
code(s, TOP, [
    "impl<F: PrimeField> FCircuit<F> for ChainStepCircuit<F>",
    "where F: Absorb {",
    "    type ExternalInputs = [F; 7];",
    "    type ExternalInputsVar = [FpVar<F>; 7];",
    "    fn state_len(&self) -> usize { 5 }",
    "",
    "    fn generate_step_constraints(&self, _cs, _i,",
    "        z_i: Vec<FpVar<F>>, external_inputs: Self::ExternalInputsVar,",
    "    ) -> Result<Vec<FpVar<F>>, SynthesisError> {",
    "        let [drone_lat, drone_lon, drone_alt, target_lat,",
    "             target_lon, target_alt, measured_range_cm] = external_inputs;",
    "        let ok = rssi_consistency_ok(&drone_lat, &drone_lon, ...)?;",
    "",
    "        Ok(vec![",
    "            z_i[0].clone(),                     // drone_id",
    "            z_i[1].clone(),                     // time_bucket",
    "            &z_i[2] + &ok,                       // consistent_count",
    "            &z_i[3] + (FpVar::constant(F::one()) - &ok), // suspicious",
    "            &z_i[4] + FpVar::constant(F::one()), // step_count",
    "        ])",
    "    }",
    "}",
], fs=10.5)

s = add_slide(); title(s, "実際の回路コード④ モバイル向けUniFFIラッパー")
code(s, TOP, [
    "// nova_poc/nova-mobile/src/lib.rs",
    "#[derive(uniffi::Object)]",
    "pub struct ChainState { inner: Mutex<N> }",
    "",
    "#[uniffi::export]",
    "impl ChainState {",
    "    #[uniffi::constructor]",
    "    pub fn new(drone_id: u64, time_bucket: u64)",
    "        -> Result<Arc<Self>, NovaMobileError> {",
    "        let params = get_params()?;   // OnceLockでpreprocessをキャッシュ",
    "        let f_circuit = ChainStepCircuit::<Fr>::new(())?;",
    "        let initial_state = vec![Fr::from(drone_id), Fr::from(time_bucket),",
    "            Fr::from(0u64), Fr::from(0u64), Fr::from(0u64)];",
    "        let fs = N::init(params, f_circuit, initial_state)?;",
    "        Ok(Arc::new(Self { inner: Mutex::new(fs) }))",
    "    }",
    "",
    "    pub fn prove_step(&self, obs: ObservationInput)",
    "        -> Result<(), NovaMobileError> {",
    "        self.inner.lock().unwrap().prove_step(OsRng, ext, None)?;",
    "        Ok(())",
    "    }",
    "}",
], fs=10.5)

s = add_slide(); title(s, "実行ファイル（バイナリ）の全体構成")
y = table(s, TOP, [
    ["ファイル", "種別", "役割"],
    ["nova_poc/uav_chain_step.rs", "example", "デスクトップPoC本体（week20/08）"],
    ["nova-mobile crate本体", "lib/cdylib/staticlib", "Nova IVCのUniFFIラッパー本体"],
    ["src/bin/uniffi-bindgen.rs", "bin（ホスト向け）", "Kotlinバインディング生成CLI"],
    ["src/bin/on_device_bench.rs", "bin（aarch64-android）", "UI無しで実機直接ベンチ"],
    ["tests/chain_state.rs", "test", "3ステップ結果をweek20/08と照合"],
], col_w=[3.1, 2.2, 3.3], fs=10.5, row_h=0.5)
bullets(s, y + 0.05, [
    (0, "nova-mobileの[lib]は crate-type=[\"lib\",\"cdylib\",\"staticlib\"] の3種を同時出力"),
], size0=13)

s = add_slide(); title(s, "実行ファイル① uav_chain_step（デスクトップ検証用）")
code(s, TOP, [
    "// nova_poc/sonobe/ 配下で（examplesへコピー後）",
    "cargo run --release --example uav_chain_step -p folding-schemes",
], fs=13)
bullets(s, 2.9, [
    (0, "中身 = drone_id/time_bucket固定＋3ステップの観測（整合×2, なりすまし×1）をハードコード"),
    (0, "preprocess→init→prove_step×3→ivc_proof()→verify()→改ざんz_iでの否定系検証、を順に実行し標準出力へ時間を出す"),
    (0, "week20/08の全実測数値（130〜280ms/step等）はこのバイナリの出力そのもの"),
], size0=14)

s = add_slide(); title(s, "実行ファイル② on_device_bench（実機直接ベンチ用）")
code(s, TOP, [
    "cargo build --release --target aarch64-linux-android -p nova-mobile \\",
    "  --bin on_device_bench",
    "adb push target/aarch64-linux-android/release/on_device_bench /data/local/tmp/",
    "adb shell chmod +x /data/local/tmp/on_device_bench",
    "adb shell /data/local/tmp/on_device_bench",
], fs=11.5)
bullets(s, 3.6, [
    (0, "中身 = ChainState経由でuav_chain_stepと同じ3ステップをRust APIから直接呼ぶだけ"),
    (0, "UI/Kotlin/UniFFI越境を一切介さない「素の実行ファイル」＝実機の生の処理時間を測る狙い"),
    (0, "week20/09の実機実測（966ms〜2.27秒/step等, UI無し経路）はこのバイナリの出力"),
], size0=14)

s = add_slide(); title(s, "実行ファイル③ uniffi-bindgen（Kotlinバインディング生成）")
code(s, TOP, [
    "// nova_poc/nova-mobile/src/bin/uniffi-bindgen.rs（全文）",
    "fn main() {",
    "    uniffi::uniffi_bindgen_main()",
    "}",
], fs=13.5)
y = code(s, 3.3, [
    "cargo build --release -p nova-mobile --bin uniffi-bindgen   # ホスト向け",
    "./target/release/uniffi-bindgen generate \\",
    "  --library target/aarch64-linux-android/release/libnova_mobile.so \\",
    "  --language kotlin --out-dir ../kotlin_bindings",
], fs=11.5)
bullets(s, y + 0.1, [
    (0, "中身はUniFFI本体のCLIをそのまま呼ぶだけの3行。生成物がnova_mobile.kt（1587行）"),
], size0=13.5)

# 5. ハマった所
section("Part 5", "実装でハマった所（3つ）")

s = add_slide(); title(s, "① arkworksの破壊的バージョン移行（16回のビルド試行）")
bullets(s, TOP, [
    (0, "Sonobeがark-groth16を古いgitコミットに固定・他は無指定(HEAD追従)"),
    (0, "取得時期にarkworks本体が0.5.0→0.6.0へ一斉に上がり噛み合わなくなった"),
    (0, "対処 = [patch]機構と格闘するより、crates.io公開済み0.6.0系に全体を統一"),
    (1, "教訓: rev無指定のgit依存は、活発なライブラリほど破壊的変更に巻き込まれやすい"),
])

s = add_slide(); title(s, "② フォーク独自APIとの非互換")
bullets(s, TOP, [
    (0, "Sonobeが依存するark-r1cs-stdのフォークに独自メソッド joint_scalar_mul_be があった"),
    (0, "公式0.6.0のark-r1cs-stdには未マージ → コンパイルエラー"),
    (0, "対処 = 機能的に等価な scalar_mul_le の2回呼び出し+加算に置換（6箇所）"),
    (1, "正しさは同一、効率のみコミットメント検証部分にわずかな影響"),
])

s = add_slide(); title(s, "③ 比較APIの選択ミスによる論理バグ")
bullets(s, TOP, [
    (0, "現象: 値はすべて正しいのに、大小比較の結果だけが常にfalseになる"),
    (0, "原因: FpVarをto_bits_be()でビット分解し、自作の辞書式比較で判定していた"),
])
code(s, 3.5, [
    "// 誤り（値は正しいのに比較結果が常にfalse）",
    "lower_sq.to_bits_be()?.is_le(claimed_scaled.to_bits_be()?)?",
    "",
    "// 修正後（専用APIに置換 → 即座に正しい結果）",
    "lower_sq.is_cmp(&claimed_scaled, Ordering::Less, true)?",
], fs=12.5)

# 5. デスクトップ実測
section("Part 6", "実測結果（デスクトップ, M2 Mac）")

s = add_slide(); title(s, "3ステップ実行結果")
table(s, TOP, [
    ["step", "内容", "prove_step", "結果"],
    ["1", "整合な観測(距離≈341cm)", "135ms", "consistent=1"],
    ["2", "整合な観測", "151ms", "consistent=2"],
    ["3", "なりすまし観測(measured=5000cm)", "281ms", "suspicious=1"],
], col_w=[0.7, 3.9, 1.7, 2.3], fs=12, row_h=0.5)
bullets(s, 3.7, [
    (0, "IVC証明の検証は28ms・改ざん(z_iの書換)は期待通り拒否"),
    (0, "gnark版(方式A)と完全に同じ推移（1→2→2 / 0→0→1）を再現"),
], size0=14.5)

s = add_slide(); title(s, "方式A(gnark) vs 方式B(Nova/Sonobe) 定量比較")
table(s, TOP, [
    ["指標", "方式A（gnark）", "方式B（Nova/Sonobe）", "比率"],
    ["セットアップ（1回きり）", "約2〜3分/回路", "625ms", "200〜300倍高速"],
    ["1ステップの証明生成", "7〜9秒", "130〜280ms", "約30〜50倍高速"],
    ["検証", "数ミリ秒", "28ms", "同程度"],
    ["ピークメモリ", "約4.04GB", "約456MB", "約9倍少ない"],
], col_w=[2.6, 1.9, 2.4, 1.7], fs=11.5, row_h=0.5)

# 6. モバイル実装
section("Part 7", "モバイル実装（Android実機まで）")

s = add_slide(); title(s, "配線 = UniFFIによる自作ラッパー")
bullets(s, TOP, [
    (0, "circom/NoirはMopro公式アダプタ経由だが、Novaには公式アダプタが存在しない"),
    (0, "→ UniFFI（Mozilla製, Rust→Swift/Kotlin自動生成）を直接使う自作crateで対応"),
    (0, "nova_poc/nova-mobile/ … ChainState（uniffi::Object）として4メソッドを公開"),
], size0=15)
code(s, 3.7, [
    "ChainState::new(drone_id, time_bucket)   preprocessを初回のみ実行しキャッシュ",
    "ChainState::prove_step(obs)              1ステップ進める(内部でMutexロック)",
    "ChainState::verify() -> bool             現在までのIVC証明を検証",
    "ChainState::state() -> Vec<String>       z=(drone_id,time,consistent,suspicious,step)",
], fs=12)

s = add_slide(); title(s, "クロスコンパイル → 実機dlopen成功")
bullets(s, TOP, [
    (0, "aarch64-linux-android向けクロスコンパイル = エラーなく成功（既知の無害warningのみ）"),
    (0, "libnova_mobile.so の動的依存 = libc.so/libm.so/libdl.soのみ（libc++系の依存なし）"),
    (1, "Rust製でC++ランタイム依存の外部Cライブラリを使わないため"),
    (1, "Noirが踏んだ「別コンパイラ由来の静的ライブラリのtypedef mangling不一致」が原理的に発生しない"),
    (0, "→ ビルド成功がそのままランタイム成功に直結（実機Pixel 8でdlopen/dlsym確認済み）"),
], size0=14.5)

s = add_slide(); title(s, "実機Pixel 8での実測")
table(s, TOP, [
    ["経路", "1ステップの証明生成", "検証"],
    ["素のバイナリ（UI無し, on_device_bench）", "966ms〜2.27秒", "357ms"],
    ["Android UI経由（nova-android-demo）", "485〜1198ms", "172ms"],
], col_w=[4.0, 2.9, 1.7], fs=12, row_h=0.55)
bullets(s, 3.6, [
    (0, "z の推移・verify()=true とも week20/08 のデスクトップ実装と完全一致"),
    (0, "方式A(gnark)実機推定「7〜9秒/step」よりも桁で有利 → 「タップして証明→検証」まで実証"),
], size0=14)

s = add_slide(); title(s, "Android UIアプリ = nova-android-demo")
bullets(s, TOP, [
    (0, "最小構成のネイティブAndroid(Kotlin)アプリ（AGP 8.7.0 / Kotlin 2.1.0）"),
    (0, "circom/NoirはFlutterアプリに統合済みだが、Novaだけ独立したネイティブアプリ"),
    (1, "UniFFIの生Kotlin出力のため、flutter_rust_bridge経由にせずKotlinで直接組む方が最短だった"),
    (0, "画面 = 「3ステップ実行」ボタン1つ＋ログ表示 → タップで3ステップ証明生成→検証まで完走"),
], size0=15)

# 7. 3スタック比較
section("Part 8", "circom / Noir / Nova 実機3スタック比較")

s = add_slide(); title(s, "実機（Pixel 8, Android 16 API 36）横断比較")
table(s, TOP, [
    ["スタック", "証明生成", "検証", "状態"],
    ["circom（rapidsnark）", "402ms", "166ms", "✅ 完全動作"],
    ["Noir（barretenberg）", "平均926ms（範囲731〜1071ms, 10回）", "平均37ms（範囲10〜56ms）", "✅ 完全動作"],
    ["Nova（UI経由, UniFFI/Kotlin）", "485〜1198ms/step", "172ms", "✅ 完全動作"],
], col_w=[2.0, 3.4, 2.2, 1.0], fs=10.8, row_h=0.6)
bullets(s, 4.6, [
    (0, "circom・Noir・Nova の3スタックすべてが実機で実回路の動作を確認済み"),
    (0, "gnark(方式A)のみ、モバイルでは非現実的なため設計上除外のまま"),
], size0=14.5)

# 8. まとめ
section("Part 9", "まとめ・今後")

s = add_slide(); title(s, "成果まとめ")
bullets(s, TOP, [
    (0, "Sonobe（Rust, 0xPARC+PSE）でNova+CycleFoldのIVCを実装"),
    (0, "方式A(gnark)と同じ検知結果を再現しつつ、メモリ約9分の1・速度約30〜50倍を実測"),
    (0, "自作UniFFIラッパーでAndroidクロスコンパイル・実機dlopen・UI組込みまで完走"),
    (0, "実機Pixel 8で3ステップ証明生成→検証を実測（circom・Noirと並ぶ3本目の実証スタック）"),
], size0=15.5)

s = add_slide(); title(s, "残課題・今後")
bullets(s, TOP, [
    (0, "Step D相当 = 最終圧縮(wrap)→EVM verifier出力は未着手（solidity-verifiersが対応候補）"),
    (0, "中間証明が単体検証不可という方式Bの構造的トレードオフは健在（「取ってきて検証」には方式Aが忠実）"),
    (0, "iOS（Swift側UniFFIバインディング）は未検証"),
    (0, "vendored clone は特定コミットへのpin無し（git clone --depth 1のHEAD依存、再現性の注意点）"),
], size0=15)

OUT = os.path.join(os.path.dirname(__file__), "..", "week20", "slides_Nova_week20.pptx")
prs.save(OUT)
print(f"saved: {os.path.abspath(OUT)}  ({len(prs.slides._sldIdLst)} slides)")
