// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../IFinalAttestationVerifierV2.sol";

contract MockFinalAttestationVerifierV2 is IFinalAttestationVerifierV2 {
    bool public shouldSucceed = true;

    function setResult(bool result) external {
        shouldSucceed = result;
    }

    function verifyProof(bytes calldata, uint256[10] calldata) external view {
        require(shouldSucceed, "invalid final proof");
    }
}
