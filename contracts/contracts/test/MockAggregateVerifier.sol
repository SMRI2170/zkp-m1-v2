// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../IAggregateVerifier.sol";

/// @notice FinalAttestationRegistry の状態遷移テスト専用 verifier。
contract MockAggregateVerifier is IAggregateVerifier {
    bool public result = true;

    function setResult(bool value) external {
        result = value;
    }

    function verifyProof(bytes calldata, uint256[5] calldata) external view override {
        require(result, "invalid aggregate proof");
    }
}
