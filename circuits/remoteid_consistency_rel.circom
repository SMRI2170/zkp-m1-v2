pragma circom 2.1.9;

include "lib_uav_safety.circom";

// ─────────────────────────────────────────────────────────────────────────────
// RemoteIdConsistencyRel
//
// remoteid_consistency.circom の「相対許容(±%)」版。
//
// RSSI の距離誤差は乗法的（相対%）なので、固定 TOL_CM ではなく
// 実測レンジに比例した帯 [measured*(1-r), measured*(1+r)] で整合を判定する。
//   r = TOL_NUM / TOL_DEN     （例 90/100 = ±90%）
//
// 平方根/除算を避けるため、スケール後の二乗＋分母倍で整数比較に落とす:
//   d_claim_scaled = sqrt(claimed_dist_sq)          （= D_cm * GEO_DEN）
//   base           = measured_range_cm * GEO_DEN
//   条件 lower ≤ d_claim ≤ upper を DEN 倍して二乗:
//     (base*(DEN-NUM))^2 ≤ claimed_dist_sq*DEN^2 ≤ (base*(DEN+NUM))^2
//
// 前提: 0 <= TOL_NUM <= TOL_DEN（下限が非負に保たれる）。
// ─────────────────────────────────────────────────────────────────────────────
template RemoteIdConsistencyRel(
    LAT_CM_NUM,
    LON_CM_NUM,
    GEO_DEN,
    TOL_NUM,
    TOL_DEN
) {
    // 放送位置（RemoteID 申告値）
    signal input drone_lat_e7_norm;
    signal input drone_lon_e7_norm;
    signal input drone_alt_cm;

    // 端末（自分）の位置
    signal input target_lat_e7_norm;
    signal input target_lon_e7_norm;
    signal input target_alt_cm;

    // 実測レンジ（RSSI 等から回路外で算出, cm）
    signal input measured_range_cm;

    signal output consistency_ok;
    signal output claimed_dist_sq;

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

    // ── 相対帯（コンパイル時定数で係数化）────────────────────────────────────
    // LOWER = DEN - NUM, UPPER = DEN + NUM
    var LOWER = TOL_DEN - TOL_NUM;
    var UPPER = TOL_DEN + TOL_NUM;

    signal base;
    base <== measured_range_cm * GEO_DEN;

    signal lower_num; signal upper_num;
    lower_num <== base * LOWER;
    upper_num <== base * UPPER;

    signal lower_sq; signal upper_sq;
    lower_sq <== lower_num * lower_num;
    upper_sq <== upper_num * upper_num;

    // claimed を DEN^2 倍して同じスケールに
    signal claimed_scaled;
    claimed_scaled <== claimed_dist_sq * (TOL_DEN * TOL_DEN);

    // ── lower_sq <= claimed_scaled <= upper_sq ───────────────────────────────
    component geLower = LessEqThan(200);
    geLower.in[0] <== lower_sq;
    geLower.in[1] <== claimed_scaled;

    component leUpper = LessEqThan(200);
    leUpper.in[0] <== claimed_scaled;
    leUpper.in[1] <== upper_sq;

    consistency_ok <== geLower.out * leUpper.out;
}

component main = RemoteIdConsistencyRel(
    11132000,   // LAT_CM_NUM
    9128800,    // LON_CM_NUM
    10000000,   // GEO_DEN
    90,         // TOL_NUM  ┐ r = 90/100 = ±90%（RSSI ±2σ 相当。実機較正後に更新）
    100         // TOL_DEN  ┘
);
