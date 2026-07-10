const { expect } = require("chai");
const { ethers } = require("hardhat");

// public signal レイアウト（回路 output 宣言順、長さ 14）
const IDX = {
  WITHIN30_AND_DETECTED: 6,
  DRONE_ID_COMMITMENT: 10,
  DEVICE_PUBKEY_X: 11,
  DEVICE_PUBKEY_Y: 12,
  TIME_BUCKET: 13,
  CONSISTENCY_OK: 14,
  DRONE_AUTH_OK: 15,
  DRONE_OPERATOR: 16,
  FRESHNESS: 17,
};

const OPERATOR = 7777n; // 登録オペレータ commitment
const FRESHNESS = 1000n; // 新鮮さビーコン

// mock verifier は proof を無視するのでダミーで良い
const DUMMY_A = [0, 0];
const DUMMY_B = [
  [0, 0],
  [0, 0],
];
const DUMMY_C = [0, 0];

function makeInput({
  within30 = 1,
  droneId,
  pubX,
  pubY,
  bucket,
  consistent = 1,
  droneAuth = 1,
  operator = OPERATOR,
  freshness = FRESHNESS,
}) {
  const input = new Array(18).fill(0n);
  input[IDX.WITHIN30_AND_DETECTED] = BigInt(within30);
  input[IDX.DRONE_ID_COMMITMENT] = BigInt(droneId);
  input[IDX.DEVICE_PUBKEY_X] = BigInt(pubX);
  input[IDX.DEVICE_PUBKEY_Y] = BigInt(pubY);
  input[IDX.TIME_BUCKET] = BigInt(bucket);
  input[IDX.CONSISTENCY_OK] = BigInt(consistent);
  input[IDX.DRONE_AUTH_OK] = BigInt(droneAuth);
  input[IDX.DRONE_OPERATOR] = BigInt(operator);
  input[IDX.FRESHNESS] = BigInt(freshness);
  return input;
}

const K = 3;
const DRONE = 111111n;
const BUCKET = 28524120n; // 1711447200 / 60 相当のダミー

