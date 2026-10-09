"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");
const { buildEddsa, buildPoseidon } = require("circomlibjs");

const {
  createWitnessFromCapture,
  expectedSharedTag,
  parseCaptureBytes,
  parseRawRidMessage,
} = require("./capture_to_witness_v2");

const ROOT = path.join(__dirname, "..");
const SESSION_KEY = Buffer.alloc(32, 0x11);
const OBSERVER_KEY = Buffer.alloc(32, 0x07);
const OBSERVER_ID = "observer-pi-01";
const RUN_ID = "field-run-test-01";
const PROFILE_ID = 2;
const EVENT_SEQ = 1;
const RECEIVE_MS = Date.UTC(2026, 9, 4, 12, 34, 56, 700);
const UAS_ID = "TEST-UAS-001";

function calibrationReport(overrides = {}) {
  return Buffer.from(JSON.stringify({
    schema: "signal.rssi-evaluation.v1",
    decision_policy: { consistency_tolerance_ratio: 0.9 },
    calibration_models: [{
      observer_id: OBSERVER_ID,
      calibration_profile_id: PROFILE_ID,
      rssi_at_1m_dbm: -40,
      path_loss_exponent: 2,
      calibration_rmse_db: 1,
      calibration_run_count: 2,
      calibration_samples: 4,
    }],
    input_artifacts: {
      calibration: { sha256: "a".repeat(64) },
      evaluation: { sha256: "b".repeat(64) },
    },
    ...overrides,
  }));
}

function basicIdMessage() {
  const raw = Buffer.alloc(25);
  raw[0] = 0x02; // Basic ID, ASTM/OpenDroneID protocol version 2
  raw[1] = 0x12;
  Buffer.from(UAS_ID, "ascii").copy(raw, 2);
  return raw;
}

function locationMessage(receiveMs = RECEIVE_MS) {
  const raw = Buffer.alloc(25);
  raw[0] = 0x12; // Location, ASTM/OpenDroneID protocol version 2
  raw.writeInt32LE(350000000, 5); // 35 degrees latitude
  raw.writeInt32LE(1390000100, 9); // about 0.91 m east
  raw.writeUInt16LE(2020, 15); // 10 m geometric altitude
  raw.writeUInt16LE(Math.floor((receiveMs % 3600000) / 100), 21);
  return raw;
}

function captureFixture({
  events,
  profileId = PROFILE_ID,
  observerLatitude = 35,
  observerLongitude = 139,
  observerAccuracy = 4.5,
  observerSource = "cli_asserted_unverified",
} = {}) {
  const observerLocation = {
    latitude_deg: observerLatitude,
    longitude_deg: observerLongitude,
    altitude_m: 10,
    accuracy_m: observerAccuracy,
    source: observerSource,
  };
  const identity = {
    run_id: RUN_ID,
    observer_id: OBSERVER_ID,
    calibration_profile_id: profileId,
    uas_id_tag_scope: "shared_session_key_and_run_id",
  };
  const basic = { idType: 1, uaType: 2, uasId: UAS_ID };
  const uasTag = expectedSharedTag(SESSION_KEY, RUN_ID, basic);
  const observation = (event, raw, messageType) => ({
    schema: "signal.observer-capture.v1",
    record_type: "observation",
    ...identity,
    capture_event_seq: event.sequence,
    captured_at_unix_ms: event.receiveMs,
    rssi_dbm: event.rssiDbm,
    transport: "BLE",
    observer_location: observerLocation,
    message_type: messageType,
    uas_id_tag: uasTag,
    raw_message_hex: raw.toString("hex"),
  });
  const inputEvents = events || [{
    sequence: EVENT_SEQ,
    receiveMs: RECEIVE_MS,
    rssiDbm: -40,
    basic: true,
    location: locationMessage(RECEIVE_MS),
  }];
  const observationRecords = [];
  for (const event of inputEvents) {
    if (event.basic !== false) observationRecords.push(observation(event, basicIdMessage(), "basic_id"));
    if (event.location) observationRecords.push(observation(event, event.location, "location"));
  }
  const records = [
    {
      schema: "signal.observer-capture.v1",
      record_type: "capture_start",
      ...identity,
      raw_payload_included: true,
      observer_location: observerLocation,
    },
    ...observationRecords,
    {
      schema: "signal.observer-capture.v1",
      record_type: "capture_end",
      ...identity,
      captured: observationRecords.length,
      capture_event_count: inputEvents.length,
    },
  ];
  return Buffer.from(`${records.map((record) => JSON.stringify(record)).join("\n")}\n`);
}

