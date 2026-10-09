#!/usr/bin/env node
/*
 * Generate synthetic inputs for uav_witness_attestation_v2.circom.
 * Fixed observer secrets are test-only fixtures.
 *
 * Usage: node scripts/gen_witness_sample_v2.js [output-directory]
 */
const fs = require("fs");
const crypto = require("crypto");
const os = require("os");
const path = require("path");
const { buildPoseidon, buildEddsa } = require("circomlibjs");

const root = path.join(__dirname, "..");
const inputDir = path.join(root, "zk-distance", "samples", "witness");
const outputDir = process.argv[2]
  ? path.resolve(process.argv[2])
  : fs.mkdtempSync(path.join(os.tmpdir(), "uav-witness-v2-samples-"));
const DEVICE_PRIV_HEX = ["01", "02", "03"].map((byte) => byte.repeat(32));
const TEST_ONLY_RUN_KEY = Buffer.from("0123456789abcdef0123456789abcdef", "ascii");
const CALIBRATION_PROFILE_ID = BigInt(process.env.UAV_V2_PROFILE_ID || "1"); // synthetic profile; production policy must allowlist it
const TIME_OFFSET_SEC = BigInt(process.env.UAV_V2_TIME_OFFSET_SEC || "0");
const RUN_ID = process.env.UAV_V2_RUN_ID || "synthetic-run-01";
const DEVICE_INDEX = process.env.UAV_V2_DEVICE_INDEX === undefined
  ? null
  : Number(process.env.UAV_V2_DEVICE_INDEX);
const SCENARIO = process.env.UAV_V2_SCENARIO || "baseline";
const DOMAIN_V2 = 0x4f42535f4c4541465f5632n; // ASCII "OBS_LEAF_V2"
const DOMAIN_RID_V2 = 0x5349474e414c5f5249445f5632n; // ASCII "SIGNAL_RID_V2"
const TIME_BUCKET_SEC = 60n;

function readRunKey() {
  const keyPath = process.env.UAV_V2_SESSION_KEY_FILE;
  if (!keyPath) return TEST_ONLY_RUN_KEY;

  const nofollow = fs.constants.O_NOFOLLOW;
  if (nofollow === undefined) throw new Error("platform cannot safely reject symlinked session-key files");
  let fd;
  try {
    fd = fs.openSync(path.resolve(keyPath), fs.constants.O_RDONLY | nofollow);
  } catch {
    throw new Error("session-key file cannot be safely opened");
  }
  try {
    const info = fs.fstatSync(fd);
    const permissions = info.mode & 0o777;
    if (!info.isFile() || (permissions & ~0o600) !== 0 || (permissions & 0o400) === 0) {
      throw new Error("session-key file must be regular, owner-readable, and no broader than mode 0600");
    }
    if (typeof process.getuid === "function" && info.uid !== process.getuid()) {
      throw new Error("session-key file must be owned by the current user");
    }
    const key = fs.readFileSync(fd);
    if (key.length !== 32) throw new Error("session-key file must contain exactly 32 raw bytes");
    return key;
  } finally {
    fs.closeSync(fd);
  }
}

