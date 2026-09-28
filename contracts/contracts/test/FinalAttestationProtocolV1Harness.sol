// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../FinalAttestationProtocolV1.sol";

/// @dev Test-only public surface for validating the canonical Solidity ABI.
contract FinalAttestationProtocolV1Harness {
    function sessionIdOf(
        uint256 droneIdCommitment,
        uint64 timeBucket,
        uint256 policyCommitment
    ) external pure returns (bytes32) {
        return FinalAttestationProtocolV1.sessionIdOf(droneIdCommitment, timeBucket, policyCommitment);
    }

    function isCanonicalFieldElement(uint256 value) external pure returns (bool) {
        return FinalAttestationProtocolV1.isCanonicalFieldElement(value);
    }

    function isValidPublicInputs(uint256[9] calldata inputs) external pure returns (bool) {
        uint256[9] memory copied = inputs;
        return FinalAttestationProtocolV1.isValidPublicInputs(copied);
    }
}
