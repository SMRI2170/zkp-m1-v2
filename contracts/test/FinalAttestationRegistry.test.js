const { expect } = require("chai");
const { ethers } = require("hardhat");

// AggCircuit / IAggregateVerifier と同じ公開値の順序。
const input = ({ drone = 424242n, bucket = 100001n, consistent = 2n, suspicious = 1n, root = 999n } = {}) => [
  drone, bucket, consistent, suspicious, root,
];
const proof = "0x123456";

describe("FinalAttestationRegistry (M2 final record)", function () {
  let registry, verifier;

  beforeEach(async function () {
    verifier = await (await ethers.getContractFactory("MockAggregateVerifier")).deploy();
    registry = await (
      await ethers.getContractFactory("FinalAttestationRegistry")
    ).deploy(await verifier.getAddress(), 2);
    await registry.setDeviceRoot(999n);
  });

  it("集約 proof を検証し、意味のある最終レコードと Finalized event を残す", async function () {
    const values = input();
    const sessionId = await registry.sessionIdOf(values[0], values[1]);
    const proofHash = ethers.keccak256(proof);

    await expect(registry.submitFinal(proof, values))
      .to.emit(registry, "Finalized")
      .withArgs(sessionId, values[0], values[1], 1n, 2n, 1n, 999n, proofHash);

    const saved = await registry.finalAttestationOf(values[0], values[1]);
    expect(saved.verdict).to.equal(1n); // Trusted
    expect(saved.consistentCount).to.equal(2n);
    expect(saved.suspiciousCount).to.equal(1n);
    expect(saved.memberRoot).to.equal(999n);
    expect(saved.proofHash).to.equal(proofHash);
    expect(await registry.proofUsed(proofHash)).to.equal(true);
  });

  it("閾値未満なら Undetermined として残す", async function () {
    const values = input({ consistent: 1n, suspicious: 1n });
    await registry.submitFinal(proof, values);
    const saved = await registry.finalAttestationOf(values[0], values[1]);
    expect(saved.verdict).to.equal(0n);
  });

  it("登録端末 Root が現在の Root と違えば、検証前に拒否する", async function () {
    await expect(registry.submitFinal(proof, input({ root: 1000n }))).to.be.revertedWith(
      "member root mismatch"
    );
  });

  it("同じセッションの再確定と、同じ proof の別セッションへの付け替えを拒否する", async function () {
    await registry.submitFinal(proof, input());
    await expect(registry.submitFinal("0xabcd", input())).to.be.revertedWith("session already finalized");
    await expect(
      registry.submitFinal(proof, input({ drone: 999999n, bucket: 100002n }))
    ).to.be.revertedWith("proof already used");
  });

  it("整合と矛盾がどちらも閾値以上の、意味の衝突する結果を拒否する", async function () {
    await expect(registry.submitFinal(proof, input({ consistent: 2n, suspicious: 2n }))).to.be.revertedWith(
      "conflicting verdict"
    );
  });

  it("無効な集約 proof は最終レコードにできない", async function () {
    await verifier.setResult(false);
    await expect(registry.submitFinal(proof, input())).to.be.revertedWith("invalid aggregate proof");
  });
});
