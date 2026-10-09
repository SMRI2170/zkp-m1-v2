// Test-only EVM check for a V2 leaf proof and tampered public signals.
// Uses a temporary verifier source/key supplied through environment variables;
// it does not modify the project's pinned V1 verifier or registry.
const fs = require("fs");
const path = require("path");
const solc = require("solc");
const { ethers } = require("hardhat");

function requireEnv(name) {
  const value = process.env[name];
  if (!value) throw new Error(`set ${name} to a temporary V2 test artifact path`);
  return path.resolve(value);
}

function compileVerifier(sourcePath) {
  const sourceName = path.basename(sourcePath);
  const input = {
    language: "Solidity",
    sources: { [sourceName]: { content: fs.readFileSync(sourcePath, "utf8") } },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: { "*": { "*": ["abi", "evm.bytecode.object"] } },
    },
  };
  const output = JSON.parse(solc.compile(JSON.stringify(input)));
  const errors = (output.errors || []).filter((error) => error.severity === "error");
  if (errors.length) throw new Error(errors.map((error) => error.formattedMessage).join("\n"));
  const candidates = Object.values(output.contracts?.[sourceName] || {});
  if (candidates.length !== 1) throw new Error(`expected one generated verifier contract, got ${candidates.length}`);
  return candidates[0];
}

function proofCallData(proof, publicSignals) {
  if (!Array.isArray(publicSignals) || publicSignals.length !== 8) {
    throw new Error(`V2 proof must expose 8 public signals; received ${publicSignals?.length}`);
  }
  return {
    a: [proof.pi_a[0], proof.pi_a[1]],
    b: [
      [proof.pi_b[0][1], proof.pi_b[0][0]],
      [proof.pi_b[1][1], proof.pi_b[1][0]],
    ],
    c: [proof.pi_c[0], proof.pi_c[1]],
    input: publicSignals,
  };
}

async function main() {
  const verifierSourcePath = requireEnv("LEAF_V2_VERIFIER_SOURCE");
  const proofPath = requireEnv("LEAF_V2_PROOF");
  const publicPath = requireEnv("LEAF_V2_PUBLIC");
  const proof = JSON.parse(fs.readFileSync(proofPath, "utf8"));
  const publicSignals = JSON.parse(fs.readFileSync(publicPath, "utf8"));
  const call = proofCallData(proof, publicSignals);
  const artifact = compileVerifier(verifierSourcePath);
  const [signer] = await ethers.getSigners();
  const factory = new ethers.ContractFactory(artifact.abi, `0x${artifact.evm.bytecode.object}`, signer);
  const verifier = await factory.deploy();
  await verifier.waitForDeployment();

  if (!(await verifier.verifyProof(call.a, call.b, call.c, call.input))) {
    throw new Error("V2 Groth16 proof was rejected by the generated EVM verifier");
  }
  const tamperCases = [
    [1, (BigInt(call.input[1]) + 1n).toString(), "session-scoped RID commitment"],
    [4, (BigInt(call.input[4]) + 1n).toString(), "time bucket"],
    [5, call.input[5] === "0" ? "1" : "0", "consistency outcome"],
    [6, (BigInt(call.input[6]) + 1n).toString(), "signed freshness timestamp"],
    [7, (BigInt(call.input[7]) + 1n).toString(), "calibration profile"],
  ];
  for (const [index, value, label] of tamperCases) {
    const tampered = [...call.input];
    tampered[index] = value;
    if (await verifier.verifyProof(call.a, call.b, call.c, tampered)) {
      throw new Error(`EVM verifier accepted a changed V2 ${label}`);
    }
  }
  console.log("V2 test proof accepted by generated EVM verifier");
  console.log("Tampered RID commitment, time bucket, consistency, freshness, and profile rejected");
  console.log("Test-only local setup; this verifier is not a release-pinned contract.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
