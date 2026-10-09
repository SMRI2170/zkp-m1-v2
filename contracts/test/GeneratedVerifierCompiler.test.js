const { expect } = require("chai");
const { compileVerifier, compileVerifierV2 } = require("../scripts/generated_verifier_compiler");
const {
  parseCanonicalPublicInputs,
  validateArtifactMinimumQuorum,
  validateArtifactVerifierHash,
} = require("../scripts/verify_pcd3_final_v2_evm");

const BN254_SCALAR_FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617n;

describe("generated FinalBN verifier compiler", function () {
  it("requires all ten FinalBNV2 public inputs to be canonical BN254 scalars", function () {
    const rawInputs = Array(10).fill("0");
    rawInputs[0] = "2";
    const parsed = parseCanonicalPublicInputs(rawInputs);
    expect(parsed).to.have.lengthOf(10);
    expect(parsed[0]).to.equal(2n);

    for (let index = 0; index < rawInputs.length; index += 1) {
      const outOfField = [...rawInputs];
      outOfField[index] = BN254_SCALAR_FIELD.toString();
      expect(() => parseCanonicalPublicInputs(outOfField))
        .to.throw(`publicInputs[${index}] must be a canonical BN254 scalar`);
    }
    expect(() => parseCanonicalPublicInputs(rawInputs.slice(0, 9)))
      .to.throw("artifact must contain ten public inputs");
    const nonCanonical = [...rawInputs];
    nonCanonical[6] = "00";
    expect(() => parseCanonicalPublicInputs(nonCanonical))
      .to.throw("publicInputs[6] must be a canonical decimal string");
  });

  it("requires the FinalBNV2 artifact quorum to match the independently approved value", function () {
    expect(() => validateArtifactMinimumQuorum({ minimumQuorum: 2 }, 2)).not.to.throw();
    expect(() => validateArtifactMinimumQuorum({ minimumQuorum: 3 }, 2))
      .to.throw("differs from independently configured approved quorum");
    expect(() => validateArtifactMinimumQuorum({ minimumQuorum: 0 }, 0))
      .to.throw("artifact minimumQuorum is invalid");
    expect(() => validateArtifactMinimumQuorum({ minimumQuorum: 0x100000000 }, 0x100000000))
      .to.throw("artifact minimumQuorum is invalid");
  });

  it("requires the FinalBNV2 artifact verifier hash to match an independent approval", function () {
    const verifierHash = "ab".repeat(32);
    expect(() => validateArtifactVerifierHash(verifierHash, verifierHash)).not.to.throw();
    expect(() => validateArtifactVerifierHash(verifierHash, "cd".repeat(32)))
      .to.throw("differs from independently approved verifier hash");
    expect(() => validateArtifactVerifierHash("not-a-sha256", "cd".repeat(32)))
      .to.throw("artifact verifierSha256 is invalid");
  });

  it("compiles only the v1 verifyProof(bytes,uint256[9]) boundary", function () {
    const source = `
      // SPDX-License-Identifier: MIT
      pragma solidity ^0.8.0;
      contract TestGeneratedVerifier {
        function verifyProof(bytes calldata proof, uint256[9] calldata publicInputs) external pure {
          require(proof.length == 1 && publicInputs[0] == 1, "bad test proof");
        }
      }
    `;
    const compiled = compileVerifier(source);
    expect(compiled.abi.some((entry) => entry.name === "verifyProof")).to.equal(true);
    expect(compiled.evm.bytecode.object.length).to.be.greaterThan(0);
  });

  it("rejects a verifier with a different public-input width", function () {
    const source = `
      pragma solidity ^0.8.0;
      contract WrongWidthVerifier {
        function verifyProof(bytes calldata, uint256[8] calldata) external pure {}
      }
    `;
    expect(() => compileVerifier(source)).to.throw("not verifyProof(bytes,uint256[9])");
  });

  it("compiles only the v2 verifyProof(bytes,uint256[10]) boundary", function () {
    const source = `
      // SPDX-License-Identifier: MIT
      pragma solidity ^0.8.0;
      contract TestGeneratedVerifierV2 {
        function verifyProof(bytes calldata proof, uint256[10] calldata publicInputs) external pure {
          require(proof.length == 1 && publicInputs[0] == 2, "bad test proof");
        }
      }
    `;
    const compiled = compileVerifierV2(source);
    expect(compiled.abi.some((entry) => entry.name === "verifyProof")).to.equal(true);
    expect(compiled.evm.bytecode.object.length).to.be.greaterThan(0);

    const wrongWidth = source.replace("uint256[10]", "uint256[9]");
    expect(() => compileVerifierV2(wrongWidth)).to.throw("not verifyProof(bytes,uint256[10])");
  });
});
