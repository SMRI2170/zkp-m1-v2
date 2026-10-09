// Verify a pcd3 FinalBN artifact against its generated verifier and finalize it
// through FinalAttestationRegistryV1 on a local Hardhat EVM.
//
// Usage from the repository root:
// cd contracts
// PCD3_FINAL_ARTIFACT=/absolute/path/final-proof-v1.json npx hardhat run scripts/verify_pcd3_final_evm.js --network hardhat
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const solc = require("solc");
const { ethers } = require("hardhat");
const { compileVerifier } = require("./generated_verifier_compiler");

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function main() {
  const artifactPath = process.env.PCD3_FINAL_ARTIFACT;
  assert(artifactPath, "set PCD3_FINAL_ARTIFACT to a pcd3 final-proof-v1.json path");
  const artifactFile = path.resolve(artifactPath);
  const artifact = JSON.parse(fs.readFileSync(artifactFile, "utf8"));
  assert(artifact.protocolVersion === 1, "artifact protocolVersion must be 1");
  assert(Number.isInteger(artifact.minimumQuorum) && artifact.minimumQuorum > 0, "artifact minimumQuorum is invalid");
  assert(typeof artifact.proof === "string" && /^0x(?:[0-9a-fA-F]{2})+$/.test(artifact.proof), "artifact proof must be nonempty hex bytes");
  assert(Array.isArray(artifact.publicInputs) && artifact.publicInputs.length === 9, "artifact must contain nine public inputs");
  const publicInputs = artifact.publicInputs.map((value, index) => {
    assert(typeof value === "string" && /^(0|[1-9][0-9]*)$/.test(value), `publicInputs[${index}] must be a canonical decimal string`);
    return BigInt(value);
  });
  const verifierSourcePath = path.resolve(path.dirname(artifactFile), artifact.verifierSource);
  const verifierSource = fs.readFileSync(verifierSourcePath, "utf8");
  const verifierHash = crypto.createHash("sha256").update(verifierSource).digest("hex");
  assert(verifierHash === artifact.verifierSha256, "generated verifier source SHA-256 does not match the proof artifact");

  const compiled = compileVerifier(verifierSource);
  const [owner] = await ethers.getSigners();
  const verifier = await new ethers.ContractFactory(compiled.abi, `0x${compiled.evm.bytecode.object}`, owner).deploy();
  await verifier.waitForDeployment();

  // The generated VK, not a mock, must accept the proof. A changed public input
  // must be rejected before the registry write is attempted.
  await verifier.verifyProof.staticCall(artifact.proof, publicInputs);
  const tamperedInputs = [...publicInputs];
  tamperedInputs[5] += 1n;
  let tamperedRejected = false;
  try {
    await verifier.verifyProof.staticCall(artifact.proof, tamperedInputs);
  } catch {
    tamperedRejected = true;
  }
  assert(tamperedRejected, "generated verifier accepted a proof with an altered nullifierRoot");

  const verifierVersion = `0x${artifact.verifierSha256}`;
  const registry = await (
    await ethers.getContractFactory("FinalAttestationRegistryV1")
  ).deploy(await verifier.getAddress(), verifierVersion);
  await registry.waitForDeployment();
  await (await registry.setActiveMemberRoot(publicInputs[4])).wait();
  await (await registry.setPolicyApproval(publicInputs[3], true)).wait();
  const receipt = await (await registry.submitFinal(artifact.proof, publicInputs)).wait();
  const record = await registry.finalAttestationOf(publicInputs[1], publicInputs[2], publicInputs[3]);
  assert(record.protocolVersion === 1n, "registry did not save protocolVersion 1");
  assert(record.verdict === publicInputs[8], "registry verdict differs from proof public input");
  assert(record.timeBucket === publicInputs[2], "registry timeBucket differs from proof public input");
  assert(record.consistentCount === publicInputs[6], "registry consistentCount differs from proof public input");
  assert(record.suspiciousCount === publicInputs[7], "registry suspiciousCount differs from proof public input");
  assert(record.droneIdCommitment === publicInputs[1], "registry droneIdCommitment differs from proof public input");
  assert(record.policyCommitment === publicInputs[3], "registry policyCommitment differs from proof public input");
  assert(record.memberRoot === publicInputs[4], "registry memberRoot differs from proof public input");
  assert(record.nullifierRoot === publicInputs[5], "registry nullifierRoot differs from proof public input");
  assert(record.verifierVersion === verifierVersion, "registry verifierVersion differs from generated verifier hash");
  assert(record.proofHash === ethers.keccak256(artifact.proof), "registry proofHash differs from submitted proof");
  assert(await registry.proofUsed(record.proofHash), "registry did not mark the proof as used");

  console.log(`Solidity compiler: ${solc.version()}`);
  console.log(`FinalBN verifier: ${await verifier.getAddress()}`);
  console.log(`FinalAttestationRegistryV1: ${await registry.getAddress()}`);
  console.log(`Finalized transaction: ${receipt.hash}`);
  console.log("PASS: generated FinalBN proof verified on EVM and was finalized by the v1 registry.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
