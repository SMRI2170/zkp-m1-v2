// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title IFinalAttestationVerifierV1
/// @notice Stable EVM boundary for final-attestation-v1 Groth16/BN254 proofs.
/// @dev Generated verifier adapters MUST expose exactly this ABI.  The legacy
///      five-input IAggregateVerifier remains only for the M2 PoC fixture.
interface IFinalAttestationVerifierV1 {
    function verifyProof(bytes calldata proof, uint256[9] calldata publicInputs) external view;
}
