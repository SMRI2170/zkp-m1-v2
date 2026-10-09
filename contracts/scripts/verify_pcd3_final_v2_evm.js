// Verify a pcd3 FinalBNV2 artifact and finalize it in a local Hardhat EVM.
// Run from contracts with PCD3_V2_FINAL_ARTIFACT=/absolute/path/final-proof-v2.json.
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const solc = require("solc");
const { ethers } = require("hardhat");
const { compileVerifierV2 } = require("./generated_verifier_compiler");

const BN254_SCALAR_FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617n;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function requiredCanonicalFieldEnv(name) {
  const raw = process.env[name];
  assert(typeof raw === "string" && /^(0|[1-9][0-9]*)$/.test(raw), `set ${name} to a canonical decimal BN254 scalar`);
  const value = BigInt(raw);
  assert(value < BN254_SCALAR_FIELD, `${name} must be a canonical BN254 scalar`);
  return value;
}

function requiredUint32Env(name) {
  const raw = process.env[name];
  assert(typeof raw === "string" && /^[1-9][0-9]*$/.test(raw), `set ${name} to a canonical nonzero uint32`);
  const value = Number(raw);
  assert(Number.isSafeInteger(value) && value <= 0xffffffff, `${name} must be a nonzero uint32`);
  return value;
}

function requiredSha256Env(name) {
  const raw = process.env[name];
  assert(typeof raw === "string" && /^[0-9a-f]{64}$/.test(raw), `set ${name} to a lowercase SHA-256 digest`);
  return raw;
}

function parseCanonicalPublicInputs(rawInputs) {
  assert(Array.isArray(rawInputs) && rawInputs.length === 10, "artifact must contain ten public inputs");
  return rawInputs.map((value, index) => {
    assert(typeof value === "string" && /^(0|[1-9][0-9]*)$/.test(value),
      `publicInputs[${index}] must be a canonical decimal string`);
    const parsed = BigInt(value);
    assert(parsed < BN254_SCALAR_FIELD,
      `publicInputs[${index}] must be a canonical BN254 scalar`);
    return parsed;
  });
}

function validateArtifactMinimumQuorum(artifact, expectedMinimumQuorum) {
  assert(Number.isSafeInteger(artifact.minimumQuorum) && artifact.minimumQuorum > 0 && artifact.minimumQuorum <= 0xffffffff,
    "artifact minimumQuorum is invalid");
  assert(artifact.minimumQuorum === expectedMinimumQuorum,
    "artifact minimumQuorum differs from independently configured approved quorum");
}

function validateArtifactVerifierHash(artifactVerifierHash, expectedVerifierHash) {
  assert(typeof artifactVerifierHash === "string" && /^[0-9a-f]{64}$/.test(artifactVerifierHash),
    "artifact verifierSha256 is invalid");
  assert(artifactVerifierHash === expectedVerifierHash,
    "artifact verifier hash differs from independently approved verifier hash");
}

