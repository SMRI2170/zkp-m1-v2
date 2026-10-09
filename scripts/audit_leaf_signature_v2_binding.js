#!/usr/bin/env node
/*
 * Check V2 witness-generation behavior: the original signed range is accepted,
 * while changing only measured_range_cm is rejected by EdDSA constraints.
 *
 * Usage: node scripts/audit_leaf_signature_v2_binding.js <wasm> <input.json> <far-mismatch-input.json>
 */
const assert = require("assert");
const { execFileSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

function main() {
  const wasmPath = process.argv[2] && path.resolve(process.argv[2]);
  const inputPath = process.argv[3] && path.resolve(process.argv[3]);
  const farMismatchInputPath = process.argv[4] && path.resolve(process.argv[4]);
  if (!wasmPath || !inputPath || !farMismatchInputPath) {
    throw new Error("usage: node scripts/audit_leaf_signature_v2_binding.js <wasm> <input.json> <far-mismatch-input.json>");
  }
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "uav-witness-v2-binding-"));
  const source = JSON.parse(fs.readFileSync(inputPath, "utf8"));
  const originalRange = BigInt(source.measured_range_cm);
  const changedRange = originalRange === 5000n ? 341n : originalRange + 1000n;
  const validWitnessPath = path.join(tmp, "valid.wtns");
  const farMismatchWitnessPath = path.join(tmp, "far-mismatch.wtns");
  const farMismatchWitnessJsonPath = path.join(tmp, "far-mismatch-witness.json");
  const generateWitness = path.join(path.dirname(wasmPath), "generate_witness.js");
  execFileSync(process.execPath, [generateWitness, wasmPath, inputPath, validWitnessPath], { stdio: "pipe" });
  execFileSync(process.execPath, [generateWitness, wasmPath, farMismatchInputPath, farMismatchWitnessPath], { stdio: "pipe" });
  const snarkjs = process.env.SNARKJS || "snarkjs";
  execFileSync(snarkjs, ["wtns", "export", "json", farMismatchWitnessPath, farMismatchWitnessJsonPath], { stdio: "pipe" });
  const farMismatchWitness = JSON.parse(fs.readFileSync(farMismatchWitnessJsonPath, "utf8"));
  // main.observation_eligible is output 0 (witness index 1); main.consistency_ok
  // is output 5 (witness index 6). Large position error must be accepted and counted.
  assert.strictEqual(BigInt(farMismatchWitness[1]), 1n, "far mismatch must remain observation-eligible");
  assert.strictEqual(BigInt(farMismatchWitness[6]), 0n, "far mismatch must be classified suspicious");

  const rejectTampering = (name, changes) => {
    const tamperedPath = path.join(tmp, `${name}.json`);
    const witnessPath = path.join(tmp, `${name}.wtns`);
    fs.writeFileSync(tamperedPath, `${JSON.stringify({ ...source, ...changes }, null, 2)}\n`);
    try {
      execFileSync(process.execPath, [generateWitness, wasmPath, tamperedPath, witnessPath], { stdio: "pipe" });
    } catch (error) {
      const failure = `${error.stdout || ""}\n${error.stderr || ""}\n${error.message || ""}`;
      if (!failure.includes("Assert Failed") || !failure.includes("EdDSAPoseidonVerifier")) {
        throw new Error(`tampering failed for a reason other than the signature constraint: ${failure}`);
      }
      return;
    }
    throw new Error(`V2 accepted tampering: ${name}`);
  };

  const rejectCircuitConstraintTampering = (name, changes) => {
    const tamperedPath = path.join(tmp, `${name}.json`);
    const witnessPath = path.join(tmp, `${name}.wtns`);
    fs.writeFileSync(tamperedPath, `${JSON.stringify({ ...source, ...changes }, null, 2)}\n`);
    try {
      execFileSync(process.execPath, [generateWitness, wasmPath, tamperedPath, witnessPath], { stdio: "pipe" });
    } catch (error) {
      const failure = `${error.stdout || ""}\n${error.stderr || ""}\n${error.message || ""}`;
      if (!failure.includes("Assert Failed")) {
        throw new Error(`freshness tampering failed for an unexpected reason: ${failure}`);
      }
      return;
    }
    throw new Error(`V2 accepted tampering: ${name}`);
  };

  rejectTampering("changed-range", { measured_range_cm: changedRange.toString() });
  rejectTampering("changed-profile", {
    calibration_profile_id: (BigInt(source.calibration_profile_id) + 1n).toString(),
  });
  rejectCircuitConstraintTampering("changed-freshness", {
    freshness: (BigInt(source.freshness) + 1n).toString(),
  });
  if (!fs.existsSync(validWitnessPath)) {
    throw new Error("V2 did not generate the valid baseline witness");
  }
  assert(fs.statSync(validWitnessPath).size > 0, "V2 baseline witness is empty");
  console.log(`V2 valid signed range ${originalRange} cm: accepted`);
  console.log(`V2 changed range ${changedRange} cm with old signature: rejected`);
  console.log("V2 changed calibration profile with old signature: rejected");
  console.log("V2 freshness timestamp not matching target_time_sec: rejected");
  console.log("V2 far-position mismatch: accepted as observation_eligible=1, consistency_ok=0");
  console.log("This tests signed-input binding, not RSSI sensor truth or a Groth16 ceremony/VK.");
}

try {
  main();
} catch (error) {
  console.error(error);
  process.exitCode = 1;
}
