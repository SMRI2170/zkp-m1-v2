const { expect } = require("chai");
const { ethers } = require("hardhat");

const proof = "0x123456";
const verifierVersion = ethers.id("final-attestation-v2/test-verifier/1");
let freshTimeBucket = 0n;
const input = ({
  version = 2n,
  drone = 424242n,
  bucket = freshTimeBucket,
  policy = 123456789n,
  profileSetRoot = 17n,
  memberRoot = 999n,
  nullifierRoot = 777n,
  consistent = 2n,
  suspicious = 1n,
  verdict = 1n,
} = {}) => [version, drone, bucket, policy, profileSetRoot, memberRoot, nullifierRoot, consistent, suspicious, verdict];

describe("FinalAttestationRegistryV2", function () {
  let registry, verifier;

  beforeEach(async function () {
    verifier = await (await ethers.getContractFactory("MockFinalAttestationVerifierV2")).deploy();
    registry = await (
      await ethers.getContractFactory("FinalAttestationRegistryV2")
    ).deploy(await verifier.getAddress(), verifierVersion);
    await registry.setActiveMemberRoot(999n);
    await registry.setPolicyApproval(123456789n, true);
    const latest = await ethers.provider.getBlock("latest");
    freshTimeBucket = BigInt(Math.floor(Number(latest.timestamp) / 60));
  });

  it("10入力のV2 proofを検証し、profile-set rootと限定的な結果コードを保存する", async function () {
    const values = input();
    const sessionId = await registry.sessionIdOf(values[1], values[2]);
    const proofHash = ethers.keccak256(proof);

    await expect(registry.submitFinal(proof, values))
      .to.emit(registry, "Finalized")
      .withArgs(sessionId, 424242n, freshTimeBucket, 123456789n, 17n, 999n, 777n, 1n, 2n, 1n, verifierVersion, proofHash);

    const saved = await registry.finalAttestationOf(values[1], values[2]);
    expect(saved.protocolVersion).to.equal(2n);
    expect(saved.calibrationProfileSetRoot).to.equal(17n);
    expect(saved.verdict).to.equal(1n); // NoInconsistencyObserved; not aircraft authenticity/safety.
    expect(saved.nullifierRoot).to.equal(777n);
    expect(saved.verifierVersion).to.equal(verifierVersion);
    expect(saved.proofHash).to.equal(proofHash);
  });

  it("version、canonical profile-set root、policy、member root、empty batchを検査する", async function () {
    await expect(registry.submitFinal(proof, input({ version: 1n }))).to.be.revertedWith("invalid v2 public inputs");
    await expect(registry.submitFinal(proof, input({ profileSetRoot: 21888242871839275222246405745257275088548364400416034343698204186575808495617n })))
      .to.be.revertedWith("invalid v2 public inputs");
    await expect(registry.submitFinal(proof, input({ policy: 12n }))).to.be.revertedWith("policy not approved");
    await expect(registry.submitFinal(proof, input({ memberRoot: 12n }))).to.be.revertedWith("member root mismatch");
    await expect(registry.submitFinal(proof, input({ consistent: 0n, suspicious: 0n, verdict: 0n })))
      .to.be.revertedWith("empty aggregate");
  });

  it("uint32を超える正準profile-set rootをそのまま保存する", async function () {
    const profileSetRoot = (1n << 32n) + 17n;
    const values = input({ profileSetRoot });
    await registry.submitFinal(proof, values);
    const saved = await registry.finalAttestationOf(values[1], values[2]);
    expect(saved.calibrationProfileSetRoot).to.equal(profileSetRoot);
  });

  it("stale/future time bucketsをlive registry窓で拒否する", async function () {
    await expect(registry.submitFinal(proof, input({ bucket: freshTimeBucket - 100n })))
      .to.be.revertedWith("stale session");
    await expect(registry.submitFinal(proof, input({ bucket: freshTimeBucket + 2n })))
      .to.be.revertedWith("session time too far future");
  });

  it("同一sessionとproofの再利用を拒否する", async function () {
    await registry.submitFinal(proof, input());
    await expect(registry.submitFinal("0xabcd", input())).to.be.revertedWith("session already finalized");
    await registry.setPolicyApproval(123456790n, true);
    await expect(registry.submitFinal(proof, input({ policy: 123456790n }))).to.be.revertedWith("session already finalized");
    await expect(registry.submitFinal(proof, input({ drone: 424243n }))).to.be.revertedWith("proof already used");
  });

  it("verifierが拒否したproofを確定しない", async function () {
    await verifier.setResult(false);
    await expect(registry.submitFinal(proof, input())).to.be.revertedWith("invalid final proof");
    const saved = await registry.finalAttestationOf(424242n, 100001n);
    expect(saved.finalizedAt).to.equal(0n);
  });
});
