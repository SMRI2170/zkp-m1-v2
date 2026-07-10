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

const IDX = {
  WITHIN30: 6, DRONE_ID: 10, PUBX: 11, PUBY: 12, BUCKET: 13, CONSISTENCY: 14,
  DRONE_AUTH: 15, OPERATOR: 16, FRESHNESS: 17,
};
const K = 2;

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
    // M3: オペレータ登録 + 新鮮さ下限（fixture の freshness 以下を許容）
    await registry.registerOperator(devs[0].pub[IDX.OPERATOR]);
    await registry.setMinFreshness(devs[0].pub[IDX.FRESHNESS]);
  });

  it("実証明: 整合2台で trusted 合意、詐称1台は suspicious", async function () {
    const droneId = devs[0].pub[IDX.DRONE_ID];
    const bucket = devs[0].pub[IDX.BUCKET];
    // dev0/dev1 は consistency_ok=1（整合）, dev2 は =0（詐称: 放送は近いが実測は遠い）
    expect(devs[0].pub[IDX.CONSISTENCY]).to.equal("1");
    expect(devs[2].pub[IDX.CONSISTENCY]).to.equal("0");

    const s0 = toCallData(devs[0].proof, devs[0].pub);
    await registry.submitAttestation(s0.a, s0.b, s0.c, s0.input);
    expect(await registry.isConsensus(droneId, bucket)).to.equal(false);

    const s1 = toCallData(devs[1].proof, devs[1].pub);
    await expect(
      registry.submitAttestation(s1.a, s1.b, s1.c, s1.input)
    ).to.emit(registry, "ConsensusReached"); // 整合 K=2 台 → 裏取り成立

    const s2 = toCallData(devs[2].proof, devs[2].pub);
    await registry.submitAttestation(s2.a, s2.b, s2.c, s2.input); // 詐称は suspicious 側

    expect(await registry.isConsensus(droneId, bucket)).to.equal(true);
    expect(await registry.consistentCountOf(droneId, bucket)).to.equal(2n);
    expect(await registry.isSpoofAlert(droneId, bucket)).to.equal(false);
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
