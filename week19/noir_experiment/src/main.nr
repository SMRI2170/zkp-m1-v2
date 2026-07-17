// UAV RSSI 多端末合意回路（Noir 試作）
//
// 目的（現行 circom 回路の Noir 版プロトタイプ）:
//   - RSSI 検証 + 距離検証: 各端末が「放送位置からの幾何距離 d_claim」と
//     「RSSI からの推定距離 d_meas」を持ち、両者が相対許容帯 r=2.1 で整合し、
//     かつ 30m 以内かを判定する（単端末判定）。
//   - 多端末を1回路に集約: N 端末ぶんを1つの証明にまとめ、
//     同一ドローン(drone_id)への束縛と、整合端末数の K-of-N 合意を回路内で強制。
//   - 共有/検証: drone_id と しきい値 k を公開入力、整合端末数を公開出力にし、
//     オンチェーン検証側は「同じドローンに K 台以上が整合した」ことだけを確認できる。
//
// 距離は cm 単位の整数。相対帯は割り算を避けて掛け算の比較に落とす:
//   d_claim >= d_meas / r  <=>  d_claim * R_NUM >= d_meas * R_DEN
//   d_claim <= d_meas * r  <=>  d_claim * R_DEN <= d_meas * R_NUM

global N: u32 = 3; // 集約する端末数
global R_NUM: u64 = 21; // r = 2.1  （±2σ 由来）
global R_DEN: u64 = 10;
global DIST_THRESH_CM: u64 = 3000; // 30 m 以内

fn is_consistent(d_claim: u64, d_meas: u64) -> bool {
    let within = d_claim <= DIST_THRESH_CM;
    let lower_ok = d_claim * R_NUM >= d_meas * R_DEN; // d_claim >= d_meas / r
    let upper_ok = d_claim * R_DEN <= d_meas * R_NUM; // d_claim <= d_meas * r
    within & lower_ok & upper_ok
}

fn main(
    drone_id: pub Field, // 公開: 対象ドローン
    k: pub u64, // 公開: 合意しきい値（K-of-N）
    drone_ids: [Field; N], // 非公開: 各端末が観測したドローンID
    d_claim: [u64; N], // 非公開: 放送位置からの幾何距離[cm]
    d_meas: [u64; N], // 非公開: RSSI からの推定距離[cm]
) -> pub u64 {
    // 集約: 各端末を同一ドローンに束縛しつつ、整合端末を数える
    let mut count: u64 = 0;
    for i in 0..N {
        assert(drone_ids[i] == drone_id); // 全端末が同じ放送を見ている
        if is_consistent(d_claim[i], d_meas[i]) {
            count += 1;
        }
    }
    assert(count >= k); // K-of-N 合意（満たさなければ証明生成が失敗）
    count // 公開出力: 整合端末数
}

// ── 単体テスト（nargo test で実行）──────────────────────────────────────────
#[test]
fn test_two_consistent_one_spoof() {
    // 端末0,1 は整合（d_claim≈d_meas, 30m以内）、端末2 は詐称（実測 50m 相当）
    let count = main(
        12345,
        2,
        [12345, 12345, 12345],
        [341, 360, 500],
        [341, 360, 5000],
    );
    assert(count == 2);
}

#[test(should_fail)]
fn test_consensus_not_met() {
    // k=3 を要求するが整合は2端末 → 合意未達で失敗するべき
    let _ = main(12345, 3, [12345, 12345, 12345], [341, 360, 500], [341, 360, 5000]);
}

#[test(should_fail)]
fn test_wrong_drone_binding() {
    // 端末2 が別ドローンを観測 → 同一放送への束縛違反で失敗するべき
    let _ = main(12345, 2, [12345, 12345, 99999], [341, 360, 341], [341, 360, 341]);
}
