// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// 本番ガバナンス用に OpenZeppelin の TimelockController をコンパイル対象へ含める。
// AttestationRegistry の owner をこの Timelock（さらにその背後をマルチシグ/Safe）に
// 移すことで、「owner compromise ＝ 即時全制御」を防ぐ（変更は遅延＋多者承認を経る）。
import {TimelockController} from "@openzeppelin/contracts/governance/TimelockController.sol";
