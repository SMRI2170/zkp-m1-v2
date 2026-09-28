// Package nullifier implements the Step-C state transition for a single
// authorised witness device.  A session owns a Merkle tree whose leaf at the
// device's registered index is initially zero.  Spending that index replaces
// zero with a session-specific nullifier, so the same device cannot be counted
// twice in a sequential proof chain.
package nullifier

import (
	"math/big"

	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/hash/mimc"

	"uav/aggregator/membership"
)

// Domain separates this construction from membership leaves and all other
// MiMC uses in the protocol.  It is part of final-attestation-v1.
const (
	SessionDomain   = 42020
	NullifierDomain = 42021
)

// Circuit proves one authorised device consumes its previously unused slot in
// the session nullifier tree.  PathBits are shared deliberately: the device's
// authorisation-tree index and its nullifier-tree index must be identical.
type Circuit struct {
	ProtocolVersion   frontend.Variable `gnark:",public"`
	DroneID           frontend.Variable `gnark:",public"`
	TimeBucket        frontend.Variable `gnark:",public"`
	PolicyCommitment  frontend.Variable `gnark:",public"`
	MemberRoot        frontend.Variable `gnark:",public"`
	SessionCommitment frontend.Variable `gnark:",public"`
	OldNullifierRoot  frontend.Variable `gnark:",public"`
	NewNullifierRoot  frontend.Variable `gnark:",public"`

	DevicePubKeyX frontend.Variable
	DevicePubKeyY frontend.Variable

	MemberSiblings    [membership.Depth]frontend.Variable
	NullifierSiblings [membership.Depth]frontend.Variable
	PathBits          [membership.Depth]frontend.Variable
}

// hashNullifier is MiMC(Domain, deviceLeaf, sessionCommitment).  deviceLeaf
// comes from the registered public key, whose possession is authenticated by
// the leaf attestation proof before this transition is accepted.
func hashNullifier(api frontend.API, deviceLeaf, sessionCommitment frontend.Variable) (frontend.Variable, error) {
	h, err := mimc.NewMiMC(api)
	if err != nil {
		return nil, err
	}
	h.Write(NullifierDomain, deviceLeaf, sessionCommitment)
	return h.Sum(), nil
}

func hashSession(api frontend.API, protocolVersion, droneID, timeBucket, policyCommitment frontend.Variable) (frontend.Variable, error) {
	h, err := mimc.NewMiMC(api)
	if err != nil {
		return nil, err
	}
	h.Write(SessionDomain, protocolVersion, droneID, timeBucket, policyCommitment)
	return h.Sum(), nil
}

func (c *Circuit) Define(api frontend.API) error {
	api.AssertIsEqual(c.ProtocolVersion, 1)
	sessionCommitment, err := hashSession(
		api, c.ProtocolVersion, c.DroneID, c.TimeBucket, c.PolicyCommitment,
	)
	if err != nil {
		return err
	}
	api.AssertIsEqual(sessionCommitment, c.SessionCommitment)

	deviceLeaf, err := membership.Leaf(api, c.DevicePubKeyX, c.DevicePubKeyY)
	if err != nil {
		return err
	}
	memberRoot, err := membership.ComputeRoot(api, deviceLeaf, c.MemberSiblings, c.PathBits)
	if err != nil {
		return err
	}
	api.AssertIsEqual(memberRoot, c.MemberRoot)

	// The old state must prove this registered index is unused.
	oldRoot, err := membership.ComputeRoot(api, 0, c.NullifierSiblings, c.PathBits)
	if err != nil {
		return err
	}
	api.AssertIsEqual(oldRoot, c.OldNullifierRoot)

	nullifier, err := hashNullifier(api, deviceLeaf, c.SessionCommitment)
	if err != nil {
		return err
	}
	api.AssertIsDifferent(nullifier, 0)
	newRoot, err := membership.ComputeRoot(api, nullifier, c.NullifierSiblings, c.PathBits)
	if err != nil {
		return err
	}
	api.AssertIsEqual(newRoot, c.NewNullifierRoot)
	return nil
}

// Nullifier is the off-circuit equivalent of hashNullifier.
func Nullifier(deviceLeaf, sessionCommitment *big.Int) *big.Int {
	return membership.MimcHash(big.NewInt(NullifierDomain), deviceLeaf, sessionCommitment)
}

// SessionCommitment is the off-circuit equivalent of hashSession.  It binds a
// nullifier tree to the same protocol/session/policy tuple used by v1 proofs.
func SessionCommitment(protocolVersion, droneID, timeBucket, policyCommitment *big.Int) *big.Int {
	return membership.MimcHash(big.NewInt(SessionDomain), protocolVersion, droneID, timeBucket, policyCommitment)
}
