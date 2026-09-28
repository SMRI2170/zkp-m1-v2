// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import "./IAggregateVerifier.sol";

/// @title FinalAttestationRegistry
/// @notice M2 の集約 proof を「どの Remote ID 観測セッションの最終判定か」として記録する。
/// @dev 個々の端末の座標、生 RSSI、leaf proof は保存しない。proof が束縛する公開値だけを保存する。
contract FinalAttestationRegistry is Ownable2Step {
    enum Verdict {
        Undetermined,
        Trusted,
        SpoofSuspected
    }

    struct FinalAttestation {
        Verdict verdict;
        uint64 finalizedAt;
        uint256 consistentCount;
        uint256 suspiciousCount;
        uint256 memberRoot;
        bytes32 proofHash;
    }

    // publicInputs の index。AggCircuit の output 順と必ず同じにする。
    uint256 private constant IDX_DRONE_ID = 0;
    uint256 private constant IDX_TIME_BUCKET = 1;
    uint256 private constant IDX_CONSISTENT = 2;
    uint256 private constant IDX_SUSPICIOUS = 3;
    uint256 private constant IDX_MEMBER_ROOT = 4;

    IAggregateVerifier public immutable verifier;
    uint256 public immutable threshold;
    uint256 public deviceRoot;

    mapping(bytes32 sessionId => FinalAttestation) private finalAttestations;
    mapping(bytes32 proofHash => bool) public proofUsed;

    event DeviceRootUpdated(uint256 indexed memberRoot);
    event Finalized(
        bytes32 indexed sessionId,
        uint256 indexed droneIdCommitment,
        uint256 indexed timeBucket,
        Verdict verdict,
        uint256 consistentCount,
        uint256 suspiciousCount,
        uint256 memberRoot,
        bytes32 proofHash
    );

    constructor(IAggregateVerifier _verifier, uint256 _threshold) Ownable(msg.sender) {
        require(address(_verifier) != address(0), "verifier is zero");
        require(_threshold > 0, "threshold must be > 0");
        verifier = _verifier;
        threshold = _threshold;
    }

    /// @notice 登録端末集合の Root を更新する。実運用では Timelock / multisig を owner にする。
    function setDeviceRoot(uint256 root) external onlyOwner {
        deviceRoot = root;
        emit DeviceRootUpdated(root);
    }

    function sessionIdOf(uint256 droneIdCommitment, uint256 timeBucket) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(droneIdCommitment, timeBucket));
    }

    /// @notice 検証済みの集約 proof を最終レコードとして一度だけ確定する。
    /// @dev proof が drone/time/counts/root を束縛するため、提出者は別セッションへ結果を付け替えられない。
    function submitFinal(bytes calldata proof, uint256[5] calldata publicInputs) external {
        require(publicInputs[IDX_MEMBER_ROOT] == deviceRoot, "member root mismatch");
        require(
            publicInputs[IDX_CONSISTENT] + publicInputs[IDX_SUSPICIOUS] > 0,
            "empty aggregate"
        );

        bool trusted = publicInputs[IDX_CONSISTENT] >= threshold;
        bool suspicious = publicInputs[IDX_SUSPICIOUS] >= threshold;
        require(!(trusted && suspicious), "conflicting verdict");

        bytes32 sessionId = sessionIdOf(publicInputs[IDX_DRONE_ID], publicInputs[IDX_TIME_BUCKET]);
        require(finalAttestations[sessionId].finalizedAt == 0, "session already finalized");

        bytes32 proofHash = keccak256(proof);
        require(!proofUsed[proofHash], "proof already used");

        // 検証器は revert したら証明無効。成功した publicInputs のみを保存する。
        verifier.verifyProof(proof, publicInputs);

        Verdict verdict = trusted
            ? Verdict.Trusted
            : suspicious
                ? Verdict.SpoofSuspected
                : Verdict.Undetermined;

        finalAttestations[sessionId] = FinalAttestation({
            verdict: verdict,
            finalizedAt: uint64(block.timestamp),
            consistentCount: publicInputs[IDX_CONSISTENT],
            suspiciousCount: publicInputs[IDX_SUSPICIOUS],
            memberRoot: publicInputs[IDX_MEMBER_ROOT],
            proofHash: proofHash
        });
        proofUsed[proofHash] = true;

        emit Finalized(
            sessionId,
            publicInputs[IDX_DRONE_ID],
            publicInputs[IDX_TIME_BUCKET],
            verdict,
            publicInputs[IDX_CONSISTENT],
            publicInputs[IDX_SUSPICIOUS],
            publicInputs[IDX_MEMBER_ROOT],
            proofHash
        );
    }

    function finalAttestationOf(
        uint256 droneIdCommitment,
        uint256 timeBucket
    ) external view returns (FinalAttestation memory) {
        return finalAttestations[sessionIdOf(droneIdCommitment, timeBucket)];
    }
}
