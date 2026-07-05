// SPDX-License-Identifier: MIT
pragma solidity >=0.7.0 <0.9.0;

/// @title snarkjs Groth16 検証器のインターフェース
/// @dev `snarkjs zkey export solidityverifier` が生成する Groth16Verifier の
///      verifyProof シグネチャに合わせる。input 長 = 回路の public signal 数(14)。
interface IGroth16Verifier {
    function verifyProof(
        uint[2] calldata a,
        uint[2][2] calldata b,
        uint[2] calldata c,
        uint[14] calldata input
    ) external view returns (bool);
}
