// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title IFinalAttestationVerifierV2
/// @notice Stable EVM boundary for the versioned 10-input FinalBNV2 proof.
interface IFinalAttestationVerifierV2 {
    function verifyProof(bytes calldata proof, uint256[10] calldata publicInputs) external view;
}