describe("AttestationRegistry (M1, K=3)", function () {
  let registry, mock, owner;
  // 端末鍵（ダミー）
  const devices = [
    { pubX: 1001n, pubY: 2001n },
    { pubX: 1002n, pubY: 2002n },
    { pubX: 1003n, pubY: 2003n },
    { pubX: 1004n, pubY: 2004n },
  ];

  beforeEach(async function () {
    [owner] = await ethers.getSigners();
    const Mock = await ethers.getContractFactory("MockVerifier");
    mock = await Mock.deploy();
    const Registry = await ethers.getContractFactory("AttestationRegistry");
    registry = await Registry.deploy(await mock.getAddress(), K);
    // M3: オペレータ登録 + 新鮮さ下限を設定（FRESHNESS 以下を許容）
    await registry.registerOperator(OPERATOR);
    await registry.setMinFreshness(FRESHNESS);
  });

  async function register(d) {
    await registry.registerDevice(d.pubX, d.pubY);
  }

  function proofFor(d, opts = {}) {
    return makeInput({
      droneId: opts.droneId ?? DRONE,
      bucket: opts.bucket ?? BUCKET,
      pubX: d.pubX,
      pubY: d.pubY,
      within30: opts.within30 ?? 1,
      consistent: opts.consistent ?? 1,
      droneAuth: opts.droneAuth ?? 1,
      operator: opts.operator ?? OPERATOR,
      freshness: opts.freshness ?? FRESHNESS,
    });
  }

  it("M3: 未認証ドローン(drone_auth_ok=0)は拒否", async function () {
    await register(devices[0]);
    await expect(
      registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[0], { droneAuth: 0 }))
    ).to.be.revertedWith("drone RemoteID not authenticated");
  });

  it("M3: 未登録オペレータは拒否", async function () {
    await register(devices[0]);
    await expect(
      registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[0], { operator: 9999n }))
    ).to.be.revertedWith("operator not registered");
  });

  it("M3: 古い freshness(リプレイ)は拒否", async function () {
    await register(devices[0]);
    await expect(
      registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[0], { freshness: FRESHNESS - 1n }))
    ).to.be.revertedWith("stale (replay)");
  });

  it("K 台の相異なる登録端末が揃うと consensus 成立", async function () {
    for (const d of devices.slice(0, 3)) await register(d);

    await registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[0]));
    expect(await registry.isConsensus(DRONE, BUCKET)).to.equal(false);

    await registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[1]));
    expect(await registry.isConsensus(DRONE, BUCKET)).to.equal(false);

    await expect(
      registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[2]))
    ).to.emit(registry, "ConsensusReached");

    expect(await registry.isConsensus(DRONE, BUCKET)).to.equal(true);
    expect(await registry.countOf(DRONE, BUCKET)).to.equal(3n);
  });

  it("同一端末の二重提出は計上されない", async function () {
    await register(devices[0]);
    await registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[0]));
    await expect(
      registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[0]))
    ).to.be.revertedWith("device already counted");
    expect(await registry.countOf(DRONE, BUCKET)).to.equal(1n);
  });

  it("未登録端末は拒否", async function () {
    await expect(
      registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[0]))
    ).to.be.revertedWith("device not registered");
  });

  it("within30_and_detected != 1 は拒否", async function () {
    await register(devices[0]);
    await expect(
      registry.submitAttestation(
        DUMMY_A,
        DUMMY_B,
        DUMMY_C,
        proofFor(devices[0], { within30: 0 })
      )
    ).to.be.revertedWith("within30_and_detected != 1");
  });

  it("無効な証明は拒否（verifier=false）", async function () {
    await register(devices[0]);
    await mock.setResult(false);
    await expect(
      registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[0]))
    ).to.be.revertedWith("invalid proof");
  });

  it("別ドローンは別グループとして数え、混ぜても consensus しない", async function () {
    for (const d of devices.slice(0, 3)) await register(d);
    const OTHER = 999999n;
    // 同一ドローンには 2 台だけ、別ドローンに 1 台
    await registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[0]));
    await registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[1]));
    await registry.submitAttestation(
      DUMMY_A,
      DUMMY_B,
      DUMMY_C,
      proofFor(devices[2], { droneId: OTHER })
    );
    expect(await registry.isConsensus(DRONE, BUCKET)).to.equal(false);
    expect(await registry.countOf(DRONE, BUCKET)).to.equal(2n);
    expect(await registry.countOf(OTHER, BUCKET)).to.equal(1n);
  });

  it("K 台が矛盾(consistency_ok=0)を検出 → SpoofAlert", async function () {
    for (const d of devices.slice(0, 3)) await register(d);
    await registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[0], { consistent: 0 }));
    await registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[1], { consistent: 0 }));
    await expect(
      registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[2], { consistent: 0 }))
    ).to.emit(registry, "SpoofAlert");
    expect(await registry.isSpoofAlert(DRONE, BUCKET)).to.equal(true);
    expect(await registry.isConsensus(DRONE, BUCKET)).to.equal(false);
  });

  it("整合と矛盾が混在: 整合K台で trusted, 矛盾は別カウント", async function () {
    for (const d of devices.slice(0, 4)) await register(d);
    // 整合 3 台 → trusted、矛盾 1 台 → suspicious だが K 未満
    await registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[0], { consistent: 1 }));
    await registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[1], { consistent: 1 }));
    await registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[3], { consistent: 0 }));
    await registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[2], { consistent: 1 }));
    expect(await registry.isConsensus(DRONE, BUCKET)).to.equal(true);
    expect(await registry.consistentCountOf(DRONE, BUCKET)).to.equal(3n);
    expect(await registry.isSpoofAlert(DRONE, BUCKET)).to.equal(false);
  });

  it("別時間窓は別グループ", async function () {
    for (const d of devices.slice(0, 3)) await register(d);
    await registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[0]));
    await registry.submitAttestation(DUMMY_A, DUMMY_B, DUMMY_C, proofFor(devices[1]));
    await registry.submitAttestation(
      DUMMY_A,
      DUMMY_B,
      DUMMY_C,
      proofFor(devices[2], { bucket: BUCKET + 1n })
    );
    expect(await registry.isConsensus(DRONE, BUCKET)).to.equal(false);
    expect(await registry.countOf(DRONE, BUCKET)).to.equal(2n);
  });
});
