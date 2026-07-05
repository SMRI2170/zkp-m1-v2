pragma circom 2.1.9;

// circomlib の primitive を使う（EdDSA/Poseidon が Num2Bits/LessThan 等を持ち込むため、
// 同名テンプレートを自前定義する lib_uav_safety.circom は include しない）。
include "../node_modules/circomlib/circuits/bitify.circom";
include "../node_modules/circomlib/circuits/comparators.circom";
include "../node_modules/circomlib/circuits/poseidon.circom";
include "../node_modules/circomlib/circuits/eddsaposeidon.circom";

// ─────────────────────────────────────────────────────────────────────────────
// AbsDiff / Distance30mTimeCore
//
// lib_uav_safety.circom の同名テンプレートを circomlib primitive 上へ移植したもの。
// （AbsDiff は circomlib に無いためここで定義。ロジックと定数は本家と一致させている）
// ─────────────────────────────────────────────────────────────────────────────
template AbsDiff(n) {
    signal input a;
    signal input b;
    signal output out;
    signal left_term;
    signal right_term;

    component aLtB = LessThan(n);
    component bLtA = LessThan(n);

    aLtB.in[0] <== a;
    aLtB.in[1] <== b;
    bLtA.in[0] <== b;
    bLtA.in[1] <== a;

    left_term <== (b - a) * aLtB.out;
    right_term <== (a - b) * bLtA.out;
    out <== left_term + right_term;
}

template Distance30mTimeCore(
    LAT_CM_NUM,
    LON_CM_NUM,
    GEO_DEN,
    DISTANCE_LIMIT_CM,
    TIME_LIMIT_SEC
) {
    signal input drone_lat_e7_norm;
    signal input drone_lon_e7_norm;
    signal input drone_alt_cm;
    signal input drone_time_sec;

    signal input target_lat_e7_norm;
    signal input target_lon_e7_norm;
    signal input target_alt_cm;
    signal input target_time_sec;

    signal output within30;
    signal output distance_ok;
    signal output time_ok;

    component dLat = AbsDiff(32);
    component dLon = AbsDiff(32);
    component dAlt = AbsDiff(32);
    component dTime = AbsDiff(64);

    dLat.a <== drone_lat_e7_norm;
    dLat.b <== target_lat_e7_norm;
    dLon.a <== drone_lon_e7_norm;
    dLon.b <== target_lon_e7_norm;
    dAlt.a <== drone_alt_cm;
    dAlt.b <== target_alt_cm;
    dTime.a <== drone_time_sec;
    dTime.b <== target_time_sec;

    signal lat_scaled;
    signal lon_scaled;
    signal alt_scaled;
    signal distance_scaled_sq;
    signal max_distance_scaled_sq;
    signal lat_sq;
    signal lon_sq;
    signal alt_sq;

    lat_scaled <== dLat.out * LAT_CM_NUM;
    lon_scaled <== dLon.out * LON_CM_NUM;
    alt_scaled <== dAlt.out * GEO_DEN;

    lat_sq <== lat_scaled * lat_scaled;
    lon_sq <== lon_scaled * lon_scaled;
    alt_sq <== alt_scaled * alt_scaled;
    distance_scaled_sq <== lat_sq + lon_sq + alt_sq;
    max_distance_scaled_sq <== (DISTANCE_LIMIT_CM * GEO_DEN) * (DISTANCE_LIMIT_CM * GEO_DEN);

    component distanceLeq = LessEqThan(128);
    distanceLeq.in[0] <== distance_scaled_sq;
    distanceLeq.in[1] <== max_distance_scaled_sq;
    distance_ok <== distanceLeq.out;

    component timeLeq = LessEqThan(64);
    timeLeq.in[0] <== dTime.out;
    timeLeq.in[1] <== TIME_LIMIT_SEC;
    time_ok <== timeLeq.out;

    within30 <== distance_ok * time_ok;
}