test("accepts ASTM protocol version 2 and rejects the prior version-0 fixture encoding", () => {
  assert.equal(parseRawRidMessage(basicIdMessage().toString("hex"), "test").type, "basic_id");
  const invalid = basicIdMessage();
  invalid[0] = 0x00;
  assert.throws(
    () => parseRawRidMessage(invalid.toString("hex"), "test"),
    /unsupported protocol version/,
  );
});

test("rejects an otherwise complete capture that records a BLE acquisition failure", () => {
  const records = captureFixture().toString("utf8").trim().split("\n").map((line) => JSON.parse(line));
  records.splice(records.length - 1, 0, {
    schema: "signal.observer-capture.v1",
    record_type: "capture_error",
    run_id: RUN_ID,
    observer_id: OBSERVER_ID,
    calibration_profile_id: PROFILE_ID,
    uas_id_tag_scope: "shared_session_key_and_run_id",
    failure_source: "ble_scan_start",
    error_type: "StateError",
    message: "BLE acquisition failed; this capture must not be used.",
  });

  assert.throws(
    () => parseCaptureBytes(Buffer.from(`${records.map((record) => JSON.stringify(record)).join("\n")}\n`)),
    /capture must contain exactly one start\/end record and no capture error/,
  );
});

test("rejects one capture event that mixes run-scoped UAS ID tags", async () => {
  const records = captureFixture().toString("utf8").trim().split("\n").map((line) => JSON.parse(line));
  const basicTag = records.find((record) => record.message_type === "basic_id").uas_id_tag;
  const mismatchedTag = `${basicTag[0] === "0" ? "1" : "0"}${basicTag.slice(1)}`;
  const location = records.find((record) => record.message_type === "location");
  location.uas_id_tag = mismatchedTag;
  const captureBytes = Buffer.from(`${records.map((record) => JSON.stringify(record)).join("\n")}\n`);

  await assert.rejects(
    () => makeWitness({ captureBytes }),
    /one capture event cannot contain multiple run-scoped UAS ID tags/,
  );
});

async function makeWitness(overrides = {}) {
  return createWitnessFromCapture({
    captureBytes: captureFixture(),
    eventSequence: EVENT_SEQ,
    windowStartUnixMs: RECEIVE_MS - 1000,
    windowEndUnixMs: RECEIVE_MS + 1000,
    sessionKey: SESSION_KEY,
    observerSecretKey: OBSERVER_KEY,
    calibrationReportBytes: calibrationReport(),
    ...overrides,
  });
}