async function main() {
  const artifactPath = process.env.PCD3_V2_FINAL_ARTIFACT;
  assert(artifactPath, "set PCD3_V2_FINAL_ARTIFACT to a pcd3 final-proof-v2.json path");
  const artifactFile = path.resolve(artifactPath);
  const artifact = JSON.parse(fs.readFileSync(artifactFile, "utf8"));
  assert(artifact.protocolVersion === 2, "artifact protocolVersion must be 2");
  validateArtifactMinimumQuorum(artifact, requiredUint32Env("PCD3_V2_APPROVED_MINIMUM_QUORUM"));
  const expectedVerifierHash = requiredSha256Env("PCD3_V2_EXPECTED_VERIFIER_SHA256");
  validateArtifactVerifierHash(artifact.verifierSha256, expectedVerifierHash);
  assert(typeof artifact.proof === "string" && /^0x(?:[0-9a-fA-F]{2})+$/.test(artifact.proof), "artifact proof must be nonempty hex bytes");
  const publicInputs = parseCanonicalPublicInputs(artifact.publicInputs);
  const expectedMemberRoot = requiredCanonicalFieldEnv("PCD3_V2_ACTIVE_MEMBER_ROOT");
  const expectedPolicyCommitment = requiredCanonicalFieldEnv("PCD3_V2_APPROVED_POLICY_COMMITMENT");
  assert(publicInputs[0] === 2n, "public input protocolVersion must be 2");
  assert(publicInputs[3] === expectedPolicyCommitment, "proof policyCommitment differs from independently approved policy");
  assert(publicInputs[5] === expectedMemberRoot, "proof memberRoot differs from independently configured active registry root");
  const verifierSourcePath = path.resolve(path.dirname(artifactFile), artifact.verifierSource);
  const verifierSource = fs.readFileSync(verifierSourcePath, "utf8");
  const verifierHash = crypto.createHash("sha256").update(verifierSource).digest("hex");
  assert(verifierHash === expectedVerifierHash, "generated V2 verifier source SHA-256 does not match the independently approved verifier");

  const compiled = compileVerifierV2(verifierSource);
  const [owner] = await ethers.getSigners();
  const verifier = await new ethers.ContractFactory(compiled.abi, `0x${compiled.evm.bytecode.object}`, owner).deploy();
  await verifier.waitForDeployment();
  await verifier.verifyProof.staticCall(artifact.proof, publicInputs);

  for (let index = 0; index < publicInputs.length; index += 1) {
    const tampered = [...publicInputs];
    tampered[index] += 1n;
    let rejected = false;
    try {
      await verifier.verifyProof.staticCall(artifact.proof, tampered);
    } catch {
      rejected = true;
    }
    assert(rejected, `generated V2 verifier accepted tampered public input ${index}`);
  }

  const verifierVersion = `0x${artifact.verifierSha256}`;
  const registry = await (
    await ethers.getContractFactory("FinalAttestationRegistryV2")
  ).deploy(await verifier.getAddress(), verifierVersion);
  await registry.waitForDeployment();
  await (await registry.setActiveMemberRoot(expectedMemberRoot)).wait();
  await (await registry.setPolicyApproval(expectedPolicyCommitment, true)).wait();
  const receipt = await (await registry.submitFinal(artifact.proof, publicInputs)).wait();
  const record = await registry.finalAttestationOf(publicInputs[1], publicInputs[2]);
  assert(record.protocolVersion === 2n, "registry did not save protocolVersion 2");
  assert(record.calibrationProfileSetRoot === publicInputs[4], "registry profile-set root differs from proof public input");
  assert(record.verdict === publicInputs[9], "registry verdict differs from proof public input");
  assert(record.nullifierRoot === publicInputs[6], "registry nullifierRoot differs from proof public input");
  assert(record.proofHash === ethers.keccak256(artifact.proof), "registry proofHash differs from submitted proof");
  assert(await registry.proofUsed(record.proofHash), "registry did not mark the proof as used");

  let sessionReplayRejected = false;
  try {
    await registry.submitFinal.staticCall("0xabcd", publicInputs);
  } catch (error) {
    sessionReplayRejected = String(error).includes("session already finalized");
  }
  assert(sessionReplayRejected, "registry did not reject a second proof for the finalized session");

  const otherSession = [...publicInputs];
  otherSession[1] += 1n;
  let proofReplayRejected = false;
  try {
    await registry.submitFinal.staticCall(artifact.proof, otherSession);
  } catch (error) {
    proofReplayRejected = String(error).includes("proof already used");
  }
  assert(proofReplayRejected, "registry did not reject reuse of the same proof bytes");

  console.log(`Solidity compiler: ${solc.version()}`);
  console.log(`FinalBNV2 verifier: ${await verifier.getAddress()}`);
  console.log(`FinalAttestationRegistryV2: ${await registry.getAddress()}`);
  console.log(`Finalized transaction: ${receipt.hash}`);
  console.log("PASS: generated FinalBNV2 proof verified on EVM and was finalized by the V2 registry.");
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}

module.exports = {
  parseCanonicalPublicInputs,
  validateArtifactMinimumQuorum,
  validateArtifactVerifierHash,
};
