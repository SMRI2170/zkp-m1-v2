#!/usr/bin/env node
/*
 * Security audit for the legacy V1 observer signature.
 *
 * V1 signs RID, target, frame, detection and freshness, but not measured_range_cm
 * or the resulting consistency_ok. This script verifies the existing sample
 * signature and writes a witness with only its private RSSI range changed.
 *
 * Usage:
 *   node scripts/audit_leaf_signature_v1_rebinding.js [input.json] [output.json]
 * Default input: synthetic observer 2 (5000 cm). Default output: OS temp dir.
 */
const fs = require("fs");
const os = require("os");
const path = require("path");
const { buildPoseidon, buildEddsa } = require("circomlibjs");

const root = path.join(__dirname, "..");
const inputPath = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(root, "zk-distance", "samples", "witness", "input_dev2.json");
const outputPath = process.argv[3]
  ? path.resolve(process.argv[3])
  : path.join(os.tmpdir(), `leaf-v1-rebind-${process.pid}.json`);
const replacementRangeCm = 341n;

function asBigInt(value, name) {
  try {
    return BigInt(value);
  } catch {
    throw new Error(`invalid ${name}: ${value}`);
  }
}

function consistencyForRangeCm(input, rangeCm) {
  const LAT_CM_NUM = 11132000n;
  const LON_CM_NUM = 9128800n;
  const GEO_DEN = 10000000n;
  const TOL_NUM = 90n;
  const TOL_DEN = 100n;
  const abs = (a, b) => (a >= b ? a - b : b - a);

  const lat = abs(asBigInt(input.drone_lat_e7_norm, "drone latitude"), asBigInt(input.target_lat_e7_norm, "target latitude")) * LAT_CM_NUM;
  const lon = abs(asBigInt(input.drone_lon_e7_norm, "drone longitude"), asBigInt(input.target_lon_e7_norm, "target longitude")) * LON_CM_NUM;
  const alt = abs(asBigInt(input.drone_alt_cm, "drone altitude"), asBigInt(input.target_alt_cm, "target altitude")) * GEO_DEN;
  const claimedDistanceSq = lat * lat + lon * lon + alt * alt;
  const base = rangeCm * GEO_DEN;
  const lower = (base * (TOL_DEN - TOL_NUM)) ** 2n;
  const upper = (base * (TOL_DEN + TOL_NUM)) ** 2n;
  const scaledClaim = claimedDistanceSq * TOL_DEN * TOL_DEN;
  return lower <= scaledClaim && scaledClaim <= upper ? 1n : 0n;
}

async function main() {
  const input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
  const poseidon = await buildPoseidon();
  const eddsa = await buildEddsa();
  const F = poseidon.F;
  const fieldBigInt = (value) => F.toObject(value);

  const droneIdCommitment = fieldBigInt(poseidon([asBigInt(input.remote_id, "remote_id")]));
  const targetCommitment = fieldBigInt(poseidon([
    asBigInt(input.target_lat_e7_norm, "target latitude"),
    asBigInt(input.target_lon_e7_norm, "target longitude"),
    asBigInt(input.target_alt_cm, "target altitude"),
    asBigInt(input.target_time_sec, "target time"),
  ]));
  const frameBinding = fieldBigInt(poseidon([
    asBigInt(input.frame_commitment_hi, "frame commitment hi"),
    asBigInt(input.frame_commitment_lo, "frame commitment lo"),
  ]));
  const freshness = asBigInt(input.freshness, "freshness");
  const signedMessage = poseidon([
    droneIdCommitment,
    targetCommitment,
    frameBinding,
    1n, // within30_and_detected in the synthetic fixture
    freshness,
  ]);
  const signature = {
    R8: [F.e(input.sig_r8x), F.e(input.sig_r8y)],
    S: asBigInt(input.sig_s, "signature S"),
  };
  const publicKey = [F.e(input.device_pubkey_ax), F.e(input.device_pubkey_ay)];
  if (!eddsa.verifyPoseidon(signedMessage, signature, publicKey)) {
    throw new Error("fixture observer signature did not verify");
  }

  const originalRange = asBigInt(input.measured_range_cm, "measured range");
  const originalOutcome = consistencyForRangeCm(input, originalRange);
  const replacementOutcome = consistencyForRangeCm(input, replacementRangeCm);
  if (originalOutcome === replacementOutcome) {
    throw new Error("chosen range change did not change the RSSI consistency result");
  }

  const reboundWitness = { ...input, measured_range_cm: replacementRangeCm.toString() };
  fs.writeFileSync(outputPath, `${JSON.stringify(reboundWitness, null, 2)}\n`);
  console.log("V1 observer signature verifies: yes");
  console.log(`same signed message: ${fieldBigInt(signedMessage)}`);
  console.log(`original range ${originalRange} cm => consistency_ok=${originalOutcome}`);
  console.log(`changed range  ${replacementRangeCm} cm => consistency_ok=${replacementOutcome}`);
  console.log(`wrote changed witness: ${outputPath}`);
  console.log("This audit demonstrates the signature-binding gap; it does not assert sensor truth.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
