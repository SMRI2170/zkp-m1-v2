const { expect } = require("chai");
const { ethers } = require("hardhat");

// gnark が出力した集約証明（N=3 の witness を1つに集約）。
// verifyProof(bytes proof, uint256[2] input) は失敗時 revert（view）。
const agg = require("./fixtures/aggregate.json");

describe("Spike C: 集約証明のオンチェーン検証（定数gas）", function () {
  let verifier;
  const input = [BigInt(agg.consistentCount), BigInt(agg.suspiciousCount)];

  beforeEach(async function () {
    const V = await ethers.getContractFactory("Verifier"); // AggregateVerifier.sol
    verifier = await V.deploy();
  });

  it("正しい集約証明は1回の検証で通り、gas を計測", async function () {
    // view: revert しなければ検証成功
    await verifier.verifyProof.staticCall(agg.proof, input);
    const gas = await verifier.verifyProof.estimateGas(agg.proof, input);
    console.log(`      集約検証 gas = ${gas.toString()}  (N=3を1回で検証／台数非依存)`);
    // 現実的な範囲（数十万gas以内）であること
    expect(gas).to.be.lessThan(600000n);
  });

  it("公開入力(consistent/suspicious)を偽ると revert", async function () {
    await expect(
      verifier.verifyProof.staticCall(agg.proof, [1n, 2n])
    ).to.be.reverted;
  });

  it("proof を改ざんすると revert", async function () {
    const tampered = "0x" + "00" + agg.proof.slice(4); // 先頭バイトを潰す
    await expect(verifier.verifyProof.staticCall(tampered, input)).to.be.reverted;
  });
});
