#!/usr/bin/env node
/*
 * Build one V2 leaf witness from an owner-private BLE decision window.
 *
 * This only attests the observer's report. It does not verify DRIP/RID
 * authenticity, observer location, RSSI sensor honesty, or calibration policy.
 */
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { buildEddsa, buildPoseidon } = require("circomlibjs");

const DOMAIN_V2 = 0x4f42535f4c4541465f5632n; // OBS_LEAF_V2
const DOMAIN_RID_V2 = 0x5349474e414c5f5249445f5632n; // SIGNAL_RID_V2
const RID_PROTOCOL_VERSION = 2;
const TIME_BUCKET_SEC = 60n;
const MAX_CAPTURE_BYTES = 64 * 1024 * 1024;
const OPAQUE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const SHA256 = /^[0-9a-f]{64}$/;

function parseOpaque(value, name) {
  if (typeof value !== "string" || !OPAQUE_ID.test(value)) {
    throw new Error(`${name} must be a bounded opaque ASCII identifier`);
  }
  return value;
}

function parseUint32(value, name) {
  if (!Number.isInteger(value) || value < 0 || value > 0xffffffff) {
    throw new Error(`${name} must be a uint32 integer`);
  }
  return value;
}

function readOwnerPrivateFile(filePath, label, maxBytes) {
  if (typeof fs.constants.O_NOFOLLOW !== "number") {
    throw new Error("platform cannot safely reject symlinked inputs");
  }
  let fd;
  try {
    fd = fs.openSync(path.resolve(filePath), fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
  } catch {
    throw new Error(`${label} cannot be safely opened`);
  }
  try {
    const stat = fs.fstatSync(fd);
    const mode = stat.mode & 0o777;
    if (!stat.isFile() || (mode & ~0o600) !== 0 || (mode & 0o400) === 0) {
      throw new Error(`${label} must be a regular owner-readable file with mode 0600 or stricter`);
    }
    if (typeof process.getuid === "function" && stat.uid !== process.getuid()) {
      throw new Error(`${label} must be owned by the current user`);
    }
    if (stat.size > maxBytes) throw new Error(`${label} exceeds the ${maxBytes}-byte limit`);
    return fs.readFileSync(fd);
  } finally {
    fs.closeSync(fd);
  }
}

function parseCaptureBytes(captureBytes) {
  if (!Buffer.isBuffer(captureBytes) || captureBytes.length === 0 || captureBytes.length > MAX_CAPTURE_BYTES) {
    throw new Error("capture JSONL must be non-empty and no larger than 64 MiB");
  }
  let decoded;
  try {
    decoded = new TextDecoder("utf-8", { fatal: true }).decode(captureBytes);
  } catch {
    throw new Error("capture JSONL must be valid UTF-8");
  }
  const records = decoded.split(/\r?\n/).filter((line) => line.length > 0).map((line, index) => {
    try {
      return JSON.parse(line);
    } catch {
      throw new Error(`capture JSONL line ${index + 1} is invalid JSON`);
    }
  });
  const starts = records.filter((record) => record.record_type === "capture_start");
  const ends = records.filter((record) => record.record_type === "capture_end");
  const observations = records.filter((record) => record.record_type === "observation");
  if (starts.length !== 1 || ends.length !== 1 || records.some((r) => r.record_type === "capture_error")) {
    throw new Error("capture must contain exactly one start/end record and no capture error");
  }
  const start = starts[0];
  const end = ends[0];
  if (records[0] !== start || records[records.length - 1] !== end) {
    throw new Error("capture start/end records must bracket the JSONL observations");
  }
  if (start.schema !== "signal.observer-capture.v1" || start.raw_payload_included !== true) {
    throw new Error("capture must use v1 schema and include raw payloads");
  }
  if (observations.length === 0 || end.captured !== observations.length) {
    throw new Error("capture_end count does not match observation records");
  }
  const eventSeqs = new Set();
  const uasTagsByEvent = new Map();
  for (const record of records) {
    if (record.schema !== "signal.observer-capture.v1") throw new Error("unsupported capture schema");
    for (const key of ["run_id", "observer_id", "calibration_profile_id", "uas_id_tag_scope"]) {
      if (record[key] !== start[key]) throw new Error(`capture identity mismatch in ${key}`);
    }
  }
  const runId = parseOpaque(start.run_id, "run_id");
  const observerId = parseOpaque(start.observer_id, "observer_id");
  const profileId = parseUint32(start.calibration_profile_id, "calibration_profile_id");
  if (start.uas_id_tag_scope !== "shared_session_key_and_run_id") {
    throw new Error("capture must use the shared run-scoped session key");
  }
  for (const record of observations) {
    if (!Number.isSafeInteger(record.capture_event_seq) || record.capture_event_seq < 1) {
      throw new Error("capture_event_seq must be a positive safe integer");
    }
    eventSeqs.add(record.capture_event_seq);
    if (record.uas_id_tag !== undefined && record.uas_id_tag !== null) {
      if (typeof record.uas_id_tag !== "string" || !/^[0-9a-f]{24}$/.test(record.uas_id_tag)) {
        throw new Error("uas_id_tag must be a 24-character lowercase hexadecimal pseudonym");
      }
      const tags = uasTagsByEvent.get(record.capture_event_seq) || new Set();
      tags.add(record.uas_id_tag);
      if (tags.size > 1) {
        throw new Error("one capture event cannot contain multiple run-scoped UAS ID tags");
      }
      uasTagsByEvent.set(record.capture_event_seq, tags);
    }
  }
  if (end.capture_event_count !== eventSeqs.size) {
    throw new Error("capture_end capture_event_count does not match observation records");
  }
  return {
    records,
    start,
    observations,
    runId,
    observerId,
    profileId,
    captureSha256: crypto.createHash("sha256").update(captureBytes).digest("hex"),
  };
}

function parseRawRidMessage(hex, label) {
  if (typeof hex !== "string" || !/^(?:[0-9a-fA-F]{50})$/.test(hex)) {
    throw new Error(`${label} raw_message_hex must be exactly 25 bytes`);
  }
  const raw = Buffer.from(hex, "hex");
  const type = raw[0] >>> 4;
  if ((raw[0] & 0x0f) !== RID_PROTOCOL_VERSION) {
    throw new Error(`${label} uses an unsupported protocol version`);
  }
  if (type === 0) {
    const idField = raw.subarray(2, 22);
    const terminator = idField.indexOf(0);
    const idBytes = terminator < 0 ? idField : idField.subarray(0, terminator);
    if (terminator >= 0 && idField.subarray(terminator).some((byte) => byte !== 0)) {
      throw new Error("Basic ID must have only zero padding after its first NUL");
    }
    if (idBytes.length === 0 || idBytes.some((byte) => byte < 0x20 || byte > 0x7e)) {
      throw new Error("Basic ID must contain printable ASCII");
    }
    const uasId = idBytes.toString("ascii");
    if (uasId.trim() !== uasId) throw new Error("Basic ID with edge whitespace is not canonical");
    return {
      type: "basic_id",
      idType: raw[1] >>> 4,
      uaType: raw[1] & 0x0f,
      uasId,
      idField: Buffer.from(idField),
    };
  }
  if (type === 1) {
    const latitudeE7 = BigInt(raw.readInt32LE(5));
    const longitudeE7 = BigInt(raw.readInt32LE(9));
    if (latitudeE7 < -900000000n || latitudeE7 > 900000000n ||
        longitudeE7 < -1800000000n || longitudeE7 > 1800000000n) {
      throw new Error("Location coordinates are outside valid bounds");
    }
    const altitudeRaw = raw.readUInt16LE(15);
    const timestampTenths = raw.readUInt16LE(21);
    if (altitudeRaw === 0xffff) throw new Error("Location message has no geometric altitude");
    if (timestampTenths === 0xffff || timestampTenths >= 36000) {
      throw new Error("Location message has no valid seconds-within-hour timestamp");
    }
    return {
      type: "location",
      latitudeE7,
      longitudeE7,
      altitudeCmShifted: BigInt(altitudeRaw) * 50n - 100000n,
      timestampTenths,
    };
  }
  return { type: type === 2 ? "authentication" : "other" };
}

function expectedSharedTag(sessionKey, runId, basic) {
  const parts = ["uas-id", runId, `${basic.idType}:${basic.uaType}:${basic.uasId}`]
    .map((value) => Buffer.from(value, "utf8"));
  const message = Buffer.concat([
    Buffer.from("signal.observer-tag.v1", "utf8"),
    ...parts.flatMap((part) => [u32be(part.length), part]),
  ]);
  return crypto.createHmac("sha256", sessionKey).update(message).digest("hex").slice(0, 24);
}

function u32be(value) {
  const bytes = Buffer.alloc(4);
  bytes.writeUInt32BE(value);
  return bytes;
}

function readCalibrationModel(calibrationReportBytes, observerId, profileId) {
  let report;
  try {
    report = JSON.parse(calibrationReportBytes.toString("utf8"));
  } catch {
    throw new Error("calibration report is invalid JSON");
  }
  if (report.schema !== "signal.rssi-evaluation.v1" ||
      report.decision_policy?.consistency_tolerance_ratio !== 0.9 ||
      !Array.isArray(report.calibration_models)) {
    throw new Error("calibration report must be an RSSI evaluation v1 report using tolerance 0.9");
  }
  const matches = report.calibration_models.filter((model) =>
    model.observer_id === observerId && model.calibration_profile_id === profileId);
  if (matches.length !== 1) throw new Error("calibration report must contain exactly one matching observer/profile model");
  const model = matches[0];
  if (!Number.isFinite(model.rssi_at_1m_dbm) || !Number.isFinite(model.path_loss_exponent) ||
      model.path_loss_exponent <= 0 || model.path_loss_exponent > 10 ||
      !Number.isInteger(model.calibration_run_count) || model.calibration_run_count < 2 ||
      !Number.isInteger(model.calibration_samples) || model.calibration_samples < 3 ||
      !Number.isFinite(model.calibration_rmse_db) || model.calibration_rmse_db < 0) {
    throw new Error("calibration model is incomplete or lacks independent calibration runs");
  }
  const calibrationHash = report.input_artifacts?.calibration?.sha256;
  const evaluationHash = report.input_artifacts?.evaluation?.sha256;
  if (!SHA256.test(calibrationHash || "") || !SHA256.test(evaluationHash || "")) {
    throw new Error("calibration report must identify the calibration and held-out evaluation CSV hashes");
  }
  return {
    model,
    reportSha256: crypto.createHash("sha256").update(calibrationReportBytes).digest("hex"),
    calibrationCsvSha256: calibrationHash,
    evaluationCsvSha256: evaluationHash,
  };
}

function unwrapRidTimestampMs(timestampTenths, receiveUnixMs) {
  if (!Number.isSafeInteger(receiveUnixMs) || receiveUnixMs < 0) {
    throw new Error("captured_at_unix_ms must be a nonnegative safe integer");
  }
  const hourMs = 3600000;
  const hourStartMs = Math.floor(receiveUnixMs / hourMs) * hourMs;
  const withinHourMs = timestampTenths * 100;
  const candidates = [-hourMs, 0, hourMs].map((offset) => hourStartMs + withinHourMs + offset);
  candidates.sort((a, b) => Math.abs(a - receiveUnixMs) - Math.abs(b - receiveUnixMs));
  const nearest = candidates[0];
  if (Math.abs(nearest - receiveUnixMs) > 5000) {
    throw new Error("Remote ID timestamp is more than five seconds from local receive time");
  }
  return nearest;
}

function median(values, label) {
  if (values.length === 0) throw new Error(`${label} requires at least one sample`);
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function roundHalfAwayFromZero(value) {
  return value < 0 ? -Math.round(-value) : Math.round(value);
}

function normalizedCoordinate(value, scale, offset, name) {
  if (!Number.isFinite(value)) throw new Error(`${name} must be finite`);
  const result = BigInt(roundHalfAwayFromZero(value * scale)) + offset;
  if (result < 0n || result > 0xffffffffn) throw new Error(`${name} is outside the V2 uint32 encoding`);
  return result;
}

function consistencyForRangeCm(input, rangeCm) {
  const abs = (a, b) => a >= b ? a - b : b - a;
  const lat = abs(input.drone_lat_e7_norm, input.target_lat_e7_norm) * 11132000n;
  const lon = abs(input.drone_lon_e7_norm, input.target_lon_e7_norm) * 9128800n;
  const alt = abs(input.drone_alt_cm, input.target_alt_cm) * 10000000n;
  const claimedDistanceSq = lat * lat + lon * lon + alt * alt;
  const base = rangeCm * 10000000n;
  const lower = (base * 10n) ** 2n;
  const upper = (base * 190n) ** 2n;
  const scaledClaim = claimedDistanceSq * 8100n;
  return lower <= scaledClaim && scaledClaim <= upper ? 1n : 0n;
}

function encodeRemoteId(basic) {
  return BigInt(`0x${Buffer.concat([
    Buffer.from([basic.idType, basic.uaType]), basic.idField,
  ]).toString("hex")}`);
}

async function createWitnessFromCapture({
  captureBytes,
  eventSequence,
  windowStartUnixMs,
  windowEndUnixMs,
  sessionKey,
  observerSecretKey,
  calibrationReportBytes,
}) {
  if (!Buffer.isBuffer(sessionKey) || sessionKey.length !== 32) {
    throw new Error("session key must contain exactly 32 bytes");
  }
  if (!Buffer.isBuffer(observerSecretKey) || observerSecretKey.length !== 32) {
    throw new Error("observer BabyJubJub private key must contain exactly 32 raw bytes");
  }
  if (!Number.isSafeInteger(eventSequence) || eventSequence < 1) {
    throw new Error("event sequence must be a positive safe integer");
  }
  if (!Number.isSafeInteger(windowStartUnixMs) || !Number.isSafeInteger(windowEndUnixMs) ||
      windowStartUnixMs < 0 || windowEndUnixMs <= windowStartUnixMs ||
      windowEndUnixMs - windowStartUnixMs > 60000) {
    throw new Error("decision window must be a positive interval no longer than 60 seconds");
  }
  if (Math.floor(windowStartUnixMs / 60000) !== Math.floor((windowEndUnixMs - 1) / 60000)) {
    throw new Error("decision window must fit inside one 60-second time bucket");
  }
  const capture = parseCaptureBytes(captureBytes);
  const calibration = readCalibrationModel(calibrationReportBytes, capture.observerId, capture.profileId);
  const anchor = capture.observations.filter((record) => record.capture_event_seq === eventSequence);
  if (anchor.length === 0) throw new Error("anchor capture event sequence was not found");
  const anchorTimeValues = new Set(anchor.map((record) => record.captured_at_unix_ms));
  if (anchorTimeValues.size !== 1) throw new Error("anchor event has inconsistent receive timestamps");
  const anchorTime = [...anchorTimeValues][0];
  if (!Number.isSafeInteger(anchorTime) || anchorTime < windowStartUnixMs || anchorTime >= windowEndUnixMs) {
    throw new Error("anchor event must lie inside the selected decision window");
  }
  if (Math.floor(anchorTime / 60000) !== Math.floor(windowStartUnixMs / 60000)) {
    throw new Error("anchor event and decision window must use the same 60-second bucket");
  }
  if (anchor.some((record) => record.transport !== "BLE" || !record.raw_message_hex)) {
    throw new Error("anchor event must contain raw BLE messages");
  }
  const anchorMessages = anchor.map((record) => ({
    record,
    message: parseRawRidMessage(record.raw_message_hex, "anchor event"),
  }));
  const basicMessages = anchorMessages.filter((entry) => entry.message.type === "basic_id");
  if (basicMessages.length !== 1) throw new Error("anchor event must contain exactly one raw Basic ID message");
  const basic = basicMessages[0].message;
  const uasTag = expectedSharedTag(sessionKey, capture.runId, basic);
  if (basicMessages[0].record.uas_id_tag !== uasTag) {
    throw new Error("shared session key/run ID does not match the capture's Basic ID pseudonym");
  }
  const taggedSequences = new Set(capture.observations.filter((record) =>
    record.uas_id_tag === uasTag && Number.isSafeInteger(record.captured_at_unix_ms) &&
    record.captured_at_unix_ms >= windowStartUnixMs && record.captured_at_unix_ms < windowEndUnixMs &&
    Math.floor(record.captured_at_unix_ms / 60000) === Math.floor(anchorTime / 60000),
  ).map((record) => record.capture_event_seq));
  if (!taggedSequences.has(eventSequence)) throw new Error("anchor event is not included in the tagged decision window");
  const eventSequences = [...taggedSequences].sort((a, b) => a - b);
  const rssiSamples = [];
  const receiveSamples = [];
  const locationSamples = [];
  for (const sequence of eventSequences) {
    const eventRecords = capture.observations.filter((record) => record.capture_event_seq === sequence);
    const times = new Set(eventRecords.map((record) => record.captured_at_unix_ms));
    const rssis = new Set(eventRecords.map((record) => record.rssi_dbm));
    if (times.size !== 1 || rssis.size !== 1) throw new Error("a capture event has inconsistent time or RSSI values");
    const receiveMs = [...times][0];
    if (!Number.isSafeInteger(receiveMs) || receiveMs < windowStartUnixMs || receiveMs >= windowEndUnixMs ||
        Math.floor(receiveMs / 60000) !== Math.floor(anchorTime / 60000)) {
      throw new Error("capture event escaped the selected time window or bucket");
    }
    const rssi = [...rssis][0];
    if (!Number.isInteger(rssi) || rssi < -200 || rssi > 50) throw new Error("RSSI must be an integer in -200..50 dBm");
    const eventMessages = eventRecords.map((record) => {
      if (record.transport !== "BLE" || !record.raw_message_hex) throw new Error("window events must contain raw BLE messages");
      return { record, message: parseRawRidMessage(record.raw_message_hex, "window event") };
    });
    for (const entry of eventMessages) {
      if (entry.message.type === "basic_id") {
        const otherId = encodeRemoteId(entry.message);
        if (otherId !== encodeRemoteId(basic) || expectedSharedTag(sessionKey, capture.runId, entry.message) !== uasTag) {
          throw new Error("a different Basic ID was found inside the selected run-scoped tag");
        }
      }
      if (entry.message.type === "location") {
        const timestampMs = unwrapRidTimestampMs(entry.message.timestampTenths, receiveMs);
        locationSamples.push({
          latitudeE7: Number(entry.message.latitudeE7),
          longitudeE7: Number(entry.message.longitudeE7),
          altitudeCm: Number(entry.message.altitudeCmShifted),
          timestampMs,
        });
      }
    }
    rssiSamples.push(rssi);
    receiveSamples.push(receiveMs);
  }
  if (locationSamples.length === 0) throw new Error("decision window must contain at least one valid Location message");
  const observer = capture.start.observer_location;
  if (!observer || !["cli_asserted_unverified", "phone_gps_asserted_unverified"].includes(observer.source) ||
      !Number.isFinite(observer.latitude_deg) || !Number.isFinite(observer.longitude_deg) ||
      !Number.isFinite(observer.altitude_m) || observer.latitude_deg < -90 || observer.latitude_deg > 90 ||
      observer.longitude_deg < -180 || observer.longitude_deg > 180) {
    throw new Error("capture_start must contain asserted observer latitude/longitude/altitude");
  }
  if (observer.accuracy_m !== undefined &&
      (!Number.isFinite(observer.accuracy_m) || observer.accuracy_m < 0)) {
    throw new Error("observer location accuracy must be a finite nonnegative number when present");
  }
  const windowRecords = capture.observations.filter((record) => taggedSequences.has(record.capture_event_seq));
  if (windowRecords.some((record) => JSON.stringify(record.observer_location) !== JSON.stringify(observer))) {
    throw new Error("observer location changed within the selected decision window");
  }

  const receiveMedianMs = Math.round(median(receiveSamples, "RSSI decision window"));
  const ridMedianMs = Math.round(median(locationSamples.map((sample) => sample.timestampMs), "Location samples"));
  const receiveSec = BigInt(Math.floor(receiveMedianMs / 1000));
  const droneSec = BigInt(Math.floor(ridMedianMs / 1000));
  const rssiDbm = median(rssiSamples, "RSSI samples");
  if (Math.abs(Number(droneSec - receiveSec)) > 5) throw new Error("median Remote ID timestamp is more than five seconds from median receive time");
  const model = calibration.model;
  const log10Range = (model.rssi_at_1m_dbm - rssiDbm) / (10 * model.path_loss_exponent);
  if (!Number.isFinite(log10Range) || log10Range < -6 || log10Range > 9) {
    throw new Error("RSSI and calibration model imply an implausible range");
  }
  const rangeCm = BigInt(Math.round((10 ** log10Range) * 100));
  if (rangeCm <= 0n || rangeCm > 0xffffffffn) throw new Error("calculated range is outside uint32 centimeters");

  if (observer.latitude_deg < 34 || observer.latitude_deg > 36) {
    throw new Error("current V2 distance projection is only supported near 35 degrees latitude (34..36)");
  }
  const targetLat = normalizedCoordinate(observer.latitude_deg, 1e7, 900000000n, "observer latitude");
  const targetLon = normalizedCoordinate(observer.longitude_deg, 1e7, 1800000000n, "observer longitude");
  const targetAlt = normalizedCoordinate(observer.altitude_m, 100, 100000n, "observer altitude plus 1000m offset");
  const droneLat = BigInt(roundHalfAwayFromZero(median(locationSamples.map((sample) => sample.latitudeE7), "Location latitude"))) + 900000000n;
  const droneLon = BigInt(roundHalfAwayFromZero(median(locationSamples.map((sample) => sample.longitudeE7), "Location longitude"))) + 1800000000n;
  const droneAlt = BigInt(roundHalfAwayFromZero(
    median(locationSamples.map((sample) => sample.altitudeCm), "Location altitude"),
  )) + 100000n;
  if (droneLat < 0n || droneLat > 0xffffffffn || droneLon < 0n || droneLon > 0xffffffffn ||
      droneAlt < 0n || droneAlt > 0xffffffffn) {
    throw new Error("Remote ID coordinates are outside the V2 uint32 encoding");
  }
  const profileId = BigInt(capture.profileId);
  const targetCommitmentInput = {
    drone_lat_e7_norm: droneLat,
    drone_lon_e7_norm: droneLon,
    drone_alt_cm: droneAlt,
    target_lat_e7_norm: targetLat,
    target_lon_e7_norm: targetLon,
    target_alt_cm: targetAlt,
  };
  const consistency = consistencyForRangeCm(targetCommitmentInput, rangeCm);
  const sessionSaltBytes = crypto.createHmac("sha256", sessionKey)
    .update(Buffer.from(`signal.observer-circuit-salt.v2\0${capture.runId}`, "utf8"))
    .digest().subarray(0, 31);
  const sessionSalt = BigInt(`0x${sessionSaltBytes.toString("hex")}`);
  if (sessionSalt === 0n) throw new Error("derived session salt must not be zero");
  const targetTime = receiveSec;
  const remoteId = encodeRemoteId(basic);

  const [poseidon, eddsa] = await Promise.all([buildPoseidon(), buildEddsa()]);
  const F = poseidon.F;
  const field = (value) => F.toObject(value).toString();
  const bucket = targetTime / TIME_BUCKET_SEC;
  const droneCommitment = poseidon([DOMAIN_RID_V2, remoteId, sessionSalt, bucket]);
  const targetCommitment = poseidon([
    targetLat, targetLon, targetAlt, targetTime,
  ]);
  const signedMessage = poseidon([
    DOMAIN_V2,
    F.toObject(droneCommitment),
    F.toObject(targetCommitment),
    1n,
    targetTime,
    rangeCm,
    profileId,
    consistency,
  ]);
  const publicKey = eddsa.prv2pub(observerSecretKey);
  const signature = eddsa.signPoseidon(observerSecretKey, F.e(signedMessage));
  const witness = {
    drone_lat_e7_norm: droneLat.toString(),
    drone_lon_e7_norm: droneLon.toString(),
    drone_alt_cm: droneAlt.toString(),
    drone_time_sec: droneSec.toString(),
    target_lat_e7_norm: targetLat.toString(),
    target_lon_e7_norm: targetLon.toString(),
    target_alt_cm: targetAlt.toString(),
    target_time_sec: targetTime.toString(),
    measured_range_cm: rangeCm.toString(),
    calibration_profile_id: profileId.toString(),
    remote_id: remoteId.toString(),
    session_salt: sessionSalt.toString(),
    freshness: targetTime.toString(),
    device_pubkey_ax: field(publicKey[0]),
    device_pubkey_ay: field(publicKey[1]),
    sig_s: signature.S.toString(),
    sig_r8x: field(signature.R8[0]),
    sig_r8y: field(signature.R8[1]),
  };
  const metadata = {
    schema: "signal.observer-witness-provenance.v1",
    observer_id: capture.observerId,
    calibration_profile_id: capture.profileId,
    run_id: capture.runId,
    anchor_capture_event_seq: eventSequence,
    decision_window_start_unix_ms: windowStartUnixMs,
    decision_window_end_unix_ms: windowEndUnixMs,
    capture_event_count: eventSequences.length,
    location_message_count: locationSamples.length,
    capture_sha256: capture.captureSha256,
    calibration_report_sha256: calibration.reportSha256,
    calibration_csv_sha256: calibration.calibrationCsvSha256,
    heldout_evaluation_csv_sha256: calibration.evaluationCsvSha256,
    rssi_dbm_median: rssiDbm,
    measured_range_cm: rangeCm.toString(),
    calibration_model: {
      rssi_at_1m_dbm: model.rssi_at_1m_dbm,
      path_loss_exponent: model.path_loss_exponent,
      calibration_rmse_db: model.calibration_rmse_db,
      calibration_run_count: model.calibration_run_count,
      calibration_samples: model.calibration_samples,
    },
    observer_pubkey_x: field(publicKey[0]),
    observer_pubkey_y: field(publicKey[1]),
    remote_id_authentication_status: "not_evaluated",
    observer_location_status: observer.source,
    observer_location_accuracy_m: observer.accuracy_m ?? null,
    sensor_truth_status: "receiver_reported_rssi; not hardware_attested",
    limitations: [
      "The proof binds the observer signature to the reported range and circuit result; it does not prove how RSSI was sampled or converted.",
      "The Basic ID is only grouped as a claimed broadcast identifier; DRIP endorsement/signature verification is not performed.",
      "The Remote ID timestamp is seconds-within-hour; hour unwrapping cannot detect a replay delayed by an exact whole hour.",
    ],
  };
  return { witness, metadata, consistencyOk: consistency === 1n };
}

function writeOwnerPrivateNewFile(filePath, contents) {
  const resolved = path.resolve(filePath);
  fs.mkdirSync(path.dirname(resolved), { recursive: true, mode: 0o700 });
  let fd;
  try {
    fd = fs.openSync(resolved, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL, 0o600);
  } catch (error) {
    if (error.code === "EEXIST") throw new Error(`refusing to overwrite existing file: ${resolved}`);
    throw error;
  }
  try {
    fs.fchmodSync(fd, 0o600);
    fs.writeFileSync(fd, contents, "utf8");
    fs.fsyncSync(fd);
  } catch (error) {
    fs.closeSync(fd);
    fs.unlinkSync(resolved);
    throw error;
  }
  fs.closeSync(fd);
  return resolved;
}

function parseArguments(argv) {
  const values = {};
  const allowed = new Set([
    "capture", "event-seq", "window-start-unix-ms", "window-end-unix-ms",
    "session-key-file", "observer-key-file", "calibration-report", "output", "provenance-output",
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--help" || arg === "-h") return { help: true };
    if (!arg.startsWith("--") || index + 1 >= argv.length || argv[index + 1].startsWith("--")) {
      throw new Error(`expected --option value, received ${arg}`);
    }
    const key = arg.slice(2);
    if (!allowed.has(key)) throw new Error(`unknown option --${key}`);
    if (Object.hasOwn(values, key)) throw new Error(`duplicate option --${key}`);
    values[key] = argv[index + 1];
    index += 1;
  }
  const required = ["capture", "event-seq", "window-start-unix-ms", "window-end-unix-ms", "session-key-file", "observer-key-file", "calibration-report", "output", "provenance-output"];
  for (const key of required) if (!values[key]) throw new Error(`missing required option --${key}`);
  if (!/^[1-9][0-9]*$/.test(values["event-seq"]) || !Number.isSafeInteger(Number(values["event-seq"]))) {
    throw new Error("--event-seq must be a positive safe integer");
  }
  for (const key of ["window-start-unix-ms", "window-end-unix-ms"]) {
    if (!/^(?:0|[1-9][0-9]*)$/.test(values[key]) || !Number.isSafeInteger(Number(values[key]))) {
      throw new Error(`--${key} must be a canonical nonnegative safe integer`);
    }
  }
  if (path.resolve(values.output) === path.resolve(values["provenance-output"])) {
    throw new Error("--output and --provenance-output must be different files");
  }
  return values;
}

function usage() {
  return `Usage: node scripts/capture_to_witness_v2.js \\
  --capture PRIVATE.jsonl --event-seq N --window-start-unix-ms MS \\
  --window-end-unix-ms MS --session-key-file RUN.key \\
  --observer-key-file OBSERVER.babyjub --calibration-report EVALUATION.json \\
  --output witness.json --provenance-output witness.provenance.json

Inputs and outputs must be owner-private (mode 0600 or stricter). The anchor
event must contain exactly one raw Basic ID; the same-bucket decision window
supplies per-event median RSSI and at least one Location message. The
calibration report must be produced by uav/evaluate_rssi.py, use the V2 0.9
tolerance, and contain at least two independent calibration runs. This tool
does not authenticate the aircraft, observer location, or RSSI hardware.`;
}

async function main(argv = process.argv.slice(2)) {
  try {
    const args = parseArguments(argv);
    if (args.help) {
      process.stdout.write(`${usage()}\n`);
      return 0;
    }
    const captureBytes = readOwnerPrivateFile(args.capture, "capture JSONL", MAX_CAPTURE_BYTES);
    const sessionKey = readOwnerPrivateFile(args["session-key-file"], "session key", 32);
    const observerKey = readOwnerPrivateFile(args["observer-key-file"], "observer key", 32);
    const calibrationBytes = readOwnerPrivateFile(args["calibration-report"], "calibration report", 16 * 1024 * 1024);
    if (sessionKey.length !== 32 || observerKey.length !== 32) throw new Error("session and observer keys must be exactly 32 bytes");
    const result = await createWitnessFromCapture({
      captureBytes,
      eventSequence: Number(args["event-seq"]),
      windowStartUnixMs: Number(args["window-start-unix-ms"]),
      windowEndUnixMs: Number(args["window-end-unix-ms"]),
      sessionKey,
      observerSecretKey: observerKey,
      calibrationReportBytes: calibrationBytes,
    });
    const witnessText = `${JSON.stringify(result.witness, null, 2)}\n`;
    const metadataText = `${JSON.stringify(result.metadata, null, 2)}\n`;
    let witnessPath;
    try {
      witnessPath = writeOwnerPrivateNewFile(args.output, witnessText);
      const provenancePath = writeOwnerPrivateNewFile(args["provenance-output"], metadataText);
      process.stdout.write(`witness created; consistency_ok=${result.consistencyOk ? 1 : 0}; remote_id_authentication=not_evaluated\n`);
      process.stdout.write(`private witness: ${witnessPath}\nprivate provenance: ${provenancePath}\n`);
      return 0;
    } catch (error) {
      if (witnessPath) fs.unlinkSync(witnessPath);
      throw error;
    }
  } catch (error) {
    process.stderr.write(`${error.message}\n\n${usage()}\n`);
    return 2;
  }
}

if (require.main === module) {
  main().then((code) => { process.exitCode = code; });
}

module.exports = {
  createWitnessFromCapture,
  expectedSharedTag,
  parseCaptureBytes,
  parseRawRidMessage,
  readCalibrationModel,
};
