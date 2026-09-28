package nullifier

import (
	"math/big"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/test"

	"uav/aggregator/membership"
)

func vars(values []*big.Int) [membership.Depth]frontend.Variable {
	var out [membership.Depth]frontend.Variable
	for i := range out {
		out[i] = values[i]
	}
	return out
}

func bitVars(values []int) [membership.Depth]frontend.Variable {
	var out [membership.Depth]frontend.Variable
	for i := range out {
		out[i] = values[i]
	}
	return out
}

func TestNullifierTransition(t *testing.T) {
	assert := test.NewAssert(t)
	protocolVersion := big.NewInt(1)
	droneID := big.NewInt(424242)
	timeBucket := big.NewInt(100001)
	policyCommitment := big.NewInt(123456789)
	session := SessionCommitment(protocolVersion, droneID, timeBucket, policyCommitment)
	type device struct{ x, y *big.Int }
	devices := []device{
		{big.NewInt(1001), big.NewInt(2001)},
		{big.NewInt(1002), big.NewInt(2002)},
		{big.NewInt(1003), big.NewInt(2003)},
	}

	memberLeaves := make([]*big.Int, len(devices))
	for i, d := range devices {
		memberLeaves[i] = membership.MimcHash(d.x, d.y)
	}
	memberRoot, memberSiblings, memberBits := membership.BuildTree(memberLeaves)

	// At session start, every nullifier slot is zero.
	zeroLeaves := make([]*big.Int, 1<<membership.Depth)
	for i := range zeroLeaves {
		zeroLeaves[i] = big.NewInt(0)
	}
	oldRoot, nullifierSiblings, _ := membership.BuildTree(zeroLeaves)

	leaf0 := memberLeaves[0]
	nullifier0 := Nullifier(leaf0, session)
	spentLeaves := append([]*big.Int(nil), zeroLeaves...)
	spentLeaves[0] = nullifier0
	newRoot, _, _ := membership.BuildTree(spentLeaves)

	valid := &Circuit{
		ProtocolVersion: protocolVersion, DroneID: droneID, TimeBucket: timeBucket,
		PolicyCommitment: policyCommitment, MemberRoot: memberRoot, SessionCommitment: session,
		OldNullifierRoot: oldRoot, NewNullifierRoot: newRoot,
		DevicePubKeyX: devices[0].x, DevicePubKeyY: devices[0].y,
		MemberSiblings:    vars(memberSiblings[0]),
		NullifierSiblings: vars(nullifierSiblings[0]),
		PathBits:          bitVars(memberBits[0]),
	}
	assert.SolvingSucceeded(&Circuit{}, valid, test.WithCurves(ecc.BN254))

	// Reusing device 0 against the updated root fails: its old leaf is no longer zero.
	duplicate := *valid
	duplicate.OldNullifierRoot = newRoot
	assert.SolvingFailed(&Circuit{}, &duplicate, test.WithCurves(ecc.BN254))

	// A non-member cannot consume an authorised index, even with a valid nullifier path.
	unknown := *valid
	unknown.DevicePubKeyX = big.NewInt(999999)
	assert.SolvingFailed(&Circuit{}, &unknown, test.WithCurves(ecc.BN254))

	// Changing the session changes the required new root and cannot replay this transition.
	otherSession := *valid
	otherSession.TimeBucket = big.NewInt(100002)
	assert.SolvingFailed(&Circuit{}, &otherSession, test.WithCurves(ecc.BN254))
}
