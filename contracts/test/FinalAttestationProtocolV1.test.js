const { expect } = require("chai");
const { ethers } = require("hardhat");
const vectors = require("../../docs/protocol/test-vectors/final-attestation-v1.json");

describe("final-attestation-v1 public-input ABI", function () {
  it("uses the fixed nine-field public-input order", function () {
    expect(vectors.publicInputOrder).to.deep.equal([
      "protocolVersion",
      "droneIdCommitment",
      "timeBucket",
      "policyCommitment",
      "memberRoot",
      "nullifierRoot",
      "consistentCount",
      "suspiciousCount",
      "verdict",
    ]);
    for (const vector of vectors.vectors) {
      expect(vector.publicInputs).to.have.length(9);
      expect(vector.publicInputs[0]).to.equal("1");
      expect(["0", "1", "2"]).to.include(vector.publicInputs[8]);
    }
  });

  it("derives sessionId with Solidity abi.encode semantics, not packed encoding", async function () {
    const harness = await (await ethers.getContractFactory("FinalAttestationProtocolV1Harness")).deploy();
    for (const vector of vectors.vectors) {
      const encoded = ethers.AbiCoder.defaultAbiCoder().encode(
        vector.sessionIdPreimageTypes,
        vector.sessionIdPreimage.map(BigInt)
      );
      const derived = ethers.keccak256(encoded);
      expect(derived).to.equal(vector.sessionId);
      expect(
        await harness.sessionIdOf(
          BigInt(vector.sessionIdPreimage[1]),
          BigInt(vector.sessionIdPreimage[2]),
          BigInt(vector.sessionIdPreimage[3])
        )
      ).to.equal(vector.sessionId);

      const packed = ethers.solidityPackedKeccak256(
        vector.sessionIdPreimageTypes,
        vector.sessionIdPreimage.map(BigInt)
      );
      expect(derived).to.not.equal(packed);
    }
  });

  it("rejects values outside the BN254 scalar field", async function () {
    const harness = await (await ethers.getContractFactory("FinalAttestationProtocolV1Harness")).deploy();
    const modulus = BigInt(vectors.bn254ScalarField);
    expect(await harness.isCanonicalFieldElement(modulus - 1n)).to.equal(true);
    expect(await harness.isCanonicalFieldElement(modulus)).to.equal(false);
  });

  it("rejects malformed v1 input ranges before calling a verifier", async function () {
    const harness = await (await ethers.getContractFactory("FinalAttestationProtocolV1Harness")).deploy();
    const valid = vectors.vectors[0].publicInputs.map(BigInt);
    expect(await harness.isValidPublicInputs(valid)).to.equal(true);

    const wrongVersion = [...valid];
    wrongVersion[0] = 2n;
    expect(await harness.isValidPublicInputs(wrongVersion)).to.equal(false);

    const invalidVerdict = [...valid];
    invalidVerdict[8] = 3n;
    expect(await harness.isValidPublicInputs(invalidVerdict)).to.equal(false);

    const invalidCount = [...valid];
    invalidCount[6] = 2n ** 32n;
    expect(await harness.isValidPublicInputs(invalidCount)).to.equal(false);
  });
});
