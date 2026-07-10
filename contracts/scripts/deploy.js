// 許可型EVM(Besu QBFT / Quorum)にも公開EVMにも同一手順でデプロイできる。
//   npx hardhat run scripts/deploy.js                 … ephemeral(スモーク)
//   npx hardhat run scripts/deploy.js --network besu  … 許可型チェーンへ
//
// M3 の初期設定（オペレータ登録・新鮮さ下限）も env で行う:
//   K=3 OPERATOR=<commitment> MIN_FRESHNESS=<v> npx hardhat run scripts/deploy.js --network besu
const { ethers } = require("hardhat");

async function main() {
  const K = process.env.K ? Number(process.env.K) : 3;

  const Verifier = await ethers.getContractFactory("Groth16Verifier");
  const verifier = await Verifier.deploy();
  await verifier.waitForDeployment();

  const Registry = await ethers.getContractFactory("AttestationRegistry");
  const registry = await Registry.deploy(await verifier.getAddress(), K);
  await registry.waitForDeployment();

  if (process.env.OPERATOR) {
    await (await registry.registerOperator(BigInt(process.env.OPERATOR))).wait();
  }
  if (process.env.MIN_FRESHNESS) {
    await (await registry.setMinFreshness(BigInt(process.env.MIN_FRESHNESS))).wait();
  }

  console.log("Groth16Verifier    :", await verifier.getAddress());
  console.log("AttestationRegistry:", await registry.getAddress());
  console.log("threshold K        :", K);
  console.log(
    "operator registered:",
    process.env.OPERATOR ? process.env.OPERATOR : "(none — call registerOperator later)"
  );
  console.log(
    "minFreshness       :",
    process.env.MIN_FRESHNESS ? process.env.MIN_FRESHNESS : "(0 — call setMinFreshness later)"
  );
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
