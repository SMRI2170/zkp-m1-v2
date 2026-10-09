// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import "./FinalAttestationProtocolV2.sol";
import "./IFinalAttestationVerifierV2.sol";

/// @title FinalAttestationRegistryV2
/// @notice Immutable record of a 10-input multi-observer V2 final proof.
/// @dev Session and proof hashes are single-use. Raw locations, RSSI, leaf
///      proofs, roster openings, and observer nullifiers are never stored.
contract FinalAttestationRegistryV2 is Ownable2Step {
    // Numeric ABI: 0 = insufficient evidence, 1 = no inconsistency observed,
    // 2 = position inconsistency suspected. Value 1 does not authenticate the aircraft.
    enum Verdict { Undetermined, NoInconsistencyObserved, PositionInconsistencySuspected }

    struct FinalAttestation {
        uint8 protocolVersion;
        Verdict verdict;
        uint64 timeBucket;
        uint64 finalizedAt;
        uint256 calibrationProfileSetRoot;
        uint32 consistentCount;
        uint32 suspiciousCount;
        uint256 droneIdCommitment;
        uint256 policyCommitment;
        uint256 memberRoot;
        uint256 nullifierRoot;
        bytes32 verifierVersion;
        bytes32 proofHash;
    }

    IFinalAttestationVerifierV2 public immutable verifier;
    bytes32 public immutable verifierVersion;
    uint256 public activeMemberRoot;
    uint64 public maxSessionAgeSeconds = 120;
    uint64 public maxFutureSkewSeconds = 5;
    mapping(uint256 policyCommitment => bool) public approvedPolicy;
    mapping(bytes32 sessionId => FinalAttestation) private finalAttestations;
    mapping(bytes32 proofHash => bool) public proofUsed;

    event MemberRootUpdated(uint256 indexed memberRoot);
    event PolicyApprovalUpdated(uint256 indexed policyCommitment, bool approved);
    event FreshnessWindowUpdated(uint64 maxSessionAgeSeconds, uint64 maxFutureSkewSeconds);
    event Finalized(
        bytes32 indexed sessionId,
        uint256 indexed droneIdCommitment,
        uint64 indexed timeBucket,
        uint256 policyCommitment,
        uint256 calibrationProfileSetRoot,
        uint256 memberRoot,
        uint256 nullifierRoot,
        Verdict verdict,
        uint32 consistentCount,
        uint32 suspiciousCount,
        bytes32 verifierVersion,
        bytes32 proofHash
    );

    constructor(IFinalAttestationVerifierV2 _verifier, bytes32 _verifierVersion) Ownable(msg.sender) {
        require(address(_verifier) != address(0), "verifier is zero");
        require(_verifierVersion != bytes32(0), "verifier version is zero");
        verifier = _verifier;
        verifierVersion = _verifierVersion;
    }

    function setActiveMemberRoot(uint256 memberRoot) external onlyOwner {
        require(FinalAttestationProtocolV2.isCanonicalFieldElement(memberRoot), "invalid member root");
        activeMemberRoot = memberRoot;
        emit MemberRootUpdated(memberRoot);
    }

    function setPolicyApproval(uint256 policyCommitment, bool approved) external onlyOwner {
        require(FinalAttestationProtocolV2.isCanonicalFieldElement(policyCommitment), "invalid policy");
        approvedPolicy[policyCommitment] = approved;
        emit PolicyApprovalUpdated(policyCommitment, approved);
    }

    function setFreshnessWindow(uint64 maxAgeSeconds, uint64 maxFutureSkew) external onlyOwner {
        require(maxAgeSeconds > 0 && maxAgeSeconds <= 3600, "invalid max age");
        require(maxFutureSkew <= 60, "invalid future skew");
        maxSessionAgeSeconds = maxAgeSeconds;
        maxFutureSkewSeconds = maxFutureSkew;
        emit FreshnessWindowUpdated(maxAgeSeconds, maxFutureSkew);
    }

    function sessionIdOf(uint256 droneIdCommitment, uint64 timeBucket)
        public pure returns (bytes32)
    {
        return FinalAttestationProtocolV2.sessionIdOf(droneIdCommitment, timeBucket);
    }

    function submitFinal(bytes calldata proof, uint256[10] calldata publicInputs) external {
        uint256[10] memory inputs = publicInputs;
        require(FinalAttestationProtocolV2.isValidPublicInputs(inputs), "invalid v2 public inputs");
        require(inputs[5] == activeMemberRoot, "member root mismatch");
        require(approvedPolicy[inputs[3]], "policy not approved");
        require(inputs[7] + inputs[8] > 0, "empty aggregate");

        // The V2 leaf constrains signed freshness == target_time_sec and
        // derives time_bucket = floor(target_time_sec / 60). Bound submission
        // recency here; this does not prove the observer's clock was honest.
        uint256 bucketStart = inputs[2] * FinalAttestationProtocolV2.TIME_BUCKET_SECONDS;
        require(bucketStart <= block.timestamp + maxFutureSkewSeconds, "session time too far future");
        require(
            bucketStart + FinalAttestationProtocolV2.TIME_BUCKET_SECONDS + maxSessionAgeSeconds >= block.timestamp,
            "stale session"
        );

        uint64 timeBucket = uint64(inputs[2]);
        bytes32 sessionId = sessionIdOf(inputs[1], timeBucket);
        require(finalAttestations[sessionId].finalizedAt == 0, "session already finalized");
        bytes32 proofHash = keccak256(proof);
        require(!proofUsed[proofHash], "proof already used");

        verifier.verifyProof(proof, publicInputs);

        FinalAttestation storage record = finalAttestations[sessionId];
        record.protocolVersion = uint8(inputs[0]);
        record.verdict = Verdict(inputs[9]);
        record.timeBucket = timeBucket;
        record.finalizedAt = uint64(block.timestamp);
        record.calibrationProfileSetRoot = inputs[4];
        record.consistentCount = uint32(inputs[7]);
        record.suspiciousCount = uint32(inputs[8]);
        record.droneIdCommitment = inputs[1];
        record.policyCommitment = inputs[3];
        record.memberRoot = inputs[5];
        record.nullifierRoot = inputs[6];
        record.verifierVersion = verifierVersion;
        record.proofHash = proofHash;
        proofUsed[proofHash] = true;

        emit Finalized(sessionId, inputs[1], timeBucket, inputs[3], inputs[4], inputs[5], inputs[6],
            Verdict(inputs[9]), uint32(inputs[7]), uint32(inputs[8]), verifierVersion, proofHash);
    }

    function finalAttestationOf(uint256 droneIdCommitment, uint64 timeBucket)
        external view returns (FinalAttestation memory)
    {
        return finalAttestations[sessionIdOf(droneIdCommitment, timeBucket)];
    }
}
