package nullifier

import (
	"github.com/consensys/gnark/frontend"

	"uav/aggregator/membership"
)

// PairCircuit consumes two authorised devices in a deterministic order. It is
// the smallest stateful merge primitive used by the recursive PCD: it proves
// oldRoot -- device[0] --> intermediateRoot -- device[1] --> newRoot entirely
// inside one circuit. It does not hash independently claimed child roots.
//
// The two paths use the same index for the authorisation and nullifier trees.
// The second nullifier path is against intermediateRoot, so using one device
// twice cannot satisfy its required zero leaf.
type PairCircuit struct {
	ProtocolVersion   frontend.Variable `gnark:",public"`
	DroneID           frontend.Variable `gnark:",public"`
	TimeBucket        frontend.Variable `gnark:",public"`
	PolicyCommitment  frontend.Variable `gnark:",public"`
	MemberRoot        frontend.Variable `gnark:",public"`
	SessionCommitment frontend.Variable `gnark:",public"`
	OldNullifierRoot  frontend.Variable `gnark:",public"`
	NewNullifierRoot  frontend.Variable `gnark:",public"`

	DevicePubKeyX [2]frontend.Variable
	DevicePubKeyY [2]frontend.Variable

	MemberSiblings    [2][membership.Depth]frontend.Variable
	NullifierSiblings [2][membership.Depth]frontend.Variable
	PathBits          [2][membership.Depth]frontend.Variable
}

func (c *PairCircuit) Define(api frontend.API) error {
	api.AssertIsEqual(c.ProtocolVersion, 1)
	sessionCommitment, err := hashSession(
		api, c.ProtocolVersion, c.DroneID, c.TimeBucket, c.PolicyCommitment,
	)
	if err != nil {
		return err
	}
	api.AssertIsEqual(sessionCommitment, c.SessionCommitment)

	currentRoot := c.OldNullifierRoot
	for i := 0; i < 2; i++ {
		deviceLeaf, err := membership.Leaf(api, c.DevicePubKeyX[i], c.DevicePubKeyY[i])
		if err != nil {
			return err
		}
		memberRoot, err := membership.ComputeRoot(api, deviceLeaf, c.MemberSiblings[i], c.PathBits[i])
		if err != nil {
			return err
		}
		api.AssertIsEqual(memberRoot, c.MemberRoot)

		// For i=1, currentRoot already includes device 0. Thus a repeat
		// cannot be represented as an unused zero leaf.
		unusedRoot, err := membership.ComputeRoot(api, 0, c.NullifierSiblings[i], c.PathBits[i])
		if err != nil {
			return err
		}
		api.AssertIsEqual(unusedRoot, currentRoot)

		nullifier, err := hashNullifier(api, deviceLeaf, c.SessionCommitment)
		if err != nil {
			return err
		}
		api.AssertIsDifferent(nullifier, 0)
		currentRoot, err = membership.ComputeRoot(api, nullifier, c.NullifierSiblings[i], c.PathBits[i])
		if err != nil {
			return err
		}
	}
	api.AssertIsEqual(currentRoot, c.NewNullifierRoot)
	return nil
}
