const { expect } = require("chai");
const { ethers } = require("hardhat");

// 実 Groth16 証明（scripts/build_witness_attestation_assets.sh の出力）を
// 実 Groth16Verifier + AttestationRegistry に通す E2E テスト。
const devs = [0, 1, 2].map((i) => ({
  proof: require(`./fixtures/input_dev${i}_proof.json`),
  pub: require(`./fixtures/input_dev${i}_public.json`),
}));

// snarkjs proof -> solidity verifier calldata（G2 の x 座標は要スワップ）
function toCallData(proof, pub) {
  return {
    a: [proof.pi_a[0], proof.pi_a[1]],
    b: [
      [proof.pi_b[0][1], proof.pi_b[0][0]],
      [proof.pi_b[1][1], proof.pi_b[1][0]],
    ],
    c: [proof.pi_c[0], proof.pi_c[1]],
    input: pub,
  };
}

const IDX = { WITHIN30: 6, DRONE_ID: 10, PUBX: 11, PUBY: 12, BUCKET: 13 };
const K = 3;

describe("E2E: 実証明 → 実 Groth16Verifier → AttestationRegistry (K=3)", function () {
  let registry, verifier;

  beforeEach(async function () {
    const Verifier = await ethers.getContractFactory("Groth16Verifier");
    verifier = await Verifier.deploy();
    const Registry = await ethers.getContractFactory("AttestationRegistry");
    registry = await Registry.deploy(await verifier.getAddress(), K);
    // 3 端末を登録
    for (const d of devs) {
      await registry.registerDevice(d.pub[IDX.PUBX], d.pub[IDX.PUBY]);
    }
  });

  it("実証明を検証しつつ 3 端末で consensus 成立", async function () {
    const droneId = devs[0].pub[IDX.DRONE_ID];
    const bucket = devs[0].pub[IDX.BUCKET];

    for (let i = 0; i < devs.length; i++) {
      const cd = toCallData(devs[i].proof, devs[i].pub);
      const tx = registry.submitAttestation(cd.a, cd.b, cd.c, cd.input);
      if (i === devs.length - 1) {
        await expect(tx).to.emit(registry, "ConsensusReached");
      } else {
        await tx;
        expect(await registry.isConsensus(droneId, bucket)).to.equal(false);
      }
    }

    expect(await registry.isConsensus(droneId, bucket)).to.equal(true);
    expect(await registry.countOf(droneId, bucket)).to.equal(3n);
  });

  it("改ざんした public signal は実 verifier が弾く", async function () {
    const cd = toCallData(devs[0].proof, devs[0].pub);
    const tampered = [...cd.input];
    // drone_id_commitment を書き換える（within30 は 1 のまま require を通過させ、verifier で落とす）
    tampered[IDX.DRONE_ID] = (BigInt(tampered[IDX.DRONE_ID]) + 1n).toString();
    await expect(
      registry.submitAttestation(cd.a, cd.b, cd.c, tampered)
    ).to.be.revertedWith("invalid proof");
  });
});
