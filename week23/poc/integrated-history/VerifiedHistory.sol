// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

// A signature/digest history fixture. Groth16 validity is attested OFF CHAIN.
contract VerifiedHistory {
    struct Envelope {
        bytes32 session;
        bytes32 evidence;
        uint64 epoch;
        uint64 deadline;
        uint256 proofSession;
        uint256 claimedRID;
        uint256 bucket;
        uint256 policy;
        uint256 members;
        uint256 consistent;
        uint256 suspicious;
    }
    address public immutable authority;
    uint64 public epoch;
    uint256 public immutable policy;
    address[3] public observers;
    mapping(address => bool) public revoked;
    mapping(bytes32 => bytes32) public accepted;
    event Decision(bytes32 indexed session, bytes32 evidence, uint64 epoch, uint256 consistent, uint256 suspicious);
    event Epoch(uint64 epoch, address[3] observers);
    event Revoked(address observer);
    constructor(uint256 p, address[3] memory roster) {
        authority = msg.sender;
        policy = p;
        _rotate(roster);
    }
    function _rotate(address[3] memory roster) private {
        require(roster[0] != address(0) && roster[1] != address(0) && roster[2] != address(0), "zero");
        require(roster[0] != roster[1] && roster[0] != roster[2] && roster[1] != roster[2], "duplicate roster");
        observers = roster;
        for (uint i; i < 3; ++i) revoked[roster[i]] = false;
        ++epoch;
        emit Epoch(epoch, roster);
    }
    function rotate(address[3] calldata roster) external {
        require(msg.sender == authority, "authority");
        _rotate(roster);
    }
    function revoke(address observer) external {
        require(msg.sender == authority, "authority");
        revoked[observer] = true;
        emit Revoked(observer);
    }
    function sessionId(Envelope memory e) public pure returns (bytes32) {
        return keccak256(abi.encode("week23-history-v1", uint256(1), e.proofSession, e.claimedRID, e.bucket, e.policy, e.epoch));
    }
    function payload(Envelope memory e) public view returns (bytes32) {
        return keccak256(abi.encode("week23-receipt-signature-v1", block.chainid, address(this), e));
    }
    function recover(bytes32 p, bytes memory sig) private pure returns (address) {
        require(sig.length == 65, "length");
        bytes32 r; bytes32 s; uint8 v;
        assembly { r := mload(add(sig, 32)) s := mload(add(sig, 64)) v := byte(0, mload(add(sig, 96))) }
        require(uint256(s) <= 0x7fffffffffffffffffffffffffffffff5d576e7357a4501ddfe92f46681b20a0 && (v == 27 || v == 28), "canonical");
        return ecrecover(keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", p)), v, r, s);
    }
    function submit(Envelope calldata e, bytes[] calldata signatures) external {
        require(e.epoch == epoch && e.policy == policy, "epoch/policy");
        require(e.session == sessionId(e), "session");
        require(e.deadline >= block.timestamp && e.deadline <= block.timestamp + 300, "expiry");
        require(e.members == 7 && e.consistent + e.suspicious == 3, "members/count");
        require(e.evidence != bytes32(0) && accepted[e.session] == bytes32(0), "decided");
        require(signatures.length == 3, "full roster");
        uint mask;
        bytes32 p = payload(e);
        for (uint i; i < 3; ++i) {
            address signer = recover(p, signatures[i]);
            require(!revoked[signer], "revoked");
            bool found;
            for (uint j; j < 3; ++j) {
                if (signer != address(0) && signer == observers[j]) {
                    require(mask & (1 << j) == 0, "duplicate");
                    mask |= 1 << j; found = true;
                }
            }
            require(found, "unknown");
        }
        require(mask == 7, "full roster");
        accepted[e.session] = e.evidence;
        emit Decision(e.session, e.evidence, e.epoch, e.consistent, e.suspicious);
    }
    // Two signed, conflicting envelopes are evidence of equivocation, not a sensor-truth test.
    function reportEquivocation(Envelope calldata a, bytes calldata sa, Envelope calldata b, bytes calldata sb) external {
        require(a.session == b.session && a.session == sessionId(a) && b.session == sessionId(b), "same session");
        require(a.epoch == epoch && b.epoch == epoch && a.evidence != b.evidence, "conflict");
        address signer = recover(payload(a), sa);
        require(signer != address(0) && signer == recover(payload(b), sb), "signer");
        bool known;
        for (uint i; i < 3; ++i) if (observers[i] == signer) known = true;
        require(known, "unknown");
        revoked[signer] = true;
        emit Revoked(signer);
    }
}
