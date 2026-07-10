// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./IGroth16Verifier.sol";

/// @title AttestationRegistry
/// @notice マルチ端末 UAV 接近証明のオンチェーン結合（M1: 個別検証＋閾値レジストリ）。
///
/// 各端末が `uav_witness_attestation.circom` の Groth16 証明を提出する。
/// 同一ドローン(drone_id_commitment) × 同一時間窓(time_bucket) について、
/// 相異なる登録端末が閾値 K 台ぶん有効な証明を出したら consensus 成立とみなす。
///
/// public signal のインデックスは回路の output 宣言順に対応:
///   [0] within30            [7]  drone_commitment
///   [1] distance_ok         [8]  target_commitment
///   [2] time_ok             [9]  frame_binding
///   [3] detection_ok        [10] drone_id_commitment
///   [4] frame_time_ok       [11] device_pubkey_x
///   [5] detection_bundle_ok [12] device_pubkey_y
///   [6] within30_and_detected [13] time_bucket
///                           [14] consistency_ok (RSSI 整合: 1=整合 / 0=矛盾)
///
/// 同一グループで相異なる登録端末が K 台:
///   consistency_ok=1 で揃う → ConsensusReached（放送位置が物理的に裏取りされた）
///   consistency_ok=0 で揃う → SpoofAlert（放送位置が実測と矛盾＝なりすまし疑い）
contract AttestationRegistry {
    // ── public signal インデックス ───────────────────────────────────────────
    uint256 private constant IDX_WITHIN30_AND_DETECTED = 6;
    uint256 private constant IDX_DRONE_ID_COMMITMENT = 10;
    uint256 private constant IDX_DEVICE_PUBKEY_X = 11;
    uint256 private constant IDX_DEVICE_PUBKEY_Y = 12;
    uint256 private constant IDX_TIME_BUCKET = 13;
    uint256 private constant IDX_CONSISTENCY_OK = 14;

    IGroth16Verifier public immutable verifier;
    uint256 public immutable threshold; // K
    address public owner;

    // 登録端末（Sybil 対策）: deviceId = keccak256(pubkey_x, pubkey_y)
    mapping(bytes32 => bool) public registeredDevice;

    // グループ = keccak256(drone_id_commitment, time_bucket)
    mapping(bytes32 => uint256) public witnessCount;      // 総提出数（整合＋矛盾）
    mapping(bytes32 => uint256) public consistentCount;   // consistency_ok=1 の数
    mapping(bytes32 => uint256) public suspiciousCount;   // consistency_ok=0 の数
    mapping(bytes32 => bool) public consensusReached;     // 裏取り成立（trusted）
    mapping(bytes32 => bool) public spoofAlert;           // なりすまし疑い
    // 同一グループ内で同一端末の二重計上を防ぐ
    mapping(bytes32 => mapping(bytes32 => bool)) public counted;

    event DeviceRegistered(bytes32 indexed deviceId);
    event DeviceDeregistered(bytes32 indexed deviceId);
    event AttestationAccepted(
        bytes32 indexed groupKey,
        bytes32 indexed deviceId,
        bool consistent,
        uint256 consistentCount,
        uint256 suspiciousCount
    );
    event ConsensusReached(
        bytes32 indexed groupKey,
        uint256 droneIdCommitment,
        uint256 timeBucket,
        uint256 count
    );
    event SpoofAlert(
        bytes32 indexed groupKey,
        uint256 droneIdCommitment,
        uint256 timeBucket,
        uint256 count
    );

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    constructor(IGroth16Verifier _verifier, uint256 _threshold) {
        require(_threshold > 0, "threshold must be > 0");
        verifier = _verifier;
        threshold = _threshold;
        owner = msg.sender;
    }

    // ── 端末登録（デモは owner 制御。実運用はハード鍵アテステーション等へ）────────
    function registerDevice(uint256 pubkeyX, uint256 pubkeyY) external onlyOwner {
        bytes32 deviceId = keccak256(abi.encodePacked(pubkeyX, pubkeyY));
        registeredDevice[deviceId] = true;
        emit DeviceRegistered(deviceId);
    }

    function deregisterDevice(uint256 pubkeyX, uint256 pubkeyY) external onlyOwner {
        bytes32 deviceId = keccak256(abi.encodePacked(pubkeyX, pubkeyY));
        registeredDevice[deviceId] = false;
        emit DeviceDeregistered(deviceId);
    }

    function deviceIdOf(uint256 pubkeyX, uint256 pubkeyY) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(pubkeyX, pubkeyY));
    }

    function groupKeyOf(uint256 droneIdCommitment, uint256 timeBucket) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(droneIdCommitment, timeBucket));
    }

    // ── 証明の提出（誰が送信してもよい。合意は device_pubkey 単位で数える）────────
    function submitAttestation(
        uint[2] calldata a,
        uint[2][2] calldata b,
        uint[2] calldata c,
        uint[15] calldata input
    ) external {
        require(input[IDX_WITHIN30_AND_DETECTED] == 1, "within30_and_detected != 1");
        require(verifier.verifyProof(a, b, c, input), "invalid proof");

        bytes32 deviceId = keccak256(
            abi.encodePacked(input[IDX_DEVICE_PUBKEY_X], input[IDX_DEVICE_PUBKEY_Y])
        );
        require(registeredDevice[deviceId], "device not registered");

        bytes32 groupKey = keccak256(
            abi.encodePacked(input[IDX_DRONE_ID_COMMITMENT], input[IDX_TIME_BUCKET])
        );
        require(!counted[groupKey][deviceId], "device already counted");

        counted[groupKey][deviceId] = true;
        witnessCount[groupKey] += 1;

        bool consistent = input[IDX_CONSISTENCY_OK] == 1;
        if (consistent) {
            consistentCount[groupKey] += 1;
        } else {
            suspiciousCount[groupKey] += 1;
        }
        emit AttestationAccepted(
            groupKey, deviceId, consistent, consistentCount[groupKey], suspiciousCount[groupKey]
        );

        // 整合が K 台 → 放送位置の裏取り成立（trusted）
        if (consistentCount[groupKey] >= threshold && !consensusReached[groupKey]) {
            consensusReached[groupKey] = true;
            emit ConsensusReached(
                groupKey, input[IDX_DRONE_ID_COMMITMENT], input[IDX_TIME_BUCKET],
                consistentCount[groupKey]
            );
        }
        // 矛盾が K 台 → なりすまし疑い
        if (suspiciousCount[groupKey] >= threshold && !spoofAlert[groupKey]) {
            spoofAlert[groupKey] = true;
            emit SpoofAlert(
                groupKey, input[IDX_DRONE_ID_COMMITMENT], input[IDX_TIME_BUCKET],
                suspiciousCount[groupKey]
            );
        }
    }

    // ── 参照ヘルパ ───────────────────────────────────────────────────────────
    function isConsensus(uint256 droneIdCommitment, uint256 timeBucket) external view returns (bool) {
        return consensusReached[groupKeyOf(droneIdCommitment, timeBucket)];
    }

    function isSpoofAlert(uint256 droneIdCommitment, uint256 timeBucket) external view returns (bool) {
        return spoofAlert[groupKeyOf(droneIdCommitment, timeBucket)];
    }

    function countOf(uint256 droneIdCommitment, uint256 timeBucket) external view returns (uint256) {
        return witnessCount[groupKeyOf(droneIdCommitment, timeBucket)];
    }

    function consistentCountOf(uint256 droneIdCommitment, uint256 timeBucket)
        external view returns (uint256)
    {
        return consistentCount[groupKeyOf(droneIdCommitment, timeBucket)];
    }
}
