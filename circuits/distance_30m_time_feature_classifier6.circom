pragma circom 2.1.9;

include "lib_uav_safety.circom";

// 6次元の音響特徴を扱う線形分類器付き距離証明。
// 学習(scripts/acoustic/train_linear.py)で得た正/負分離の重み WP/WN と
// 非負オフセット ADD_POS/ADD_NEG を回路パラメータとして受け取る。
//
// 判定: neg + ADD_NEG <= pos + ADD_POS
//   pos = sum(WP[i] * features[i]),  neg = sum(WN[i] * features[i])
// すべて非負なので LessEqThan で安全に比較できる(負の重みを符号分離で吸収)。
//
// 特徴 features[i] は features.py 出力(0..1)を ×S_X(=1000) した整数で渡す。
template Distance30mTimeFeatureClassifier6(
    LAT_CM_NUM,
    LON_CM_NUM,
    GEO_DEN,
    DISTANCE_LIMIT_CM,
    TIME_LIMIT_SEC,
    N_FEATURES,
    WP,
    WN,
    ADD_POS,
    ADD_NEG
) {
    signal input drone_lat_e7_norm;
    signal input drone_lon_e7_norm;
    signal input drone_alt_cm;
    signal input drone_time_sec;

    signal input target_lat_e7_norm;
    signal input target_lon_e7_norm;
    signal input target_alt_cm;
    signal input target_time_sec;

    signal input frame_time_sec;
    signal input features[N_FEATURES];

    signal output within30;
    signal output distance_ok;
    signal output time_ok;
    signal output frame_time_ok;
    signal output pos;
    signal output neg;
    signal output model_ok;
    signal output within30_and_model;

    component base = Distance30mTimeCore(
        LAT_CM_NUM,
        LON_CM_NUM,
        GEO_DEN,
        DISTANCE_LIMIT_CM,
        TIME_LIMIT_SEC
    );

    base.drone_lat_e7_norm <== drone_lat_e7_norm;
    base.drone_lon_e7_norm <== drone_lon_e7_norm;
    base.drone_alt_cm <== drone_alt_cm;
    base.drone_time_sec <== drone_time_sec;
    base.target_lat_e7_norm <== target_lat_e7_norm;
    base.target_lon_e7_norm <== target_lon_e7_norm;
    base.target_alt_cm <== target_alt_cm;
    base.target_time_sec <== target_time_sec;

    // 動画/音声フレーム時刻が利用者時刻に近いか
    component frameTimeDiff = AbsDiff(64);
    frameTimeDiff.a <== frame_time_sec;
    frameTimeDiff.b <== target_time_sec;

    component frameTimeLeq = LessEqThan(64);
    frameTimeLeq.in[0] <== frameTimeDiff.out;
    frameTimeLeq.in[1] <== TIME_LIMIT_SEC;

    // 正/負の重みをそれぞれ非負で内積累積
    signal pos_acc[N_FEATURES + 1];
    signal neg_acc[N_FEATURES + 1];
    pos_acc[0] <== 0;
    neg_acc[0] <== 0;
    for (var i = 0; i < N_FEATURES; i++) {
        pos_acc[i + 1] <== pos_acc[i] + WP[i] * features[i];
        neg_acc[i + 1] <== neg_acc[i] + WN[i] * features[i];
    }

    pos <== pos_acc[N_FEATURES] + ADD_POS;
    neg <== neg_acc[N_FEATURES] + ADD_NEG;

    // neg <= pos  ⟺  w·x + b >= 0
    component modelLeq = LessEqThan(32);
    modelLeq.in[0] <== neg;
    modelLeq.in[1] <== pos;

    within30 <== base.within30;
    distance_ok <== base.distance_ok;
    time_ok <== base.time_ok;
    frame_time_ok <== frameTimeLeq.out;
    model_ok <== modelLeq.out * frame_time_ok;
    within30_and_model <== within30 * model_ok;
}

// 末尾の WP / WN / ADD_POS / ADD_NEG は train_linear.py の出力で置換する。
component main = Distance30mTimeFeatureClassifier6(
    11132000,
    9128800,
    10000000,
    3000,
    5,
    6,
    [0, 0, 771, 4790, 0, 0],
    [3771, 3031, 0, 0, 5913, 168],
    0,
    2024495
);
