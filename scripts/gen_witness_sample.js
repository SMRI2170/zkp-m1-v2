#!/usr/bin/env node
/*
 * uav_witness_attestation.circom 用のサンプル入力生成。
 *
 * 回路内で検証する EdDSA-Poseidon 署名は手で作れないため、circomlibjs で
 *   M = Poseidon(drone_id_commitment, target_commitment, frame_binding, within30_and_detected)
 * を回路と同じ順序で計算し、端末鍵で署名した完全な入力 JSON を出力する。
 *
 * 同一ドローン(remote_id)・同一観測を共有し、端末鍵だけ異なる N 台ぶんを生成する。
 * 出力:
 *   zk-distance/samples/witness/input_dev{0..N-1}.json  … 各端末の回路入力
 *   zk-distance/samples/sample_multi_witness.json       … N 台ぶんの配列（参照用）
 *   zk-distance/samples/sample_witness_attestation.json … dev0（ビルドスクリプトの既定入力）
 */
const fs = require("fs");
const path = require("path");
const { buildPoseidon, buildEddsa } = require("circomlibjs");

// ── 観測値（distance_30m_time_detection_commitment のサンプルと同一。within30+detected=1）──
const base = {
  drone_lat_e7_norm: 1256891390n,
  drone_lon_e7_norm: 3196917000n,
  drone_alt_cm: 1200n,
  drone_time_sec: 1711447200n,
  target_lat_e7_norm: 1256891590n,
  target_lon_e7_norm: 3196917180n,
  target_alt_cm: 1000n,
  target_time_sec: 1711447203n,
  uav_detected: 1n,
  detection_score_bps: 8300n,
  detection_class_id: 1n,
  frame_time_sec: 1711447202n,
  frame_commitment_hi: 123456789n,
  frame_commitment_lo: 987654321n,
  remote_id: 424242424242n, // 同一ドローンの RemoteID
};

const TIME_BUCKET_SEC = 60n;
const WITHIN30_AND_DETECTED = 1n; // 上記観測は 30m/5s 以内かつ検知 → 1

// 端末秘密鍵（デモ用固定 32byte）。distinct な pubkey を生む。
const DEVICE_PRIV_HEX = [
  "01".repeat(32),
  "02".repeat(32),
  "03".repeat(32),
];

// 各端末の RSSI 実測レンジ[cm]（中央値集約済み想定）。
// 放送位置(drone) と自端末(target) の実距離は約 3.4m ≈ 341cm。
// dev0/dev1 は整合(≈341cm)、dev2 は矛盾(5000cm=放送は近いと言うが実測は遠い)。
const MEASURED_RANGE_CM = ["341", "360", "5000"];

async function main() {
  const poseidon = await buildPoseidon();
  const eddsa = await buildEddsa();
  const F = poseidon.F;
  const o = (x) => F.toObject(x); // field element -> bigint

  const droneId = o(poseidon([base.remote_id]));
  const targetCommit = o(
    poseidon([
      base.target_lat_e7_norm,
      base.target_lon_e7_norm,
      base.target_alt_cm,
      base.target_time_sec,
    ])
  );
  const frameBinding = o(poseidon([base.frame_commitment_hi, base.frame_commitment_lo]));
  // 新鮮さビーコン（直近ブロックハッシュ等の想定。デモ用固定値）
  const FRESHNESS = 987654321987654321n;
  const M = o(poseidon([droneId, targetCommit, frameBinding, WITHIN30_AND_DETECTED, FRESHNESS]));

  // ── ドローン署名 RemoteID（M3）: オペレータ鍵で放送内容に署名 ─────────────
  // 3端末は同一ドローンの同一放送を受けるので、署名は全端末で共通。
  const DRONE_PRIV = Buffer.from("0a".repeat(32), "hex");
  const dronePub = eddsa.prv2pub(DRONE_PRIV);
  const droneMsg = o(
    poseidon([
      base.remote_id,
      base.drone_lat_e7_norm,
      base.drone_lon_e7_norm,
      base.drone_alt_cm,
      base.drone_time_sec,
    ])
  );
  const droneSig = eddsa.signPoseidon(DRONE_PRIV, F.e(droneMsg));

  const outDir = path.join(__dirname, "..", "zk-distance", "samples");
  const witnessDir = path.join(outDir, "witness");
  fs.mkdirSync(witnessDir, { recursive: true });

  const all = [];
  for (let i = 0; i < DEVICE_PRIV_HEX.length; i++) {
    const prv = Buffer.from(DEVICE_PRIV_HEX[i], "hex");
    const pub = eddsa.prv2pub(prv);
    const sig = eddsa.signPoseidon(prv, F.e(M));

    const input = {};
    for (const [k, v] of Object.entries(base)) input[k] = v.toString();
    input.measured_range_cm = MEASURED_RANGE_CM[i] ?? "341";
    input.device_pubkey_ax = o(pub[0]).toString();
    input.device_pubkey_ay = o(pub[1]).toString();
    input.sig_s = sig.S.toString();
    input.sig_r8x = o(sig.R8[0]).toString();
    input.sig_r8y = o(sig.R8[1]).toString();

    // ドローン署名 RemoteID（M3・全端末共通）
    input.drone_auth_enabled = "1";
    input.drone_pubkey_ax = o(dronePub[0]).toString();
    input.drone_pubkey_ay = o(dronePub[1]).toString();
    input.drone_sig_s = droneSig.S.toString();
    input.drone_sig_r8x = o(droneSig.R8[0]).toString();
    input.drone_sig_r8y = o(droneSig.R8[1]).toString();

    // 新鮮さ（device 署名 M に含まれる。リプレイ対策）
    input.freshness = FRESHNESS.toString();

    fs.writeFileSync(
      path.join(witnessDir, `input_dev${i}.json`),
      JSON.stringify(input, null, 2)
    );
    all.push(input);
  }

  fs.writeFileSync(path.join(outDir, "sample_multi_witness.json"), JSON.stringify(all, null, 2));
  fs.writeFileSync(
    path.join(outDir, "sample_witness_attestation.json"),
    JSON.stringify(all[0], null, 2)
  );

  console.log("drone_id_commitment =", droneId.toString());
  console.log("target_commitment   =", targetCommit.toString());
  console.log("frame_binding       =", frameBinding.toString());
  console.log("M (signed message)  =", M.toString());
  console.log("time_bucket         =", (base.target_time_sec / TIME_BUCKET_SEC).toString());
  console.log(`\nWrote ${all.length} device inputs to ${witnessDir}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
