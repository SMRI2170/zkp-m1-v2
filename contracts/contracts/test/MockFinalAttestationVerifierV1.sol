// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../IFinalAttestationVerifierV1.sol";
import "../FinalAttestationProtocolV1.sol";

/// @dev Test-only placeholder. It models a generated verifier's ABI and
/// rejects malformed v1 public inputs; it must never be deployed in production.
contract MockFinalAttestationVerifierV1 is IFinalAttestationVerifierV1 {
    bool public result = true;

    function setResult(bool value) external {
        result = value;
    }

    function verifyProof(bytes calldata, uint256[9] calldata publicInputs) external view override {
        uint256[9] memory inputs = publicInputs;
        require(FinalAttestationProtocolV1.isValidPublicInputs(inputs), "invalid v1 public inputs");
        require(result, "invalid final proof");
    }
}
