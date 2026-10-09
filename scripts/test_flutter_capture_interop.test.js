"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const ROOT = path.join(__dirname, "..");
const APP = path.join(ROOT, "rapidsnark_app");
const SESSION_KEY = Buffer.alloc(32, 0x11);
const OBSERVER_KEY = Buffer.alloc(32, 0x07);

test("Flutter recorder JSONL becomes a V2 witness accepted by the current Circom leaf", () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "flutter-capture-interop-"));
  fs.chmodSync(tempDir, 0o700);
  try {
    const captureDir = path.join(tempDir, "phone-capture");
    fs.mkdirSync(captureDir, { mode: 0o700 });
    const dart = process.env.DART_BIN || "dart";
    const generated = spawnSync(dart, [
      "run",
      "tool/generate_v2_observer_capture_fixture.dart",
      captureDir,
    ], { cwd: APP, encoding: "utf8", timeout: 180000 });
    assert.equal(generated.status, 0,
      `${generated.error?.message || ""}\n${generated.stdout}\n${generated.stderr}`);
    const resultLine = generated.stdout.trim().split(/\r?\n/).filter(Boolean).at(-1);
    const fixture = JSON.parse(resultLine);
    assert.equal(path.dirname(fixture.capture_path), captureDir);

    const capturePath = fixture.capture_path;
    const dartRecords = fs.readFileSync(capturePath, "utf8").trim().split(/\r?\n/)
      .map((line) => JSON.parse(line));
    const dartObservations = dartRecords.filter((record) => record.record_type === "observation");
    assert.equal(dartObservations[0].message_pack_size, 2);
    assert.equal(dartObservations[0].capture_event_seq, dartObservations[1].capture_event_seq);
    assert.equal(dartObservations[0].raw_message_pack_hex, dartObservations[1].raw_message_pack_hex);
    const sessionKeyPath = path.join(tempDir, "session.key");
    const observerKeyPath = path.join(tempDir, "observer.key");
    const calibrationPath = path.join(tempDir, "evaluation-report.json");
    const witnessPath = path.join(tempDir, "phone-input.json");
    const provenancePath = path.join(tempDir, "phone-provenance.json");
    fs.writeFileSync(sessionKeyPath, SESSION_KEY, { mode: 0o600, flag: "wx" });
    fs.writeFileSync(observerKeyPath, OBSERVER_KEY, { mode: 0o600, flag: "wx" });
    fs.writeFileSync(calibrationPath, JSON.stringify({
      schema: "signal.rssi-evaluation.v1",
      decision_policy: { consistency_tolerance_ratio: 0.9 },
      calibration_models: [{
        observer_id: fixture.observer_id,
        calibration_profile_id: fixture.calibration_profile_id,
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
    }), { mode: 0o600, flag: "wx" });

    const cliArgs = [
      path.join(__dirname, "capture_to_witness_v2.js"),
      "--capture", capturePath,
      "--event-seq", String(fixture.event_seq),
      "--window-start-unix-ms", String(fixture.window_start_unix_ms),
      "--window-end-unix-ms", String(fixture.window_end_unix_ms),
      "--session-key-file", sessionKeyPath,
      "--observer-key-file", observerKeyPath,
      "--calibration-report", calibrationPath,
      "--output", witnessPath,
      "--provenance-output", provenancePath,
    ];
    // A naive adb redirection commonly creates mode 0644. The adapter rejects
    // that copy; use `umask 077` before exporting sensitive phone captures.
    fs.chmodSync(capturePath, 0o644);
    const exposedCopy = spawnSync(process.execPath, cliArgs, {
      cwd: ROOT, encoding: "utf8", timeout: 120000,
    });
    assert.equal(exposedCopy.status, 2);
    assert.match(exposedCopy.stderr, /capture JSONL must be a regular owner-readable file with mode 0600 or stricter/);
    fs.chmodSync(capturePath, 0o600);

    const converted = spawnSync(process.execPath, cliArgs, {
      cwd: ROOT, encoding: "utf8", timeout: 120000,
    });
    assert.equal(converted.status, 0, `${converted.stdout}\n${converted.stderr}`);
    const witness = JSON.parse(fs.readFileSync(witnessPath, "utf8"));
    const provenance = JSON.parse(fs.readFileSync(provenancePath, "utf8"));
    assert.equal(provenance.observer_id, fixture.observer_id);
    assert.equal(provenance.remote_id_authentication_status, "not_evaluated");
    assert.equal(provenance.observer_location_status, "phone_gps_asserted_unverified");
    assert.equal(provenance.observer_location_accuracy_m, 3.25);
    assert.equal(provenance.capture_event_count, 3);
    assert.equal(provenance.location_message_count, 3);
    assert.equal(provenance.rssi_dbm_median, -40);
    assert.equal(witness.measured_range_cm, "100");
    assert.doesNotMatch(JSON.stringify(provenance), /TEST-PHONE-001|139\.00001|35\.0/);

    const circuitDir = path.join(tempDir, "circuit");
    fs.mkdirSync(circuitDir, { mode: 0o700 });
    const compile = spawnSync("circom", [
      "circuits/uav_witness_attestation_v2.circom",
      "--O2", "--r1cs", "--wasm", "-l", "node_modules", "-o", circuitDir,
    ], { cwd: ROOT, encoding: "utf8", timeout: 120000 });
    assert.equal(compile.status, 0, `${compile.stdout}\n${compile.stderr}`);
    const wasmDir = path.join(circuitDir, "uav_witness_attestation_v2_js");
    const witnessFile = path.join(tempDir, "phone.wtns");
    const calculate = spawnSync(process.execPath, [
      path.join(wasmDir, "generate_witness.js"),
      path.join(wasmDir, "uav_witness_attestation_v2.wasm"),
      witnessPath,
      witnessFile,
    ], { cwd: ROOT, encoding: "utf8", timeout: 120000 });
    assert.equal(calculate.status, 0, `${calculate.stdout}\n${calculate.stderr}`);
    assert.ok(fs.statSync(witnessFile).size > 0);
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});
