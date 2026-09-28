package nullifier

import (
	"math/big"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/test"

	"uav/aggregator/membership"
)

func TestPairTransitionConsumesTwoDifferentAuthorisedDevices(t *testing.T) {
	assert := test.NewAssert(t)
	version := big.NewInt(1)
	droneID := big.NewInt(424242)
	bucket := big.NewInt(100001)
	policy := big.NewInt(123456789)
	session := SessionCommitment(version, droneID, bucket, policy)
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
	zeroLeaves := make([]*big.Int, 1<<membership.Depth)
	for i := range zeroLeaves {
		zeroLeaves[i] = big.NewInt(0)
	}
	oldRoot, firstSiblings, firstBits := membership.BuildTree(zeroLeaves)
	spentOne := append([]*big.Int(nil), zeroLeaves...)
	spentOne[0] = Nullifier(memberLeaves[0], session)
	intermediateRoot, secondSiblings, secondBits := membership.BuildTree(spentOne)
	spentTwo := append([]*big.Int(nil), spentOne...)
	spentTwo[1] = Nullifier(memberLeaves[1], session)
	newRoot, _, _ := membership.BuildTree(spentTwo)

	valid := &PairCircuit{
		ProtocolVersion: version, DroneID: droneID, TimeBucket: bucket,
		PolicyCommitment: policy, MemberRoot: memberRoot, SessionCommitment: session,
		OldNullifierRoot: oldRoot, NewNullifierRoot: newRoot,
	}
	for i := 0; i < 2; i++ {
		valid.DevicePubKeyX[i] = devices[i].x
		valid.DevicePubKeyY[i] = devices[i].y
		valid.MemberSiblings[i] = vars(memberSiblings[i])
	}
	valid.NullifierSiblings[0] = vars(firstSiblings[0])
	valid.PathBits[0] = bitVars(firstBits[0])
	valid.NullifierSiblings[1] = vars(secondSiblings[1])
	valid.PathBits[1] = bitVars(secondBits[1])
	if intermediateRoot.Sign() == 0 {
		t.Fatal("intermediate root must reflect the first consumption")
	}
	assert.SolvingSucceeded(&PairCircuit{}, valid, test.WithCurves(ecc.BN254))

	// A final root that omits the second consumption is not a valid pair transition.
	omitSecond := *valid
	omitSecond.NewNullifierRoot = intermediateRoot
	assert.SolvingFailed(&PairCircuit{}, &omitSecond, test.WithCurves(ecc.BN254))

	// The same device cannot occupy the second slot: its path is evaluated
	// against the post-first root, where its leaf is no longer zero.
	replay := *valid
	replay.DevicePubKeyX[1] = devices[0].x
	replay.DevicePubKeyY[1] = devices[0].y
	replay.MemberSiblings[1] = vars(memberSiblings[0])
	replay.PathBits[1] = bitVars(memberBits[0])
	replay.NullifierSiblings[1] = vars(secondSiblings[0])
	assert.SolvingFailed(&PairCircuit{}, &replay, test.WithCurves(ecc.BN254))

	unknown := *valid
	unknown.DevicePubKeyX[1] = frontend.Variable(big.NewInt(999999))
	assert.SolvingFailed(&PairCircuit{}, &unknown, test.WithCurves(ecc.BN254))
}
