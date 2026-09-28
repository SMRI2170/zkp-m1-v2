// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title IAggregateVerifier
/// @notice 最終集約 proof の検証器インターフェース。
/// @dev publicInputs の並びは集約回路 AggCircuit と同一に固定する。
///      [droneIdCommitment, timeBucket, consistentCount, suspiciousCount, memberRoot]
interface IAggregateVerifier {
    function verifyProof(bytes calldata proof, uint256[5] calldata publicInputs) external view;
}
