pragma circom 2.1.9;

// Versioned leaf V2. Never use the legacy V1 VK with this circuit.

// circomlib の primitive を使う（EdDSA/Poseidon が Num2Bits/LessThan 等を持ち込むため、
// 同名テンプレートを自前定義する lib_uav_safety.circom は include しない）。
include "../node_modules/circomlib/circuits/bitify.circom";
include "../node_modules/circomlib/circuits/comparators.circom";
include "../node_modules/circomlib/circuits/poseidon.circom";
include "../node_modules/circomlib/circuits/eddsaposeidon.circom";

// AbsDiff is kept local because circomlib does not provide this helper.
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

template ObservationTimeCore(TIME_LIMIT_SEC) {
    signal input drone_time_sec;
    signal input target_time_sec;
    signal output time_ok;

    component dTime = AbsDiff(64);
    dTime.a <== drone_time_sec;
    dTime.b <== target_time_sec;

    component timeLeq = LessEqThan(64);
    timeLeq.in[0] <== dTime.out;
    timeLeq.in[1] <== TIME_LIMIT_SEC;
    time_ok <== timeLeq.out;
}

// ─────────────────────────────────────────────────────────────────────────────
// UavWitnessAttestationV2
//
// RSSI-based multi-observer aggregation用の1端末ぶんの証明回路。
//
// Observer署名を受けた測距値から、Remote ID申告位置との整合結果を算出する。
// 距離が大きく不整合であることは報告拒否条件ではなく、集約される判定結果である。
//
//   1. drone_id_commitment = Poseidon(domain, remote_id, session_salt, time_bucket)
//      session_saltはrunごとに共有する秘密salt。RIDを公開commitmentから
//      time bucketをまたいで照合されることを避けつつ、同じrun内の観測を結合する。
//      回路はsaltの乱数性を証明しないため、生成・配布は信頼境界として扱う。
//
//   2. device_pubkey (Ax, Ay) + EdDSA-Poseidon 署名検証
//      端末が「この主張(claim)」を自分の鍵で署名したことを回路内で検証する。
//      公開する pubkey により、チェーン側で「相異なる K 台」を判定でき（Sybil 対策）、
//      他人の proof を別の pubkey で使い回す replay を防ぐ。
//
// V2署名対象メッセージ:
//   M = Poseidon(domain, drone_id_commitment, target_commitment, observation_eligible,
//                freshness, measured_range_cm, calibration_profile_id, consistency_ok)
//   → 回路が計算したRSSI判定と、その判定に使う測距/profileを端末署名に束縛。
//
// Public outputs:
//   observation_eligible, target_commitment,
//   drone_id_commitment, device_pubkey_x, device_pubkey_y,
//   calibration_profile_id_pub (V2 allowlist input)
// ─────────────────────────────────────────────────────────────────────────────
template UavWitnessAttestationV2(
    LAT_CM_NUM,
    LON_CM_NUM,
    GEO_DEN,
    TIME_LIMIT_SEC,
    TIME_BUCKET_SEC,
    TOL_NUM,
    TOL_DEN
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

    // ── Private input: RSSI 実測レンジ（cm。中央値集約済みの値を回路外で算出）──
    signal input measured_range_cm;
    // Public profile id identifies the externally allowlisted RSSI calibration policy.
    signal input calibration_profile_id;

    // ── Private inputs: ドローン RemoteID ───────────────────────────────────
    // RemoteID(operator id / uas id) を体系的に 1 つの体上要素へ符号化した値。
    signal input remote_id;
    // 全observerへ安全に共有したrun固有32-byte keyからKDFした秘密field salt。
    // proofには公開せず、秘密性・高エントロピー・runごとの更新は運用要件。
    signal input session_salt;

    // ── Private input: observerが主張する観測時刻（M3・鮮度）───────────────
    // freshnessは観測対象時刻と一致させ、observer署名に束縛する。
    // proofは時計や受信自体の真実性を証明しない。EVMはtime_bucketを現在時刻と比較する。
    signal input freshness;

    // ── Private inputs: EdDSA 署名 ──────────────────────────────────────────
    // device_pubkey (Ax, Ay) は public にするが、S / R8 は private。
    signal input device_pubkey_ax;
    signal input device_pubkey_ay;
    signal input sig_s;
    signal input sig_r8x;
    signal input sig_r8y;

    // ── Public output: 判定対象として受理可能なRSSI観測 ────────────────────
    // 位置不整合そのものでは拒否せず、鮮度と正の測距値だけを受理条件にする。
    signal output observation_eligible;

    // ── Private commitment ───────────────────────────────────────────────────
    signal output target_commitment;

    // ── Public outputs: マルチ端末結合用 ─────────────────────────────────────
    signal output drone_id_commitment;
    signal output device_pubkey_x;
    signal output device_pubkey_y;

    // ── Public output: 時間バケット（チェーン側のグループ化キー）──────────────
    // target_time_sec を TIME_BUCKET_SEC 粒度に丸めた値。正確な時刻は隠したまま
    // 「同じ時間窓の同じドローン」でオンチェーン集計できるようにする。
    signal output time_bucket;

    // ── Public output: RSSI 整合（放送位置 vs 実測レンジの相対帯判定）──────────
    // 1=整合（放送は物理的に妥当）/ 0=矛盾（なりすまし疑い）。座標は秘匿のまま。
    signal output consistency_ok;

    // ── Public output: 新鮮さ（チェーン側で直近窓に入るか検査）────────────────
    signal output freshness_pub;
    // V2 public output; aggregator must require an explicitly allowlisted profile id.
    signal output calibration_profile_id_pub;

    // ── 鮮度と測距値だけで観測の受理可否を決める ───────────────────────────
    // 離れた申告位置はconsistency_ok=0として集約する。30m以内やカメラ検知を
    // 必須にすると、検出したい大きな位置不整合そのものを捨ててしまう。
    component observationTime = ObservationTimeCore(TIME_LIMIT_SEC);
    observationTime.drone_time_sec <== drone_time_sec;
    observationTime.target_time_sec <== target_time_sec;
    component rangeIsZero = IsZero();
    rangeIsZero.in <== measured_range_cm;
    observation_eligible <== observationTime.time_ok * (1 - rangeIsZero.out);

    // ── Poseidon コミットメント計算 ──────────────────────────────────────────
    component targetHash = Poseidon(4);
    targetHash.inputs[0] <== target_lat_e7_norm;
    targetHash.inputs[1] <== target_lon_e7_norm;
    targetHash.inputs[2] <== target_alt_cm;
    targetHash.inputs[3] <== target_time_sec;
    target_commitment <== targetHash.out;

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

    // ── run + time-bucket scoped RID commitment ──────────────────────────────
    // Public outputは異なるrun/時間窓間で同じRIDを安易に追跡させない。
    // session_saltのentropyは回路では保証できない。
    component droneIdHash = Poseidon(4);
    droneIdHash.inputs[0] <== 0x5349474e414c5f5249445f5632; // "SIGNAL_RID_V2"
    droneIdHash.inputs[1] <== remote_id;
    droneIdHash.inputs[2] <== session_salt;
    droneIdHash.inputs[3] <== time_bucket;
    drone_id_commitment <== droneIdHash.out;

    // Do not let the prover choose an unrelated freshness beacon. The bucket
    // is derived from target_time_sec above; the V2 registry applies a live
    // age/future-skew window to that bucket at submission time.
    component freshnessBits = Num2Bits(64);
    freshnessBits.in <== freshness;
    freshness === target_time_sec;

    // Prevent field-wrap aliases and oversized profile ids in V2 signed values.
    component measuredRangeBits = Num2Bits(32);
    measuredRangeBits.in <== measured_range_cm;
    component calibrationProfileBits = Num2Bits(32);
    calibrationProfileBits.in <== calibration_profile_id;

    // ── RSSI 整合判定（放送位置 vs 実測レンジの相対帯）────────────────────────
    // 放送位置(drone_*)と自端末(target_*)の二乗距離が、実測レンジ measured_range_cm の
    // 相対帯 [±(TOL_NUM/TOL_DEN)] に入るかを、平方根を避けて二乗＋DEN^2倍で判定する。
    component cLat = AbsDiff(32);
    component cLon = AbsDiff(32);
    component cAlt = AbsDiff(32);
    cLat.a <== drone_lat_e7_norm;  cLat.b <== target_lat_e7_norm;
    cLon.a <== drone_lon_e7_norm;  cLon.b <== target_lon_e7_norm;
    cAlt.a <== drone_alt_cm;       cAlt.b <== target_alt_cm;

    signal c_lat_scaled; signal c_lon_scaled; signal c_alt_scaled;
    c_lat_scaled <== cLat.out * LAT_CM_NUM;
    c_lon_scaled <== cLon.out * LON_CM_NUM;
    c_alt_scaled <== cAlt.out * GEO_DEN;

    signal c_lat_sq; signal c_lon_sq; signal c_alt_sq;
    c_lat_sq <== c_lat_scaled * c_lat_scaled;
    c_lon_sq <== c_lon_scaled * c_lon_scaled;
    c_alt_sq <== c_alt_scaled * c_alt_scaled;
    signal claimed_dist_sq;
    claimed_dist_sq <== c_lat_sq + c_lon_sq + c_alt_sq;

    var C_LOWER = TOL_DEN - TOL_NUM;
    var C_UPPER = TOL_DEN + TOL_NUM;

    signal c_base;
    c_base <== measured_range_cm * GEO_DEN;
    signal c_lower_num; signal c_upper_num;
    c_lower_num <== c_base * C_LOWER;
    c_upper_num <== c_base * C_UPPER;
    signal c_lower_sq; signal c_upper_sq;
    c_lower_sq <== c_lower_num * c_lower_num;
    c_upper_sq <== c_upper_num * c_upper_num;
    signal c_claimed_scaled;
    c_claimed_scaled <== claimed_dist_sq * (TOL_DEN * TOL_DEN);

    component cGeLower = LessEqThan(200);
    cGeLower.in[0] <== c_lower_sq;
    cGeLower.in[1] <== c_claimed_scaled;
    component cLeUpper = LessEqThan(200);
    cLeUpper.in[0] <== c_claimed_scaled;
    cLeUpper.in[1] <== c_upper_sq;
    consistency_ok <== cGeLower.out * cLeUpper.out;

    // ── V2署名対象: policy/session/測距/calibration/outcomeを1メッセージへ束縛 ──
    // domain = ASCII "OBS_LEAF_V2" encoded as a field constant.
    // consistency_ok is computed above from measured_range_cm by this same circuit.
    freshness_pub <== freshness;
    calibration_profile_id_pub <== calibration_profile_id;

    component msgHash = Poseidon(8);
    msgHash.inputs[0] <== 0x4f42535f4c4541465f5632;
    msgHash.inputs[1] <== drone_id_commitment;
    msgHash.inputs[2] <== target_commitment;
    msgHash.inputs[3] <== observation_eligible;
    msgHash.inputs[4] <== freshness;
    msgHash.inputs[5] <== measured_range_cm;
    msgHash.inputs[6] <== calibration_profile_id;
    msgHash.inputs[7] <== consistency_ok;

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

// The core keeps diagnostic and evidence commitments available internally, but
// only values required by the multi-observer statement cross the Groth16 public
// input boundary. This is deliberate data minimisation and shrinks the
// recursive verifier's public-input linear combination without weakening the
// constraints that derive these outputs.
template UavWitnessAttestationV2Public(
    LAT_CM_NUM,
    LON_CM_NUM,
    GEO_DEN,
    TIME_LIMIT_SEC,
    TIME_BUCKET_SEC,
    TOL_NUM,
    TOL_DEN
) {
    signal input drone_lat_e7_norm;
    signal input drone_lon_e7_norm;
    signal input drone_alt_cm;
    signal input drone_time_sec;
    signal input target_lat_e7_norm;
    signal input target_lon_e7_norm;
    signal input target_alt_cm;
    signal input target_time_sec;
    signal input measured_range_cm;
    signal input calibration_profile_id;
    signal input remote_id;
    signal input session_salt;
    signal input freshness;
    signal input device_pubkey_ax;
    signal input device_pubkey_ay;
    signal input sig_s;
    signal input sig_r8x;
    signal input sig_r8y;

    signal output observation_eligible;
    signal output drone_id_commitment;
    signal output device_pubkey_x;
    signal output device_pubkey_y;
    signal output time_bucket;
    signal output consistency_ok;
    signal output freshness_pub;
    signal output calibration_profile_id_pub;

    component core = UavWitnessAttestationV2(
        LAT_CM_NUM,
        LON_CM_NUM,
        GEO_DEN,
        TIME_LIMIT_SEC,
        TIME_BUCKET_SEC,
        TOL_NUM,
        TOL_DEN
    );

    core.drone_lat_e7_norm <== drone_lat_e7_norm;
    core.drone_lon_e7_norm <== drone_lon_e7_norm;
    core.drone_alt_cm <== drone_alt_cm;
    core.drone_time_sec <== drone_time_sec;
    core.target_lat_e7_norm <== target_lat_e7_norm;
    core.target_lon_e7_norm <== target_lon_e7_norm;
    core.target_alt_cm <== target_alt_cm;
    core.target_time_sec <== target_time_sec;
    core.measured_range_cm <== measured_range_cm;
    core.calibration_profile_id <== calibration_profile_id;
    core.remote_id <== remote_id;
    core.session_salt <== session_salt;
    core.freshness <== freshness;
    core.device_pubkey_ax <== device_pubkey_ax;
    core.device_pubkey_ay <== device_pubkey_ay;
    core.sig_s <== sig_s;
    core.sig_r8x <== sig_r8x;
    core.sig_r8y <== sig_r8y;

    observation_eligible <== core.observation_eligible;
    drone_id_commitment <== core.drone_id_commitment;
    device_pubkey_x <== core.device_pubkey_x;
    device_pubkey_y <== core.device_pubkey_y;
    time_bucket <== core.time_bucket;
    consistency_ok <== core.consistency_ok;
    freshness_pub <== core.freshness_pub;
    calibration_profile_id_pub <== core.calibration_profile_id_pub;
}

component main = UavWitnessAttestationV2Public(
    11132000,   // LAT_CM_NUM:  緯度 1度 ≈ 111.32 km → cm
    9128800,    // LON_CM_NUM:  経度 1度 ≈ 91.288 km → cm（北緯 35° 近辺）
    10000000,   // GEO_DEN:     E7 スケールの分母
    5,          // TIME_LIMIT_SEC:     5 秒
    60,         // TIME_BUCKET_SEC: 時間窓 60 秒
    90,         // TOL_NUM  ┐ RSSI 整合の相対許容 90/100 = ±90%（実機較正後に更新）
    100         // TOL_DEN  ┘
);
