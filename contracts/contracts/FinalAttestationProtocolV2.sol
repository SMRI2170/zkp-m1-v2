// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title FinalAttestationProtocolV2
/// @notice Public-input order and admission checks for FinalBNV2.
library FinalAttestationProtocolV2 {
    uint8 internal constant VERSION = 2;
    uint256 internal constant PUBLIC_INPUT_COUNT = 10;
    uint64 internal constant TIME_BUCKET_SECONDS = 60;
    uint256 internal constant BN254_SCALAR_FIELD =
        21888242871839275222246405745257275088548364400416034343698204186575808495617;

    uint256 internal constant IDX_PROTOCOL_VERSION = 0;
    uint256 internal constant IDX_DRONE_ID = 1;
    uint256 internal constant IDX_TIME_BUCKET = 2;
    uint256 internal constant IDX_POLICY_COMMITMENT = 3;
    uint256 internal constant IDX_CALIBRATION_PROFILE_SET_ROOT = 4;
    uint256 internal constant IDX_MEMBER_ROOT = 5;
    uint256 internal constant IDX_NULLIFIER_ROOT = 6;
    uint256 internal constant IDX_CONSISTENT_COUNT = 7;
    uint256 internal constant IDX_SUSPICIOUS_COUNT = 8;
    uint256 internal constant IDX_VERDICT = 9;

    function sessionIdOf(uint256 droneIdCommitment, uint64 timeBucket)
        internal pure returns (bytes32)
    {
        // Policy changes must not create a second finalization for the same
        // claimed aircraft/time window.
        return keccak256(abi.encode(VERSION, droneIdCommitment, timeBucket));
    }

    function isCanonicalFieldElement(uint256 value) internal pure returns (bool) {
        return value < BN254_SCALAR_FIELD;
    }

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
