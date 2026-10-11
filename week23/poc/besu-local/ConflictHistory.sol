// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

// Research fixture: signed synthetic digests only; no ZKP or sensor authentication.
contract ConflictHistory {
    address[3] public observers;
    mapping(bytes32 => bytes32) public accepted;
    event Decision(bytes32 indexed slot, bytes32 candidate);
    constructor(address[3] memory roster) { observers = roster; }
    function submit(bytes32 slot, bytes32 candidate, bytes[] calldata signatures) external {
        require(candidate != bytes32(0) && accepted[slot] == bytes32(0), "decided");
        bytes32 payload = keccak256(abi.encode(block.chainid, address(this), slot, candidate));
        bytes32 digest = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", payload));
        uint mask;
        for (uint i; i < signatures.length; ++i) {
            bytes memory sig = signatures[i];
            require(sig.length == 65, "length");
            bytes32 r; bytes32 s; uint8 v;
            assembly { r := mload(add(sig, 32)) s := mload(add(sig, 64)) v := byte(0, mload(add(sig, 96))) }
            require(uint(s) <= 0x7fffffffffffffffffffffffffffffff5d576e7357a4501ddfe92f46681b20a0 && (v == 27 || v == 28), "canonical");
            address signer = ecrecover(digest, v, r, s);
            bool found;
            for (uint j; j < 3; ++j) {
                if (signer != address(0) && signer == observers[j]) {
                    require(mask & (1 << j) == 0, "duplicate");
                    mask |= 1 << j;
                    found = true;
                }
            }
            require(found, "unknown");
        }
        require(mask == 3 || mask == 5 || mask == 6 || mask == 7, "quorum");
        accepted[slot] = candidate;
        emit Decision(slot, candidate);
    }
}
