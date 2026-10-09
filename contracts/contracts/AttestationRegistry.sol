// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./IGroth16Verifier.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";

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
contract AttestationRegistry is Ownable2Step {
    // ── public signal インデックス ───────────────────────────────────────────
    uint256 private constant IDX_WITHIN30_AND_DETECTED = 6;
    uint256 private constant IDX_DRONE_ID_COMMITMENT = 10;
    uint256 private constant IDX_DEVICE_PUBKEY_X = 11;
    uint256 private constant IDX_DEVICE_PUBKEY_Y = 12;
    uint256 private constant IDX_TIME_BUCKET = 13;
    uint256 private constant IDX_CONSISTENCY_OK = 14;
    uint256 private constant IDX_DRONE_AUTH_OK = 15;         // legacy leaf self-signature check bit
    uint256 private constant IDX_DRONE_OPERATOR = 16;        // commitment to supplied key; no RID binding
    uint256 private constant IDX_FRESHNESS = 17;             // M3: 新鮮さビーコン

    IGroth16Verifier public immutable verifier;
    uint256 public immutable threshold; // K
    // owner は Ownable2Step が提供（2段階移転で誤送金/乗っ取りに強い）。
    // 本番は owner を TimelockController / マルチシグ(Safe) にして「compromise=即時全制御」を防ぐ。

    // 登録端末（Sybil 対策）: deviceId = keccak256(pubkey_x, pubkey_y)
    mapping(bytes32 => bool) public registeredDevice;
    // 登録済み鍵 commitment の gate。現行mappingは claimed droneId との対応を証明しない。
    mapping(uint256 => bool) public registeredOperator;
    // 新鮮さの下限（M3: これ未満の freshness を持つ古い proof を拒否＝リプレイ対策）
    uint256 public minFreshness;
    // 登録端末の Merkle ルート（#3: M2集約の Sybil メンバーシップ用）。
    // 集約回路が公開する Root がこれと一致することを submitAggregate 側で確認する。
    // MiMC ベース（回路 aggregator/membership と一致）。registerDevice と併せて owner が更新。
    uint256 public deviceRoot;

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

    constructor(IGroth16Verifier _verifier, uint256 _threshold) Ownable(msg.sender) {
        require(_threshold > 0, "threshold must be > 0");
        verifier = _verifier;
        threshold = _threshold;
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

    // ── オペレータ登録（M3: ドローン鍵の Sybil 対策）─────────────────────────
    function registerOperator(uint256 operatorCommitment) external onlyOwner {
        registeredOperator[operatorCommitment] = true;
    }

    // ── 新鮮さ下限の更新（M3: 直近窓。これ未満の古い proof を弾く）────────────
    function setMinFreshness(uint256 v) external onlyOwner {
        minFreshness = v;
    }

    // ── 登録端末ルートの更新（#3: M2集約のSybilメンバーシップ）───────────────
    // registerDevice で登録集合が変わったら、その MiMC Merkle ルートを設定する。
    // 集約証明が公開する Root == deviceRoot を submitAggregate が確認する（定数gas）。
    function setDeviceRoot(uint256 root) external onlyOwner {
        deviceRoot = root;
    }

    function groupKeyOf(uint256 droneIdCommitment, uint256 timeBucket) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(droneIdCommitment, timeBucket));
    }

    // ── 証明の提出（誰が送信してもよい。合意は device_pubkey 単位で数える）────────
    function submitAttestation(
        uint[2] calldata a,
        uint[2][2] calldata b,
        uint[2] calldata c,
        uint[18] calldata input
    ) external {
        require(input[IDX_WITHIN30_AND_DETECTED] == 1, "within30_and_detected != 1");
        require(verifier.verifyProof(a, b, c, input), "invalid proof");

        // ── M3: 入力真正性 ────────────────────────────────────────────────
        // ドローン署名RemoteIDが検証済み（偽造対策）
        require(input[IDX_DRONE_AUTH_OK] == 1, "drone RemoteID not authenticated");
        // 登録オペレータの機体のみ（Sybil対策）
        require(registeredOperator[input[IDX_DRONE_OPERATOR]], "operator not registered");
        // 新鮮さが直近窓内（古いproofの使い回し＝リプレイ対策）
        require(input[IDX_FRESHNESS] >= minFreshness, "stale (replay)");

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
