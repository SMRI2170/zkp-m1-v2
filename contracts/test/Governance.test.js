const { expect } = require("chai");
const { ethers } = require("hardhat");

// #4: ガバナンス強化（Ownable2Step + Timelock 所有）のテスト。
describe("Governance: Ownable2Step + Timelock", function () {
  let registry, mock, owner, alice, bob;

  beforeEach(async function () {
    [owner, alice, bob] = await ethers.getSigners();
    mock = await (await ethers.getContractFactory("MockVerifier")).deploy();
    registry = await (await ethers.getContractFactory("AttestationRegistry"))
      .deploy(await mock.getAddress(), 3);
  });

  it("2段階の所有権移転（transfer→pending→accept）", async function () {
    await registry.transferOwnership(alice.address);
    // まだ移っていない：owner は元のまま、pendingOwner が alice
    expect(await registry.owner()).to.equal(owner.address);
    expect(await registry.pendingOwner()).to.equal(alice.address);
    // pending でない bob は accept できない
    await expect(registry.connect(bob).acceptOwnership()).to.be.reverted;
    // alice が受理して初めて移る
    await registry.connect(alice).acceptOwnership();
    expect(await registry.owner()).to.equal(alice.address);
  });

  it("移転後、旧ownerは onlyOwner を呼べない", async function () {
    await registry.transferOwnership(alice.address);
    await registry.connect(alice).acceptOwnership();
    await expect(registry.setMinFreshness(1)).to.be.reverted; // 旧owner(owner)は不可
    await registry.connect(alice).setMinFreshness(1); // 新owner(alice)は可
    expect(await registry.minFreshness()).to.equal(1n);
  });

  it("owner=Timelock: 方針変更は遅延を経てのみ実行できる", async function () {
    const DELAY = 60; // seconds
    const Timelock = await ethers.getContractFactory("TimelockController");
    // proposer/executor = owner（本番はマルチシグ/複数者）
    const timelock = await Timelock.deploy(DELAY, [owner.address], [owner.address], owner.address);
    const tlAddr = await timelock.getAddress();

    // registry の所有権を Timelock へ（2段階）: transfer → timelock が accept を予約実行
    await registry.transferOwnership(tlAddr);
    const acceptData = registry.interface.encodeFunctionData("acceptOwnership");
    const salt = ethers.ZeroHash;
    await timelock.schedule(await registry.getAddress(), 0, acceptData, ethers.ZeroHash, salt, DELAY);
    await ethers.provider.send("evm_increaseTime", [DELAY + 1]);
    await ethers.provider.send("evm_mine", []);
    await timelock.execute(await registry.getAddress(), 0, acceptData, ethers.ZeroHash, salt);
    expect(await registry.owner()).to.equal(tlAddr);

    // 以降、方針変更(setDeviceRoot)は Timelock 経由＝遅延必須
    const setData = registry.interface.encodeFunctionData("setDeviceRoot", [12345]);
    const salt2 = ethers.id("setDeviceRoot");
    await timelock.schedule(await registry.getAddress(), 0, setData, ethers.ZeroHash, salt2, DELAY);
    // 遅延前は実行不可
    await expect(
      timelock.execute(await registry.getAddress(), 0, setData, ethers.ZeroHash, salt2)
    ).to.be.reverted;
    // 遅延後は実行可
    await ethers.provider.send("evm_increaseTime", [DELAY + 1]);
    await ethers.provider.send("evm_mine", []);
    await timelock.execute(await registry.getAddress(), 0, setData, ethers.ZeroHash, salt2);
    expect(await registry.deviceRoot()).to.equal(12345n);
  });
});
