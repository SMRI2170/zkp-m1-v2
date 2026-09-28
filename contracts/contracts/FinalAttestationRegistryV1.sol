// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import "./FinalAttestationProtocolV1.sol";
import "./IFinalAttestationVerifierV1.sol";

/// @title FinalAttestationRegistryV1
/// @notice Immutable record of a final-attestation-v1 proof verification.
/// @dev The verifier proves private observation data. This contract only keeps
///      the versioned public statement and never stores device IDs, RSSI,
///      locations, leaf proofs, Merkle paths, or nullifiers themselves.
contract FinalAttestationRegistryV1 is Ownable2Step {
    enum Verdict {
        Undetermined,
        Trusted,
        SpoofSuspected
    }

    struct FinalAttestation {
        uint8 protocolVersion;
        Verdict verdict;
        uint64 timeBucket;
        uint64 finalizedAt;
        uint32 consistentCount;
        uint32 suspiciousCount;
        uint256 droneIdCommitment;
        uint256 policyCommitment;
        uint256 memberRoot;
        uint256 nullifierRoot;
        bytes32 verifierVersion;
        bytes32 proofHash;
    }

    IFinalAttestationVerifierV1 public immutable verifier;
    bytes32 public immutable verifierVersion;

    // The active roots/policies are admission controls for new sessions. A
    // finalized record stores its own values and is never changed retroactively.
    uint256 public activeMemberRoot;
    mapping(uint256 policyCommitment => bool) public approvedPolicy;
    mapping(bytes32 sessionId => FinalAttestation) private finalAttestations;
    mapping(bytes32 proofHash => bool) public proofUsed;

    event MemberRootUpdated(uint256 indexed memberRoot);
    event PolicyApprovalUpdated(uint256 indexed policyCommitment, bool approved);
    event Finalized(
        bytes32 indexed sessionId,
        uint256 indexed droneIdCommitment,
        uint64 indexed timeBucket,
        uint256 policyCommitment,
        uint256 memberRoot,
        uint256 nullifierRoot,
        Verdict verdict,
        uint32 consistentCount,
        uint32 suspiciousCount,
        bytes32 verifierVersion,
        bytes32 proofHash
    );

    constructor(
        IFinalAttestationVerifierV1 _verifier,
        bytes32 _verifierVersion
    ) Ownable(msg.sender) {
        require(address(_verifier) != address(0), "verifier is zero");
        require(_verifierVersion != bytes32(0), "verifier version is zero");
        verifier = _verifier;
        verifierVersion = _verifierVersion;
    }

    function setActiveMemberRoot(uint256 memberRoot) external onlyOwner {
        require(FinalAttestationProtocolV1.isCanonicalFieldElement(memberRoot), "invalid member root");
        activeMemberRoot = memberRoot;
        emit MemberRootUpdated(memberRoot);
    }

    function setPolicyApproval(uint256 policyCommitment, bool approved) external onlyOwner {
        require(FinalAttestationProtocolV1.isCanonicalFieldElement(policyCommitment), "invalid policy");
        approvedPolicy[policyCommitment] = approved;
        emit PolicyApprovalUpdated(policyCommitment, approved);
    }

    function sessionIdOf(
        uint256 droneIdCommitment,
        uint64 timeBucket,
        uint256 policyCommitment
    ) public pure returns (bytes32) {
        return FinalAttestationProtocolV1.sessionIdOf(droneIdCommitment, timeBucket, policyCommitment);
    }

    /// @notice Verify and permanently finalize one v1 proof statement.
    function submitFinal(bytes calldata proof, uint256[9] calldata publicInputs) external {
        uint256[9] memory inputs = publicInputs;
        require(FinalAttestationProtocolV1.isValidPublicInputs(inputs), "invalid v1 public inputs");
        require(
            inputs[FinalAttestationProtocolV1.IDX_MEMBER_ROOT] == activeMemberRoot,
            "member root mismatch"
        );
        require(
            approvedPolicy[inputs[FinalAttestationProtocolV1.IDX_POLICY_COMMITMENT]],
            "policy not approved"
        );
        require(
            inputs[FinalAttestationProtocolV1.IDX_CONSISTENT_COUNT] +
                inputs[FinalAttestationProtocolV1.IDX_SUSPICIOUS_COUNT] > 0,
            "empty aggregate"
        );

        uint64 timeBucket = uint64(inputs[FinalAttestationProtocolV1.IDX_TIME_BUCKET]);
        bytes32 sessionId = sessionIdOf(
            inputs[FinalAttestationProtocolV1.IDX_DRONE_ID],
            timeBucket,
            inputs[FinalAttestationProtocolV1.IDX_POLICY_COMMITMENT]
        );
        require(finalAttestations[sessionId].finalizedAt == 0, "session already finalized");

        bytes32 proofHash = keccak256(proof);
        require(!proofUsed[proofHash], "proof already used");

        verifier.verifyProof(proof, publicInputs);

        Verdict verdict = Verdict(inputs[FinalAttestationProtocolV1.IDX_VERDICT]);
        finalAttestations[sessionId] = FinalAttestation({
            protocolVersion: uint8(inputs[FinalAttestationProtocolV1.IDX_PROTOCOL_VERSION]),
            verdict: verdict,
            timeBucket: timeBucket,
            finalizedAt: uint64(block.timestamp),
            consistentCount: uint32(inputs[FinalAttestationProtocolV1.IDX_CONSISTENT_COUNT]),
            suspiciousCount: uint32(inputs[FinalAttestationProtocolV1.IDX_SUSPICIOUS_COUNT]),
            droneIdCommitment: inputs[FinalAttestationProtocolV1.IDX_DRONE_ID],
            policyCommitment: inputs[FinalAttestationProtocolV1.IDX_POLICY_COMMITMENT],
            memberRoot: inputs[FinalAttestationProtocolV1.IDX_MEMBER_ROOT],
            nullifierRoot: inputs[FinalAttestationProtocolV1.IDX_NULLIFIER_ROOT],
            verifierVersion: verifierVersion,
            proofHash: proofHash
        });
        proofUsed[proofHash] = true;

        emit Finalized(
            sessionId,
            inputs[FinalAttestationProtocolV1.IDX_DRONE_ID],
            timeBucket,
            inputs[FinalAttestationProtocolV1.IDX_POLICY_COMMITMENT],
            inputs[FinalAttestationProtocolV1.IDX_MEMBER_ROOT],
            inputs[FinalAttestationProtocolV1.IDX_NULLIFIER_ROOT],
            verdict,
            uint32(inputs[FinalAttestationProtocolV1.IDX_CONSISTENT_COUNT]),
            uint32(inputs[FinalAttestationProtocolV1.IDX_SUSPICIOUS_COUNT]),
            verifierVersion,
            proofHash
        );
    }

    function finalAttestationOf(
        uint256 droneIdCommitment,
        uint64 timeBucket,
        uint256 policyCommitment
    ) external view returns (FinalAttestation memory) {
        return finalAttestations[sessionIdOf(droneIdCommitment, timeBucket, policyCommitment)];
    }
}