test("creates a current V2 capture witness accepted by Circom", async () => {
  const captureEvents = [
    { sequence: 1, receiveMs: RECEIVE_MS - 500, rssiDbm: -42, basic: true, location: locationMessage(RECEIVE_MS - 500) },
    { sequence: 2, receiveMs: RECEIVE_MS, rssiDbm: -40, basic: false, location: locationMessage(RECEIVE_MS) },
    { sequence: 3, receiveMs: RECEIVE_MS + 500, rssiDbm: -38, basic: false, location: locationMessage(RECEIVE_MS + 500) },
  ];
  const captureBytes = captureFixture({ events: captureEvents });
  const result = await makeWitness({
    captureBytes,
    eventSequence: 1,
    windowStartUnixMs: RECEIVE_MS - 1000,
    windowEndUnixMs: RECEIVE_MS + 1000,
  });
  assert.equal(result.consistencyOk, true);
  assert.equal(result.witness.calibration_profile_id, String(PROFILE_ID));
  assert.equal(result.witness.measured_range_cm, "100");
  assert.equal(result.witness.drone_alt_cm, "101000");
  assert.equal(result.metadata.capture_event_count, 3);
  assert.equal(result.metadata.rssi_dbm_median, -40);
  assert.equal(result.metadata.remote_id_authentication_status, "not_evaluated");
  assert.equal(result.metadata.observer_location_status, "cli_asserted_unverified");
  assert.equal(result.metadata.sensor_truth_status, "receiver_reported_rssi; not hardware_attested");
  assert.equal(result.metadata.observer_location_accuracy_m, 4.5);
  assert.doesNotMatch(JSON.stringify(result.metadata), /TEST-UAS-001|139\.00001|35\.0/);

  const [poseidon, eddsa] = await Promise.all([buildPoseidon(), buildEddsa()]);
  const F = poseidon.F;
  const remoteId = BigInt(result.witness.remote_id);
  const salt = BigInt(result.witness.session_salt);
  const time = BigInt(result.witness.target_time_sec);
  const bucket = time / 60n;
  const droneCommitment = F.toObject(poseidon([0x5349474e414c5f5249445f5632n, remoteId, salt, bucket]));
  const targetCommitment = F.toObject(poseidon([
    BigInt(result.witness.target_lat_e7_norm),
    BigInt(result.witness.target_lon_e7_norm),
    BigInt(result.witness.target_alt_cm),
    time,
  ]));
  const message = poseidon([
    0x4f42535f4c4541465f5632n,
    droneCommitment,
    targetCommitment,
    1n,
    time,
    BigInt(result.witness.measured_range_cm),
    BigInt(result.witness.calibration_profile_id),
    1n,
  ]);
  const signature = {
    S: BigInt(result.witness.sig_s),
    R8: [F.e(BigInt(result.witness.sig_r8x)), F.e(BigInt(result.witness.sig_r8y))],
  };
  const publicKey = [F.e(BigInt(result.witness.device_pubkey_ax)), F.e(BigInt(result.witness.device_pubkey_ay))];
  assert.equal(eddsa.verifyPoseidon(F.e(message), signature, publicKey), true);

  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "capture-to-witness-v2-test-"));
  try {
    fs.chmodSync(tempDir, 0o700);
    const circuitDir = path.join(tempDir, "circuit");
    fs.mkdirSync(circuitDir, { mode: 0o700 });
    const compile = spawnSync("circom", [
      "circuits/uav_witness_attestation_v2.circom", "--O2", "--r1cs", "--wasm",
      "-l", "node_modules", "-o", circuitDir,
    ], { cwd: ROOT, encoding: "utf8", timeout: 120000 });
    assert.equal(compile.status, 0, `${compile.stdout}\n${compile.stderr}`);
    const wasmDir = path.join(circuitDir, "uav_witness_attestation_v2_js");
    const input = path.join(tempDir, "input.json");
    const witness = path.join(tempDir, "input.wtns");
    fs.writeFileSync(input, `${JSON.stringify(result.witness)}\n`, { mode: 0o600, flag: "wx" });
    const calculate = spawnSync("node", [
      path.join(wasmDir, "generate_witness.js"),
      path.join(wasmDir, "uav_witness_attestation_v2.wasm"), input, witness,
    ], { cwd: ROOT, encoding: "utf8", timeout: 120000 });
    assert.equal(calculate.status, 0, `${calculate.stdout}\n${calculate.stderr}`);
    assert.ok(fs.statSync(witness).size > 0, "Circom witness file was not created");

    if (process.env.RUN_CAPTURE_WITNESS_GROTH16 === "1") {
      // Disposable, single-contributor integration test only. Never publish
      // its zkey/VK or treat this contribution as a trusted ceremony.
      const snarkjs = process.env.SNARKJS_BIN || "snarkjs";
      const pot0 = path.join(tempDir, "pot0.ptau");
      const pot1 = path.join(tempDir, "pot1.ptau");
      const potFinal = path.join(tempDir, "pot-final.ptau");
      const zkey = path.join(tempDir, "test-only.zkey");
      const proof = path.join(tempDir, "proof.json");
      const publicSignals = path.join(tempDir, "public.json");
      const verificationKey = path.join(tempDir, "verification_key.json");
      const snark = (args) => {
        const result = spawnSync(snarkjs, args, { cwd: ROOT, encoding: "utf8", timeout: 300000 });
        assert.equal(result.status, 0, `${args.join(" ")}\n${result.error?.message || ""}\n${result.stdout || ""}\n${result.stderr || ""}`);
      };
      // Current V2 R1CS has 6,201 constraints; 2^13 powers are sufficient.
      snark(["powersoftau", "new", "bn128", "13", pot0]);
      snark([
        "powersoftau", "contribute", pot0, pot1,
        "--name=capture-to-witness test only", `-e=${crypto.randomBytes(64).toString("hex")}`,
      ]);
      snark(["powersoftau", "prepare", "phase2", pot1, potFinal]);
      snark(["powersoftau", "verify", potFinal]);
      snark(["groth16", "setup", path.join(circuitDir, "uav_witness_attestation_v2.r1cs"), potFinal, zkey]);
      snark(["zkey", "verify", path.join(circuitDir, "uav_witness_attestation_v2.r1cs"), potFinal, zkey]);
      snark(["groth16", "prove", zkey, witness, proof, publicSignals]);
      snark(["zkey", "export", "verificationkey", zkey, verificationKey]);
      snark(["groth16", "verify", verificationKey, publicSignals, proof]);
    }

    const capturePath = path.join(tempDir, "capture.jsonl");
    const sessionKeyPath = path.join(tempDir, "session.key");
    const observerKeyPath = path.join(tempDir, "observer.key");
    const calibrationPath = path.join(tempDir, "evaluation-report.json");
    const cliWitnessPath = path.join(tempDir, "cli-input.json");
    const metadataPath = path.join(tempDir, "cli-provenance.json");
    fs.writeFileSync(capturePath, captureBytes, { mode: 0o600, flag: "wx" });
    fs.writeFileSync(sessionKeyPath, SESSION_KEY, { mode: 0o600, flag: "wx" });
    fs.writeFileSync(observerKeyPath, OBSERVER_KEY, { mode: 0o600, flag: "wx" });
    fs.writeFileSync(calibrationPath, calibrationReport(), { mode: 0o600, flag: "wx" });
    const args = [
      path.join(__dirname, "capture_to_witness_v2.js"),
      "--capture", capturePath,
      "--event-seq", "1",
      "--window-start-unix-ms", String(RECEIVE_MS - 1000),
      "--window-end-unix-ms", String(RECEIVE_MS + 1000),
      "--session-key-file", sessionKeyPath,
      "--observer-key-file", observerKeyPath,
      "--calibration-report", calibrationPath,
      "--output", cliWitnessPath,
      "--provenance-output", metadataPath,
    ];
    const cli = spawnSync(process.execPath, args, { cwd: ROOT, encoding: "utf8", timeout: 120000 });
    assert.equal(cli.status, 0, `${cli.stdout}\n${cli.stderr}`);
    assert.deepEqual(JSON.parse(fs.readFileSync(cliWitnessPath, "utf8")), result.witness);
    assert.equal(JSON.parse(fs.readFileSync(metadataPath, "utf8")).remote_id_authentication_status, "not_evaluated");
    assert.equal(fs.statSync(cliWitnessPath).mode & 0o777, 0o600);
    assert.equal(fs.statSync(metadataPath).mode & 0o777, 0o600);
    const before = fs.readFileSync(cliWitnessPath);
    const rerun = spawnSync(process.execPath, args, { cwd: ROOT, encoding: "utf8", timeout: 120000 });
    assert.equal(rerun.status, 2);
    assert.deepEqual(fs.readFileSync(cliWitnessPath), before, "a rerun must not overwrite witness material");
    const unknownOption = spawnSync(process.execPath, [...args, "--ignore-errors", "true"], {
      cwd: ROOT, encoding: "utf8", timeout: 120000,
    });
    assert.equal(unknownOption.status, 2);
    assert.match(unknownOption.stderr, /unknown option --ignore-errors/);
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test("preserves the phone GPS source while keeping it explicitly unverified", async () => {
  const result = await createWitnessFromCapture({
    captureBytes: captureFixture({ observerSource: "phone_gps_asserted_unverified" }),
    eventSequence: EVENT_SEQ,
    windowStartUnixMs: RECEIVE_MS - 1000,
    windowEndUnixMs: RECEIVE_MS + 1000,
    sessionKey: SESSION_KEY,
    observerSecretKey: OBSERVER_KEY,
    calibrationReportBytes: calibrationReport(),
  });
  assert.equal(result.metadata.observer_location_status, "phone_gps_asserted_unverified");
  assert.equal(result.metadata.observer_location_accuracy_m, 4.5);
});

test("rejects malformed reported phone GPS accuracy", async () => {
  await assert.rejects(
    makeWitness({
      captureBytes: captureFixture({ observerAccuracy: -1 }),
    }),
    /accuracy must be a finite nonnegative number/,
  );
});

test("rejects a different session key, preventing accidental cross-run linkage", async () => {
  await assert.rejects(
    makeWitness({ sessionKey: Buffer.alloc(32, 0x22) }),
    /does not match the capture's Basic ID pseudonym/,
  );
});

test("rejects a stale seconds-within-hour timestamp", async () => {
  const staleMs = RECEIVE_MS - 20000;
  await assert.rejects(
    makeWitness({ captureBytes: captureFixture({ events: [{
      sequence: EVENT_SEQ,
      receiveMs: RECEIVE_MS,
      rssiDbm: -40,
      basic: true,
      location: locationMessage(staleMs),
    }] }) }),
    /more than five seconds/,
  );
});

test("rejects a calibration report without this observer/profile", async () => {
  const report = calibrationReport({ calibration_models: [] });
  await assert.rejects(
    makeWitness({ calibrationReportBytes: report }),
    /exactly one matching observer\/profile model/,
  );
});

test("aggregates one RSSI median sample per event within the selected bucket window", async () => {
  const events = [
    { sequence: 1, receiveMs: RECEIVE_MS - 500, rssiDbm: -42, basic: true, location: locationMessage(RECEIVE_MS - 500) },
    { sequence: 2, receiveMs: RECEIVE_MS, rssiDbm: -40, basic: false, location: locationMessage(RECEIVE_MS) },
    { sequence: 3, receiveMs: RECEIVE_MS + 500, rssiDbm: -38, basic: false, location: locationMessage(RECEIVE_MS + 500) },
  ];
  const result = await makeWitness({
    captureBytes: captureFixture({ events }),
    eventSequence: 1,
    windowStartUnixMs: RECEIVE_MS - 1000,
    windowEndUnixMs: RECEIVE_MS + 1000,
  });
  assert.equal(result.metadata.capture_event_count, 3);
  assert.equal(result.metadata.location_message_count, 3);
  assert.equal(result.metadata.rssi_dbm_median, -40);
  assert.equal(result.witness.measured_range_cm, "100");
});

test("joins the anchor Basic ID and Location messages found in separate events", async () => {
  const events = [
    { sequence: 1, receiveMs: RECEIVE_MS - 500, rssiDbm: -42, basic: true, location: null },
    { sequence: 2, receiveMs: RECEIVE_MS, rssiDbm: -40, basic: false, location: locationMessage(RECEIVE_MS) },
  ];
  const result = await makeWitness({
    captureBytes: captureFixture({ events }),
    eventSequence: 1,
    windowStartUnixMs: RECEIVE_MS - 1000,
    windowEndUnixMs: RECEIVE_MS + 1000,
  });
  assert.equal(result.metadata.capture_event_count, 2);
  assert.equal(result.metadata.location_message_count, 1);
});

test("rejects a decision window with no Location messages", async () => {
  const onlyBasic = captureFixture({ events: [{
    sequence: EVENT_SEQ,
    receiveMs: RECEIVE_MS,
    rssiDbm: -40,
    basic: true,
    location: null,
  }] });
  const lines = onlyBasic.toString("utf8").trim().split("\n").map((line) => JSON.parse(line));
  await assert.rejects(
    makeWitness({ captureBytes: Buffer.from(`${lines.map((line) => JSON.stringify(line)).join("\n")}\n`) }),
    /at least one valid Location/,
  );
});

test("rejects a decision window crossing a 60-second bucket", async () => {
  await assert.rejects(
    makeWitness({
      windowStartUnixMs: RECEIVE_MS - 30000,
      windowEndUnixMs: RECEIVE_MS + 30000,
    }),
    /fit inside one 60-second time bucket/,
  );
});

test("uses half-away-from-zero coordinate encoding and enforces the projection latitude", async () => {
  const negativeLongitude = await makeWitness({
    captureBytes: captureFixture({ observerLongitude: -0.00000005 }),
  });
  assert.equal(negativeLongitude.witness.target_lon_e7_norm, "1799999999");

  await assert.rejects(
    makeWitness({ captureBytes: captureFixture({ observerLatitude: 36.01 }) }),
    /only supported near 35 degrees latitude/,
  );
});
