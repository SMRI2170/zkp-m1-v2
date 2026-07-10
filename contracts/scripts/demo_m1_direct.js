// M1直接提出のデモ: 各端末が自分の Groth16 証明を「直接」チェーンに提出する。
// 許可型チェーン(Besu QBFT)ではこの提出Txが BFT合意で必ず包含され、全複製される
// （検閲不可・DA内蔵）。ここでは実RPCノードに対して同じフローを実演する。
//   npx hardhat node                          # 別ターミナルで実RPCノード起動
//   npx hardhat run scripts/demo_m1_direct.js --network localhost
const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");

const IDX = {
  WITHIN30: 6, DRONE_ID: 10, PUBX: 11, PUBY: 12, BUCKET: 13,
  CONSISTENCY: 14, DRONE_AUTH: 15, OPERATOR: 16, FRESHNESS: 17,
};

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

async function main() {
  const dir = path.join(__dirname, "..", "test", "fixtures");
  const devs = [0, 1, 2].map((i) => ({
    proof: JSON.parse(fs.readFileSync(path.join(dir, `input_dev${i}_proof.json`))),
    pub: JSON.parse(fs.readFileSync(path.join(dir, `input_dev${i}_public.json`))),
  }));

  const K = 2;
  const net = await ethers.provider.getNetwork();
  console.log(`chainId=${net.chainId}  (許可型なら Besu QBFT の chainId)`);

  const Verifier = await ethers.getContractFactory("Groth16Verifier");
  const verifier = await Verifier.deploy();
  await verifier.waitForDeployment();
  const Registry = await ethers.getContractFactory("AttestationRegistry");
  const registry = await Registry.deploy(await verifier.getAddress(), K);
  await registry.waitForDeployment();
  console.log("AttestationRegistry:", await registry.getAddress(), "K=", K);

  // 初期設定（M3）: オペレータ登録・新鮮さ下限・端末登録
  await (await registry.registerOperator(BigInt(devs[0].pub[IDX.OPERATOR]))).wait();
  await (await registry.setMinFreshness(BigInt(devs[0].pub[IDX.FRESHNESS]))).wait();
  for (const d of devs) {
    await (await registry.registerDevice(d.pub[IDX.PUBX], d.pub[IDX.PUBY])).wait();
  }

  const droneId = devs[0].pub[IDX.DRONE_ID];
  const bucket = devs[0].pub[IDX.BUCKET];

  console.log("\n--- 各端末が自分の証明を直接提出 (M1) ---");
  for (let i = 0; i < devs.length; i++) {
    const cd = toCallData(devs[i].proof, devs[i].pub);
    const tx = await registry.submitAttestation(cd.a, cd.b, cd.c, cd.input);
    const r = await tx.wait();
    console.log(
      `dev${i}: block=${r.blockNumber} gasUsed=${r.gasUsed} ` +
        `consistency=${devs[i].pub[IDX.CONSISTENCY]} drone_auth=${devs[i].pub[IDX.DRONE_AUTH]}`
    );
  }

  console.log("\n--- 結果 ---");
  console.log("trusted(ConsensusReached):", await registry.isConsensus(droneId, bucket));
  console.log("consistentCount          :", (await registry.consistentCountOf(droneId, bucket)).toString());
  console.log("spoofAlert               :", await registry.isSpoofAlert(droneId, bucket));
  console.log("\nBesu QBFT では上記提出Txが BFT合意で必ず包含・全複製される（検閲不可・DA内蔵）。");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