// ─────────────────────────────────────────────────────────────────────────────
// UavWitnessAttestation
//
// マルチ端末合意（ブロックチェーン結合）用の 1 端末ぶんの証明回路。
//
// distance_30m_time_detection_commitment.circom（距離+時刻+映像検知+Poseidon
// コミットメント）を土台に、次の 2 つをオンチェーン結合のために追加する。
//
//   1. drone_id_commitment = Poseidon(remote_id)
//      各端末が受信するドローンの RemoteID(operator/uas id) は共通なので、
//      同じドローンを見た端末どうしでこの値が一致する。チェーン上の結合キー。
//
//   2. device_pubkey (Ax, Ay) + EdDSA-Poseidon 署名検証
//      端末が「この主張(claim)」を自分の鍵で署名したことを回路内で検証する。
//      公開する pubkey により、チェーン側で「相異なる K 台」を判定でき（Sybil 対策）、
//      他人の proof を別の pubkey で使い回す replay を防ぐ。
//
// 署名対象メッセージ:
//   M = Poseidon(drone_id_commitment, target_commitment, frame_binding,
//                within30_and_detected)
//   → その端末が「どのドローンを・どの観測点で・どのフレームで・接近検知したか」を束縛。
//
// Public outputs:
//   within30, distance_ok, time_ok,
//   detection_ok, frame_time_ok, detection_bundle_ok, within30_and_detected,
//   drone_commitment, target_commitment, frame_binding,
//   drone_id_commitment, device_pubkey_x, device_pubkey_y
// ─────────────────────────────────────────────────────────────────────────────
template UavWitnessAttestation(
    LAT_CM_NUM,
    LON_CM_NUM,
    GEO_DEN,
    DISTANCE_LIMIT_CM,
    TIME_LIMIT_SEC,
    DETECTION_MIN_SCORE_BPS,
    UAV_CLASS_ID,
    TIME_BUCKET_SEC
) {
    // ── Private inputs: ドローン側ログ ──────────────────────────────────────
    signal input drone_lat_e7_norm;
    signal input drone_lon_e7_norm;
    signal input drone_alt_cm;
    signal input drone_time_sec;

    // ── Private inputs: 利用者側ログ ────────────────────────────────────────
    signal input target_lat_e7_norm;
    signal input target_lon_e7_norm;
    signal input target_alt_cm;
    signal input target_time_sec;

    // ── Private inputs: 動画検知ログ ────────────────────────────────────────
    signal input uav_detected;
    signal input detection_score_bps;
    signal input detection_class_id;
    signal input frame_time_sec;
    signal input frame_commitment_hi;
    signal input frame_commitment_lo;

    // ── Private inputs: ドローン RemoteID ───────────────────────────────────
    // RemoteID(operator id / uas id) を体系的に 1 つの体上要素へ符号化した値。
    signal input remote_id;

    // ── Private inputs: EdDSA 署名 ──────────────────────────────────────────
    // device_pubkey (Ax, Ay) は public にするが、S / R8 は private。
    signal input device_pubkey_ax;
    signal input device_pubkey_ay;
    signal input sig_s;
    signal input sig_r8x;
    signal input sig_r8y;

    // ── Public outputs: 距離・時刻判定 ──────────────────────────────────────
    signal output within30;
    signal output distance_ok;
    signal output time_ok;

    // ── Public outputs: 検知判定 ─────────────────────────────────────────────
    signal output detection_ok;
    signal output frame_time_ok;
    signal output detection_bundle_ok;
    signal output within30_and_detected;

    // ── Public outputs: Poseidon コミットメント ──────────────────────────────
    signal output drone_commitment;
    signal output target_commitment;
    signal output frame_binding;

    // ── Public outputs: マルチ端末結合用 ─────────────────────────────────────
    signal output drone_id_commitment;
    signal output device_pubkey_x;
    signal output device_pubkey_y;

    // ── Public output: 時間バケット（チェーン側のグループ化キー）──────────────
    // target_time_sec を TIME_BUCKET_SEC 粒度に丸めた値。正確な時刻は隠したまま
    // 「同じ時間窓の同じドローン」でオンチェーン集計できるようにする。
    signal output time_bucket;

    // ── 内部 signal ──────────────────────────────────────────────────────────
    signal detection_time_gate;

    // ── 距離・時刻コア判定 ───────────────────────────────────────────────────
    component base = Distance30mTimeCore(
        LAT_CM_NUM,
        LON_CM_NUM,
        GEO_DEN,
        DISTANCE_LIMIT_CM,
        TIME_LIMIT_SEC
    );

    base.drone_lat_e7_norm  <== drone_lat_e7_norm;
    base.drone_lon_e7_norm  <== drone_lon_e7_norm;
    base.drone_alt_cm       <== drone_alt_cm;
    base.drone_time_sec     <== drone_time_sec;
    base.target_lat_e7_norm <== target_lat_e7_norm;
    base.target_lon_e7_norm <== target_lon_e7_norm;
    base.target_alt_cm      <== target_alt_cm;
    base.target_time_sec    <== target_time_sec;

    within30    <== base.within30;
    distance_ok <== base.distance_ok;
    time_ok     <== base.time_ok;

    // ── 検知スコア・クラス検証 ───────────────────────────────────────────────
    uav_detected * (uav_detected - 1) === 0;

    component scoreMinLeq = LessEqThan(16);
    scoreMinLeq.in[0] <== DETECTION_MIN_SCORE_BPS;
    scoreMinLeq.in[1] <== detection_score_bps;

    component classEq = IsEqual();
    classEq.in[0] <== detection_class_id;
    classEq.in[1] <== UAV_CLASS_ID;

    signal detection_gate;
    detection_gate <== uav_detected * scoreMinLeq.out;
    detection_ok   <== detection_gate * classEq.out;

    // ── フレーム時刻検証 ─────────────────────────────────────────────────────
    component frameTimeDiff = AbsDiff(64);
    frameTimeDiff.a <== frame_time_sec;
    frameTimeDiff.b <== target_time_sec;

    component frameTimeLeq = LessEqThan(64);
    frameTimeLeq.in[0] <== frameTimeDiff.out;
    frameTimeLeq.in[1] <== TIME_LIMIT_SEC;

    frame_time_ok <== frameTimeLeq.out;

    // ── 検知バンドル判定 ─────────────────────────────────────────────────────
    detection_time_gate  <== detection_ok * frame_time_ok;
    detection_bundle_ok  <== detection_time_gate;
    within30_and_detected <== within30 * detection_bundle_ok;

    // ── Poseidon コミットメント計算 ──────────────────────────────────────────
    component droneHash = Poseidon(4);
    droneHash.inputs[0] <== drone_lat_e7_norm;
    droneHash.inputs[1] <== drone_lon_e7_norm;
    droneHash.inputs[2] <== drone_alt_cm;
    droneHash.inputs[3] <== drone_time_sec;
    drone_commitment <== droneHash.out;

    component targetHash = Poseidon(4);
    targetHash.inputs[0] <== target_lat_e7_norm;
    targetHash.inputs[1] <== target_lon_e7_norm;
    targetHash.inputs[2] <== target_alt_cm;
    targetHash.inputs[3] <== target_time_sec;
    target_commitment <== targetHash.out;

    component frameHash = Poseidon(2);
    frameHash.inputs[0] <== frame_commitment_hi;
    frameHash.inputs[1] <== frame_commitment_lo;
    frame_binding <== frameHash.out;

    // ── ドローン ID コミットメント（同一ドローン結合キー）──────────────────────
    component droneIdHash = Poseidon(1);
    droneIdHash.inputs[0] <== remote_id;
    drone_id_commitment <== droneIdHash.out;

    // ── 端末鍵を公開 ─────────────────────────────────────────────────────────
    device_pubkey_x <== device_pubkey_ax;
    device_pubkey_y <== device_pubkey_ay;

    // ── 時間バケットの計算（time_bucket = target_time_sec \ TIME_BUCKET_SEC）────
    // 商と剰余を witness で与え、回路内で正しさを強制する:
    //   target_time_sec === time_bucket * TIME_BUCKET_SEC + time_rem,  0 <= time_rem < TIME_BUCKET_SEC
    signal time_rem;
    time_bucket <-- target_time_sec \ TIME_BUCKET_SEC;
    time_rem    <-- target_time_sec % TIME_BUCKET_SEC;
    target_time_sec === time_bucket * TIME_BUCKET_SEC + time_rem;

    // 剰余が [0, TIME_BUCKET_SEC) に収まることを検証
    component remLt = LessThan(32);
    remLt.in[0] <== time_rem;
    remLt.in[1] <== TIME_BUCKET_SEC;
    remLt.out === 1;

    // 商が 32bit 内であることを検証（体上での巻き戻り偽装を防ぐ）
    component bucketBits = Num2Bits(32);
    bucketBits.in <== time_bucket;

    // ── 署名対象メッセージ M の計算 ──────────────────────────────────────────
    // 端末が「このドローン・この観測・このフレーム・接近検知の成否」を束縛して署名した値。
    component msgHash = Poseidon(4);
    msgHash.inputs[0] <== drone_id_commitment;
    msgHash.inputs[1] <== target_commitment;
    msgHash.inputs[2] <== frame_binding;
    msgHash.inputs[3] <== within30_and_detected;

    // ── EdDSA-Poseidon 署名検証 ──────────────────────────────────────────────
    component sigVerify = EdDSAPoseidonVerifier();
    sigVerify.enabled <== 1;
    sigVerify.Ax  <== device_pubkey_ax;
    sigVerify.Ay  <== device_pubkey_ay;
    sigVerify.S   <== sig_s;
    sigVerify.R8x <== sig_r8x;
    sigVerify.R8y <== sig_r8y;
    sigVerify.M   <== msgHash.out;
}

component main = UavWitnessAttestation(
    11132000,   // LAT_CM_NUM:  緯度 1度 ≈ 111.32 km → cm
    9128800,    // LON_CM_NUM:  経度 1度 ≈ 91.288 km → cm（北緯 35° 近辺）
    10000000,   // GEO_DEN:     E7 スケールの分母
    3000,       // DISTANCE_LIMIT_CM: 30 m
    5,          // TIME_LIMIT_SEC:     5 秒
    7000,       // DETECTION_MIN_SCORE_BPS: 70.00% (basis points)
    1,          // UAV_CLASS_ID
    60          // TIME_BUCKET_SEC: 時間窓 60 秒
);
