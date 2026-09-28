// RSSI整合判定（Noir版）── circuits/remoteid_consistency_rel.circom(RemoteIdConsistencyRel)
// と完全に同じ計算・同じ係数。gnark版(week20/06 §1.4)・Nova版(week20/08)との性能比較のため、
// 式を一切変えずに移植する。
//
// 申告位置(drone)と自位置(target)から幾何距離の二乗を求め、RSSI実測レンジ(measured_range_cm)の
// 相対許容帯 ±90% と整数のまま比較する（平方根・除算を避ける設計は他言語版と同じ）。
// u128で計算する（claimed_dist_sq等は最大で概ね2^90程度に達するため、u64ではオーバーフローする）。

global LAT_CM_NUM: u128 = 11132000;
global LON_CM_NUM: u128 = 9128800;
global GEO_DEN: u128 = 10000000;
global TOL_NUM: u128 = 90;
global TOL_DEN: u128 = 100;

fn abs_diff(a: u128, b: u128) -> u128 {
    if a > b { a - b } else { b - a }
}

// 戻り値: 1 なら整合、0 ならなりすまし（不整合）
fn rssi_consistency_ok(
    drone_lat: u128, drone_lon: u128, drone_alt: u128,
    target_lat: u128, target_lon: u128, target_alt: u128,
    measured_range_cm: u128,
) -> bool {
    let d_lat = abs_diff(drone_lat, target_lat);
    let d_lon = abs_diff(drone_lon, target_lon);
    let d_alt = abs_diff(drone_alt, target_alt);

    let lat_scaled = d_lat * LAT_CM_NUM;
    let lon_scaled = d_lon * LON_CM_NUM;
    let alt_scaled = d_alt * GEO_DEN;

    let claimed_dist_sq = lat_scaled * lat_scaled + lon_scaled * lon_scaled + alt_scaled * alt_scaled;

    let lower = TOL_DEN - TOL_NUM; // 10
    let upper = TOL_DEN + TOL_NUM; // 190

    let base = measured_range_cm * GEO_DEN;
    let lower_num = base * lower;
    let upper_num = base * upper;
    let lower_sq = lower_num * lower_num;
    let upper_sq = upper_num * upper_num;

    let claimed_scaled = claimed_dist_sq * (TOL_DEN * TOL_DEN);

    let ge_lower = lower_sq <= claimed_scaled;
    let le_upper = claimed_scaled <= upper_sq;

    ge_lower & le_upper
}

// 累積状態 z = (drone_id, time_bucket, consistent_count, suspicious_count, step_count) の
// 1ステップぶん。week20/06(gnark)・week20/08(Nova)と同じ関係を強制する。
// drone_lat等は秘匿（回路の外に出ない）、z関連は公開。
fn main(
    drone_id: pub Field,
    time_bucket: pub Field,
    prev_consistent_count: pub u64,
    prev_suspicious_count: pub u64,
    prev_step_count: pub u64,
    consistent_count: pub u64,
    suspicious_count: pub u64,
    step_count: pub u64,
    drone_lat: u128,
    drone_lon: u128,
    drone_alt: u128,
    target_lat: u128,
    target_lon: u128,
    target_alt: u128,
    measured_range_cm: u128,
) {
    let ok = rssi_consistency_ok(
        drone_lat, drone_lon, drone_alt,
        target_lat, target_lon, target_alt,
        measured_range_cm,
    );
    let ok64 = ok as u64;

    assert(consistent_count == prev_consistent_count + ok64);
    assert(suspicious_count == prev_suspicious_count + (1 - ok64));
    assert(step_count == prev_step_count + 1);
}
