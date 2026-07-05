// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../IGroth16Verifier.sol";

/// @title MockVerifier
/// @notice テスト用。Groth16 の本ビルド前に AttestationRegistry のロジック
///         （閾値・重複排除・端末登録）を検証するためのスタブ。
///         `setResult(false)` で「無効な証明」も再現できる。
contract MockVerifier is IGroth16Verifier {
    bool public result = true;

    function setResult(bool r) external {
        result = r;
    }

    function verifyProof(
        uint[2] calldata,
        uint[2][2] calldata,
        uint[2] calldata,
        uint[14] calldata
    ) external view override returns (bool) {
        return result;
    }
}
