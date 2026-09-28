const { expect } = require("chai");
const { ethers } = require("hardhat");

const proof = "0x123456";
const verifierVersion = ethers.id("final-attestation-v1/test-verifier/1");
const input = ({
  version = 1n,
  drone = 424242n,
  bucket = 100001n,
  policy = 123456789n,
  memberRoot = 999n,
  nullifierRoot = 777n,
  consistent = 2n,
  suspicious = 1n,
  verdict = 1n,
} = {}) => [version, drone, bucket, policy, memberRoot, nullifierRoot, consistent, suspicious, verdict];

describe("FinalAttestationRegistryV1", function () {
  let registry, verifier;

  beforeEach(async function () {
    verifier = await (await ethers.getContractFactory("MockFinalAttestationVerifierV1")).deploy();
    registry = await (
      await ethers.getContractFactory("FinalAttestationRegistryV1")
    ).deploy(await verifier.getAddress(), verifierVersion);
    await registry.setActiveMemberRoot(999n);
    await registry.setPolicyApproval(123456789n, true);
  });

  it("v1 proofを検証し、versionedな最終recordを不変に保存する", async function () {
    const values = input();
    const sessionId = await registry.sessionIdOf(values[1], values[2], values[3]);
    const proofHash = ethers.keccak256(proof);

    await expect(registry.submitFinal(proof, values))
      .to.emit(registry, "Finalized")
      .withArgs(sessionId, 424242n, 100001n, 123456789n, 999n, 777n, 1n, 2n, 1n, verifierVersion, proofHash);

    const saved = await registry.finalAttestationOf(values[1], values[2], values[3]);
    expect(saved.protocolVersion).to.equal(1n);
    expect(saved.verdict).to.equal(1n);
    expect(saved.nullifierRoot).to.equal(777n);
    expect(saved.verifierVersion).to.equal(verifierVersion);
    expect(saved.proofHash).to.equal(proofHash);
  });

  it("policy、member root、入力versionが認可条件を満たさなければ拒否する", async function () {
    await expect(registry.submitFinal(proof, input({ policy: 12n }))).to.be.revertedWith("policy not approved");
    await expect(registry.submitFinal(proof, input({ memberRoot: 12n }))).to.be.revertedWith("member root mismatch");
    await expect(registry.submitFinal(proof, input({ version: 2n }))).to.be.revertedWith("invalid v1 public inputs");
  });

  it("同一sessionとproofの再利用を拒否し、policy違いは別sessionとして扱う", async function () {
    await registry.submitFinal(proof, input());
    await expect(registry.submitFinal("0xabcd", input())).to.be.revertedWith("session already finalized");
    await registry.setPolicyApproval(123456790n, true);
    await expect(registry.submitFinal(proof, input({ policy: 123456790n }))).to.be.revertedWith("proof already used");
  });

  it("verifierが拒否したproofは確定recordにならない", async function () {
    await verifier.setResult(false);
    await expect(registry.submitFinal(proof, input())).to.be.revertedWith("invalid final proof");
  });
});
