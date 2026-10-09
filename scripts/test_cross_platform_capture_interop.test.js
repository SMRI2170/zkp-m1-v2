"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");
const { buildPoseidon } = require("circomlibjs");

const ROOT = path.join(__dirname, "..");
const APP = path.join(ROOT, "rapidsnark_app");
const SESSION_KEY = Buffer.alloc(32, 0x11);
const DISPOSABLE_PTAU_POWER = 13;
// These keys match only the checked-in synthetic three-member test roster.
// They are not enrolled credentials and must never be used for field runs.
const OBSERVER_KEYS = [1, 2, 3].map((byte) => Buffer.alloc(32, byte));
const DOMAIN_RID_V2 = 0x5349474e414c5f5249445f5632n;

function run(command, args, options = {}) {
  const { includeStderr = false, ...spawnOptions } = options;
  const result = spawnSync(command, args, {
    cwd: ROOT,
    encoding: "utf8",
    timeout: 180000,
    ...spawnOptions,
  });
  assert.equal(result.status, 0,
    `${command} ${args.join(" ")} failed (${result.error?.message || result.signal || "no exit status"})\n` +
    `${result.stdout || ""}\n${result.stderr || ""}`);
  return includeStderr ? `${result.stdout || ""}\n${result.stderr || ""}` : result.stdout;
}

function runFailure(command, args, expectedError, options = {}) {
  const result = spawnSync(command, args, {
    cwd: ROOT,
    encoding: "utf8",
    timeout: 180000,
    ...options,
  });
  assert.notEqual(result.status, 0,
    `${command} ${args.join(" ")} unexpectedly succeeded\n${result.stdout || ""}`);
  assert.match(`${result.stdout || ""}\n${result.stderr || ""}`, expectedError);
}

function assertPowersOfTauCapacity(circomOutput, power) {
  const nonlinear = circomOutput.match(/^non-linear constraints: ([0-9]+)\s*$/m);
  const linear = circomOutput.match(/^linear constraints: ([0-9]+)\s*$/m);
  assert.ok(nonlinear && linear, "Circom output must include linear and non-linear constraint counts");
  const constraints = Number(nonlinear[1]) + Number(linear[1]);
  assert.ok(Number.isSafeInteger(constraints) && constraints > 0, "Circom constraint count must be a positive safe integer");
  const capacity = 2 ** power;
  assert.ok(
    Number.isSafeInteger(power) && power > 0 && constraints <= capacity,
    `current circuit needs ${constraints} constraints; disposable Powers-of-Tau power ${power} supports ${capacity}`,
  );
  return constraints;
}

test("checks disposable Powers-of-Tau capacity before starting ceremony work", () => {
  assert.equal(assertPowersOfTauCapacity(
    "non-linear constraints: 6201\nlinear constraints: 0\n",
    DISPOSABLE_PTAU_POWER,
  ), 6201);
  assert.throws(
    () => assertPowersOfTauCapacity("non-linear constraints: 8193\nlinear constraints: 0\n", DISPOSABLE_PTAU_POWER),
    /needs 8193 constraints.*supports 8192/,
  );
  assert.throws(
    () => assertPowersOfTauCapacity("compiler output changed\n", DISPOSABLE_PTAU_POWER),
    /must include linear and non-linear constraint counts/,
  );
});

function lastJsonLine(stdout) {
  const lines = stdout.trim().split(/\r?\n/).filter(Boolean);
  return JSON.parse(lines.at(-1));
}