function sessionSaltForRun(runKey) {
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(RUN_ID)) {
    throw new Error("UAV_V2_RUN_ID must be an opaque 1..64 character ASCII identifier");
  }
  const message = Buffer.from(`signal.observer-circuit-salt.v2\0${RUN_ID}`, "utf8");
  const saltBytes = crypto.createHmac("sha256", runKey).update(message).digest().subarray(0, 31);
  const salt = BigInt(`0x${saltBytes.toString("hex")}`);
  if (salt === 0n) throw new Error("derived session salt must not be zero");
  return salt;
}

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
  const poseidon = await buildPoseidon();
  const eddsa = await buildEddsa();
  const F = poseidon.F;
  const fieldBigInt = (value) => F.toObject(value);
  const sessionSalt = sessionSaltForRun(readRunKey());
  if (CALIBRATION_PROFILE_ID < 0n || CALIBRATION_PROFILE_ID > 0xffffffffn) {
    throw new Error("UAV_V2_PROFILE_ID must fit uint32");
  }
  if (DEVICE_INDEX !== null && (!Number.isInteger(DEVICE_INDEX) || DEVICE_INDEX < 0 || DEVICE_INDEX >= DEVICE_PRIV_HEX.length)) {
    throw new Error("UAV_V2_DEVICE_INDEX must be 0, 1, or 2");
  }
  fs.mkdirSync(outputDir, { recursive: true });

  for (let i = 0; i < DEVICE_PRIV_HEX.length; i++) {
    if (DEVICE_INDEX !== null && i !== DEVICE_INDEX) continue;
    const inputPath = path.join(inputDir, `input_dev${i}.json`);
    const input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
    // The checked-in seed witnesses retain V1-era video/frame fields. V2 is
    // BLE/RSSI-only; remove those obsolete fields instead of inventing values.
    for (const field of [
      "uav_detected", "detection_score_bps", "detection_class_id", "frame_time_sec",
      "frame_commitment_hi", "frame_commitment_lo", "drone_auth_enabled",
      "drone_pubkey_ax", "drone_pubkey_ay", "drone_sig_s", "drone_sig_r8x", "drone_sig_r8y",
    ]) {
      delete input[field];
    }
    if (TIME_OFFSET_SEC !== 0n) {
      for (const field of ["drone_time_sec", "target_time_sec"]) {
        input[field] = (asBigInt(input[field], field) + TIME_OFFSET_SEC).toString();
      }
    }
    if (SCENARIO === "far-mismatch") {
      input.target_lat_e7_norm = (asBigInt(input.target_lat_e7_norm, "target latitude") + 5000n).toString();
      input.measured_range_cm = "341";
    } else if (SCENARIO !== "baseline") {
      throw new Error(`unsupported UAV_V2_SCENARIO: ${SCENARIO}`);
    }
    const remoteId = asBigInt(input.remote_id, "remote_id");
    const targetTime = asBigInt(input.target_time_sec, "target_time_sec");
    const timeBucket = targetTime / TIME_BUCKET_SEC;
    input.session_salt = sessionSalt.toString();
    const droneId = fieldBigInt(poseidon([DOMAIN_RID_V2, remoteId, sessionSalt, timeBucket]));
    const targetCommitment = fieldBigInt(poseidon([
      asBigInt(input.target_lat_e7_norm, "target latitude"),
      asBigInt(input.target_lon_e7_norm, "target longitude"),
      asBigInt(input.target_alt_cm, "target altitude"),
      asBigInt(input.target_time_sec, "target time"),
    ]));
    const measuredRange = asBigInt(input.measured_range_cm, "measured range");
    if (measuredRange <= 0n) throw new Error("measured range must be greater than zero");
    const timeDelta = asBigInt(input.drone_time_sec, "drone time") - asBigInt(input.target_time_sec, "target time");
    if ((timeDelta < 0n ? -timeDelta : timeDelta) > 5n) {
      throw new Error("synthetic observation timestamps must differ by at most five seconds");
    }
    const observationEligible = 1n;
    const consistency = consistencyForRangeCm(input, measuredRange);
    // V2 constrains the signed freshness value to the observation timestamp
    // used to derive time_bucket. The old fixture scalar was not a clock.
    const freshness = asBigInt(input.target_time_sec, "target_time_sec");
    input.freshness = freshness.toString();
    const message = poseidon([
      DOMAIN_V2,
      droneId,
      targetCommitment,
      observationEligible,
      freshness,
      measuredRange,
      CALIBRATION_PROFILE_ID,
      consistency,
    ]);
    const privateKey = Buffer.from(DEVICE_PRIV_HEX[i], "hex");
    const publicKey = eddsa.prv2pub(privateKey);
    const signature = eddsa.signPoseidon(privateKey, F.e(message));
    input.calibration_profile_id = CALIBRATION_PROFILE_ID.toString();
    input.device_pubkey_ax = fieldBigInt(publicKey[0]).toString();
    input.device_pubkey_ay = fieldBigInt(publicKey[1]).toString();
    input.sig_s = signature.S.toString();
    input.sig_r8x = fieldBigInt(signature.R8[0]).toString();
    input.sig_r8y = fieldBigInt(signature.R8[1]).toString();
    const outputPath = path.join(outputDir, `input_dev${i}.json`);
    fs.writeFileSync(outputPath, `${JSON.stringify(input, null, 2)}\n`, { flag: "wx", mode: 0o600 });
    console.log(`observer ${i}: scenario=${SCENARIO} observation_eligible=${observationEligible} range=${measuredRange}cm consistency_ok=${consistency} profile=${CALIBRATION_PROFILE_ID} timeOffset=${TIME_OFFSET_SEC}s`);
  }
  console.log(`V2 synthetic inputs written to ${outputDir} (run scope ${RUN_ID})`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
