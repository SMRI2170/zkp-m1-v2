pragma circom 2.1.9;

include "lib_uav_safety.circom";

// ─────────────────────────────────────────────────────────────────────────────
// RemoteIdConsistency
//
// 「RemoteID が放送した位置」と「端末が物理的に実測したレンジ(RSSI由来)」の
// 整合を検証する最小プリミティブ。ドローン側の改造・署名を一切必要とせず、
// 地上側の観測だけで放送値の矛盾（なりすまし/リプレイ）を検出する土台。
//
//   claimed_dist = |broadcast_pos - phone_pos|      （放送値から計算した距離）
//   measured_range                                   （RSSI 等から得た実測距離, private）
//   consistency_ok = ( |claimed_dist - measured_range| <= TOL )
//
// 平方根を避けるため、すべて「スケール後の二乗距離」で比較する:
//   lower = max(measured_range - TOL, 0),  upper = measured_range + TOL
//   consistency_ok = ( lower^2 <= claimed_dist_sq <= upper^2 )
//
// 単位は Distance30mTimeCore と同じ（cm × GEO_DEN のスケール）。
// ─────────────────────────────────────────────────────────────────────────────
template RemoteIdConsistency(
    LAT_CM_NUM,
    LON_CM_NUM,
    GEO_DEN,
    TOL_CM
) {
    // 放送位置（RemoteID の申告値）
    signal input drone_lat_e7_norm;
    signal input drone_lon_e7_norm;
    signal input drone_alt_cm;

    // 端末（自分）の位置
    signal input target_lat_e7_norm;
    signal input target_lon_e7_norm;
    signal input target_alt_cm;

    // 実測レンジ（RSSI 等から回路外で算出した距離, cm）
    signal input measured_range_cm;

    signal output consistency_ok;
    signal output claimed_dist_sq; // 参照用（放送位置から計算した二乗距離）

    // ── 放送位置と端末位置の二乗距離（スケール後）────────────────────────────
    component dLat = AbsDiff(32);
    component dLon = AbsDiff(32);
    component dAlt = AbsDiff(32);
    dLat.a <== drone_lat_e7_norm;  dLat.b <== target_lat_e7_norm;
    dLon.a <== drone_lon_e7_norm;  dLon.b <== target_lon_e7_norm;
    dAlt.a <== drone_alt_cm;       dAlt.b <== target_alt_cm;

    signal lat_scaled; signal lon_scaled; signal alt_scaled;
    lat_scaled <== dLat.out * LAT_CM_NUM;
    lon_scaled <== dLon.out * LON_CM_NUM;
    alt_scaled <== dAlt.out * GEO_DEN;

    signal lat_sq; signal lon_sq; signal alt_sq;
    lat_sq <== lat_scaled * lat_scaled;
    lon_sq <== lon_scaled * lon_scaled;
    alt_sq <== alt_scaled * alt_scaled;
    claimed_dist_sq <== lat_sq + lon_sq + alt_sq;

    // ── 許容帯 [lower, upper]（cm）→ スケール後に二乗 ──────────────────────────
    // lower_cm = max(measured_range_cm - TOL_CM, 0)
    component mLtTol = LessThan(32);
    mLtTol.in[0] <== measured_range_cm;
    mLtTol.in[1] <== TOL_CM;
    signal diff_cm;
    diff_cm <== measured_range_cm - TOL_CM;
    signal lower_cm;
    lower_cm <== diff_cm * (1 - mLtTol.out); // measured<TOL のとき 0、それ以外 measured-TOL

    signal upper_cm;
    upper_cm <== measured_range_cm + TOL_CM;

    signal lower_scaled; signal upper_scaled;
    lower_scaled <== lower_cm * GEO_DEN;
    upper_scaled <== upper_cm * GEO_DEN;

    signal lower_sq; signal upper_sq;
    lower_sq <== lower_scaled * lower_scaled;
    upper_sq <== upper_scaled * upper_scaled;

    // ── 二乗距離が帯の中に収まるか ───────────────────────────────────────────
    component geLower = LessEqThan(128); // lower_sq <= claimed_dist_sq
    geLower.in[0] <== lower_sq;
    geLower.in[1] <== claimed_dist_sq;

    component leUpper = LessEqThan(128); // claimed_dist_sq <= upper_sq
    leUpper.in[0] <== claimed_dist_sq;
    leUpper.in[1] <== upper_sq;

    consistency_ok <== geLower.out * leUpper.out;
}

component main = RemoteIdConsistency(
    11132000,   // LAT_CM_NUM
    9128800,    // LON_CM_NUM
    10000000,   // GEO_DEN
    500         // TOL_CM: 実測レンジの許容誤差 5 m（RSSI は粗いので広め）
);