function writeCalibrationReport(filePath, observerId, profileId) {
  fs.writeFileSync(filePath, JSON.stringify({
    schema: "signal.rssi-evaluation.v1",
    decision_policy: { consistency_tolerance_ratio: 0.9 },
    calibration_models: [{
      observer_id: observerId,
      calibration_profile_id: profileId,
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
  }) + "\n", { flag: "wx", mode: 0o600 });
}

function pcd3PlanArgs(verificationKey, proofDir, artifactDir) {
  return [
    "run", "./cmd/pcd3",
    "--protocol=v2",
    "--stage=plan",
    `--leaf-vk=${verificationKey}`,
    `--proof-dir=${proofDir}`,
    `--roster=${path.join(ROOT, "aggregator/pcd/testdata/observer-roster-v1.json")}`,
    "--allow-manifest-root-for-test",
    "--calibration-profile-ids=1,2,7",
    "--quorum=2",
    `--artifacts=${artifactDir}`,
  ];
}

function copyProofSet(sourceDir, destinationDir) {
  fs.mkdirSync(destinationDir, { mode: 0o700 });
  for (let index = 0; index < 3; index++) {
    for (const suffix of ["proof", "public"]) {
      const name = `input_dev${index}_${suffix}.json`;
      fs.copyFileSync(path.join(sourceDir, name), path.join(destinationDir, name));
    }
  }
}

function convertCapture({ source, fixture, secret, tempDir }) {
  const secretPath = path.join(tempDir, `${source}-observer.key`);
  const calibrationPath = path.join(tempDir, `${source}-calibration.json`);
  const witnessPath = path.join(tempDir, `${source}-input.json`);
  const provenancePath = path.join(tempDir, `${source}-provenance.json`);
  fs.chmodSync(fixture.capture_path, 0o600);
  fs.writeFileSync(secretPath, secret, { flag: "wx", mode: 0o600 });
  writeCalibrationReport(calibrationPath, fixture.observer_id, fixture.calibration_profile_id);
  run(process.execPath, [
    path.join(ROOT, "scripts/capture_to_witness_v2.js"),
    "--capture", fixture.capture_path,
    "--event-seq", String(fixture.event_seq),
    "--window-start-unix-ms", String(fixture.window_start_unix_ms),
    "--window-end-unix-ms", String(fixture.window_end_unix_ms),
    "--session-key-file", fixture.session_key_path,
    "--observer-key-file", secretPath,
    "--calibration-report", calibrationPath,
    "--output", witnessPath,
    "--provenance-output", provenancePath,
  ]);
  return {
    witness: JSON.parse(fs.readFileSync(witnessPath, "utf8")),
    provenance: JSON.parse(fs.readFileSync(provenancePath, "utf8")),
    witnessPath,
  };
}

test("Flutter and Pi captures produce verified V2 leaf proofs accepted by multi-observer preflight", async () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "cross-platform-capture-"));
  fs.chmodSync(tempDir, 0o700);
  try {
    const phoneDir = path.join(tempDir, "phone");
    const piDirs = [path.join(tempDir, "pi-1"), path.join(tempDir, "pi-2")];
    fs.mkdirSync(phoneDir, { mode: 0o700 });
    for (const piDir of piDirs) fs.mkdirSync(piDir, { mode: 0o700 });

    const dart = process.env.DART_BIN || "dart";
    const phoneFixture = lastJsonLine(run(dart, [
      "run", "tool/generate_v2_observer_capture_fixture.dart", phoneDir,
    ], { cwd: APP }));
    const piFixtures = [
      lastJsonLine(run(process.env.PYTHON_BIN || "python3", [
        path.join(ROOT, "uav/generate_v2_pi_capture_fixture.py"),
        piDirs[0],
        String(phoneFixture.window_start_unix_ms + 5000),
        "--observer-id", "pi-interop-01",
        "--profile-id", "2",
        "--observer-lon", "139.00005",
      ])),
      lastJsonLine(run(process.env.PYTHON_BIN || "python3", [
        path.join(ROOT, "uav/generate_v2_pi_capture_fixture.py"),
        piDirs[1],
        String(phoneFixture.window_start_unix_ms + 5000),
        "--observer-id", "pi-interop-02",
        "--profile-id", "1",
        "--observer-lon", "139.00008",
      ])),
    ];
    for (const piFixture of piFixtures) {
      assert.equal(piFixture.run_id, phoneFixture.run_id);
      assert.equal(piFixture.window_start_unix_ms, phoneFixture.window_start_unix_ms);
      assert.equal(piFixture.window_end_unix_ms, phoneFixture.window_end_unix_ms);
      assert.deepEqual(fs.readFileSync(piFixture.session_key_path), SESSION_KEY);
    }

    const fixtures = [phoneFixture, ...piFixtures];
    const sessions = fixtures.map((fixture, index) => convertCapture({
      source: `observer-${index}`,
      fixture: { ...fixture, session_key_path: piFixtures[0].session_key_path },
      secret: OBSERVER_KEYS[index],
      tempDir,
    }));
    const [phone, piNear, piFar] = sessions;

    assert.deepEqual(sessions.map((item) => item.provenance.observer_id), [
      "phone-interop-01", "pi-interop-01", "pi-interop-02",
    ]);
    assert.deepEqual(sessions.map((item) => item.provenance.calibration_profile_id), [7, 2, 1]);
    assert.equal(new Set(sessions.map((item) => item.provenance.observer_pubkey_x)).size, 3);
    assert.notEqual(phone.witness.target_lon_e7_norm, piNear.witness.target_lon_e7_norm);
    assert.notEqual(piNear.witness.target_lon_e7_norm, piFar.witness.target_lon_e7_norm);
    for (const item of sessions) {
      assert.equal(item.provenance.run_id, phone.provenance.run_id);
      assert.equal(item.witness.remote_id, phone.witness.remote_id);
      assert.equal(item.witness.session_salt, phone.witness.session_salt);
      assert.equal(
        BigInt(item.witness.target_time_sec) / 60n,
        BigInt(phone.witness.target_time_sec) / 60n,
      );
    }

    const poseidon = await buildPoseidon();
    const F = poseidon.F;
    const commitment = (witness) => F.toObject(poseidon([
      DOMAIN_RID_V2,
      BigInt(witness.remote_id),
      BigInt(witness.session_salt),
      BigInt(witness.target_time_sec) / 60n,
    ])).toString();
    assert.equal(new Set(sessions.map((item) => commitment(item.witness))).size, 1);

    const circuitDir = path.join(tempDir, "circuit");
    fs.mkdirSync(circuitDir, { mode: 0o700 });
    const circomOutput = run("circom", [
      "circuits/uav_witness_attestation_v2.circom",
      "--O2", "--r1cs", "--wasm", "-l", "node_modules", "-o", circuitDir,
    ], { includeStderr: true });
    const currentConstraintCount = assertPowersOfTauCapacity(circomOutput, DISPOSABLE_PTAU_POWER);
    assert.ok(currentConstraintCount <= 2 ** DISPOSABLE_PTAU_POWER);
    const wasmDir = path.join(circuitDir, "uav_witness_attestation_v2_js");
    const r1csPath = path.join(circuitDir, "uav_witness_attestation_v2.r1cs");
    const witnesses = [];
    for (const [index, result] of sessions.entries()) {
      const source = `observer-${index}`;
      const witnessFile = path.join(tempDir, `${source}.wtns`);
      run(process.execPath, [
        path.join(wasmDir, "generate_witness.js"),
        path.join(wasmDir, "uav_witness_attestation_v2.wasm"),
        result.witnessPath,
        witnessFile,
      ]);
      run(process.env.SNARKJS_BIN || "snarkjs", ["wtns", "check", r1csPath, witnessFile]);
      witnesses.push(witnessFile);
    }

    // Disposable one-contributor ceremony, strictly test-only. The generated
    // zkey/VK is never a release trust root.
    const snarkjs = process.env.SNARKJS_BIN || "snarkjs";
    const ptau0 = path.join(tempDir, "pot0.ptau");
    const ptau1 = path.join(tempDir, "pot1.ptau");
    const ptauFinal = path.join(tempDir, "pot-final.ptau");
    const zkey = path.join(tempDir, "test-only.zkey");
    const verificationKey = path.join(tempDir, "verification_key.json");
    // Capacity was checked against Circom's compiled constraint counts above,
    // before this disposable ceremony does any phase2 work.
    run(snarkjs, ["powersoftau", "new", "bn128", String(DISPOSABLE_PTAU_POWER), ptau0]);
    run(snarkjs, [
      "powersoftau", "contribute", ptau0, ptau1,
      "--name=cross-platform observer test only",
      `-e=${crypto.randomBytes(64).toString("hex")}`,
    ]);
    run(snarkjs, ["powersoftau", "prepare", "phase2", ptau1, ptauFinal]);
    run(snarkjs, ["powersoftau", "verify", ptauFinal]);
    run(snarkjs, ["groth16", "setup", r1csPath, ptauFinal, zkey]);
    run(snarkjs, ["zkey", "verify", r1csPath, ptauFinal, zkey]);
    run(snarkjs, ["zkey", "export", "verificationkey", zkey, verificationKey]);

    const proofDir = path.join(tempDir, "leaf-proofs");
    fs.mkdirSync(proofDir, { mode: 0o700 });
    for (const [index, witnessFile] of witnesses.entries()) {
      const proofPath = path.join(proofDir, `input_dev${index}_proof.json`);
      const publicPath = path.join(proofDir, `input_dev${index}_public.json`);
      run(snarkjs, ["groth16", "prove", zkey, witnessFile, proofPath, publicPath]);
      run(snarkjs, ["groth16", "verify", verificationKey, publicPath, proofPath]);
    }

    const artifactDir = path.join(tempDir, "pcd3-artifacts");
    const pcd3Args = (inputDir) => pcd3PlanArgs(verificationKey, inputDir, artifactDir);
    const pcd3Options = { cwd: path.join(ROOT, "aggregator") };
    const plan = run("go", pcd3Args(proofDir), pcd3Options);
    assert.match(plan, /Verified V2 leaf proofs: 3; distinct registered observers: 3/);
    assert.match(plan, /Counts: consistent=1 suspicious=2 decision=POSITION_INCONSISTENCY_SUSPECTED/);
    assert.match(plan, /Approved calibration profile IDs: 1,2,7/);
    assert.match(plan, /Plan only: no circuit compile, Groth16 setup, or proof was performed\./);

    const duplicateDir = path.join(tempDir, "duplicate-observer-proofs");
    copyProofSet(proofDir, duplicateDir);
    fs.copyFileSync(
      path.join(duplicateDir, "input_dev1_proof.json"),
      path.join(duplicateDir, "input_dev2_proof.json"),
    );
    fs.copyFileSync(
      path.join(duplicateDir, "input_dev1_public.json"),
      path.join(duplicateDir, "input_dev2_public.json"),
    );
    runFailure("go", pcd3Args(duplicateDir), /observer registry index .* is used more than once/, pcd3Options);

    const tamperedDir = path.join(tempDir, "tampered-public-signal-proofs");
    copyProofSet(proofDir, tamperedDir);
    const tamperedPublicPath = path.join(tamperedDir, "input_dev2_public.json");
    const tamperedSignals = JSON.parse(fs.readFileSync(tamperedPublicPath, "utf8"));
    tamperedSignals[5] = tamperedSignals[5] === "0" ? "1" : "0";
    fs.writeFileSync(tamperedPublicPath, `${JSON.stringify(tamperedSignals)}\n`, { mode: 0o600 });
    runFailure("go", pcd3Args(tamperedDir), /V2 leaf proof verification failed/, pcd3Options);

    const otherRunDir = path.join(tempDir, "other-run");
    fs.mkdirSync(otherRunDir, { mode: 0o700 });
    const otherRunFixture = lastJsonLine(run(process.env.PYTHON_BIN || "python3", [
      path.join(ROOT, "uav/generate_v2_pi_capture_fixture.py"),
      otherRunDir,
      String(phoneFixture.window_start_unix_ms + 5000),
      "--observer-id", "pi-interop-02",
      "--profile-id", "1",
      "--observer-lon", "139.00008",
      "--run-id", "phone-interop-run-02",
    ]));
    const otherRun = convertCapture({
      source: "other-run-observer",
      fixture: otherRunFixture,
      secret: OBSERVER_KEYS[2],
      tempDir,
    });
    assert.notEqual(otherRun.witness.session_salt, phone.witness.session_salt);
    assert.equal(BigInt(otherRun.witness.target_time_sec) / 60n,
      BigInt(phone.witness.target_time_sec) / 60n);
    const otherRunWitness = path.join(tempDir, "other-run-observer.wtns");
    run(process.execPath, [
      path.join(wasmDir, "generate_witness.js"),
      path.join(wasmDir, "uav_witness_attestation_v2.wasm"),
      otherRun.witnessPath,
      otherRunWitness,
    ]);
    run(snarkjs, ["wtns", "check", r1csPath, otherRunWitness]);
    const otherRunProof = path.join(tempDir, "other-run-proof.json");
    const otherRunPublic = path.join(tempDir, "other-run-public.json");
    run(snarkjs, ["groth16", "prove", zkey, otherRunWitness, otherRunProof, otherRunPublic]);
    run(snarkjs, ["groth16", "verify", verificationKey, otherRunPublic, otherRunProof]);

    const mixedRunDir = path.join(tempDir, "mixed-session-proofs");
    copyProofSet(proofDir, mixedRunDir);
    fs.copyFileSync(otherRunProof, path.join(mixedRunDir, "input_dev2_proof.json"));
    fs.copyFileSync(otherRunPublic, path.join(mixedRunDir, "input_dev2_public.json"));
    runFailure("go", pcd3Args(mixedRunDir), /different session-scoped RID commitment or time bucket/, pcd3Options);
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});
