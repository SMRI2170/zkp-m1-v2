// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title FinalAttestationProtocolV1
/// @notice Canonical public-input indexes and EVM session-id derivation for
///         final-attestation-v1.  The nine-input verifier is introduced in
///         Issue #5; this library intentionally does not retrofit the M2 PoC.
library FinalAttestationProtocolV1 {
    uint8 internal constant VERSION = 1;
    uint256 internal constant PUBLIC_INPUT_COUNT = 9;
    uint256 internal constant BN254_SCALAR_FIELD =
        21888242871839275222246405745257275088548364400416034343698204186575808495617;

    uint256 internal constant IDX_PROTOCOL_VERSION = 0;
    uint256 internal constant IDX_DRONE_ID = 1;
    uint256 internal constant IDX_TIME_BUCKET = 2;
    uint256 internal constant IDX_POLICY_COMMITMENT = 3;
    uint256 internal constant IDX_MEMBER_ROOT = 4;
    uint256 internal constant IDX_NULLIFIER_ROOT = 5;
    uint256 internal constant IDX_CONSISTENT_COUNT = 6;
    uint256 internal constant IDX_SUSPICIOUS_COUNT = 7;
    uint256 internal constant IDX_VERDICT = 8;

    function sessionIdOf(
        uint256 droneIdCommitment,
        uint64 timeBucket,
        uint256 policyCommitment
    ) internal pure returns (bytes32) {
        return keccak256(abi.encode(VERSION, droneIdCommitment, timeBucket, policyCommitment));
    }

    function isCanonicalFieldElement(uint256 value) internal pure returns (bool) {
        return value < BN254_SCALAR_FIELD;
    }

    /// @notice Cheap ABI/range checks that must happen before an EVM verifier
    /// call.  This does not replace the ZK constraints; it prevents malformed
    /// values from being interpreted differently by a registry and verifier.
    function isValidPublicInputs(uint256[PUBLIC_INPUT_COUNT] memory inputs) internal pure returns (bool) {
        if (inputs[IDX_PROTOCOL_VERSION] != VERSION) return false;
        if (inputs[IDX_TIME_BUCKET] > type(uint64).max) return false;
        if (inputs[IDX_CONSISTENT_COUNT] > type(uint32).max) return false;
        if (inputs[IDX_SUSPICIOUS_COUNT] > type(uint32).max) return false;
        if (inputs[IDX_VERDICT] > 2) return false;
        for (uint256 i = 0; i < PUBLIC_INPUT_COUNT; i++) {
            if (!isCanonicalFieldElement(inputs[i])) return false;
        }
        return true;
    }
}
