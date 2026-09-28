const { expect } = require("chai");
const { ethers } = require("hardhat");
const vectors = require("../../docs/protocol/test-vectors/final-attestation-v1.json");

describe("IFinalAttestationVerifierV1", function () {
  it("uses the fixed nine-input ABI and rejects malformed inputs", async function () {
    const verifier = await (await ethers.getContractFactory("MockFinalAttestationVerifierV1")).deploy();
    const inputs = vectors.vectors[0].publicInputs.map(BigInt);
    await verifier.verifyProof.staticCall("0x1234", inputs);

    const malformed = [...inputs];
    malformed[0] = 2n;
    await expect(verifier.verifyProof.staticCall("0x1234", malformed)).to.be.revertedWith(
      "invalid v1 public inputs"
    );

    await verifier.setResult(false);
    await expect(verifier.verifyProof.staticCall("0x1234", inputs)).to.be.revertedWith("invalid final proof");
  });
});
