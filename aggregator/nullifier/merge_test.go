package nullifier

import (
	"math/big"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/test"

	"uav/aggregator/membership"
)

func treeRoot(leaves [TreeSize]*big.Int) *big.Int {
	values := make([]*big.Int, TreeSize)
	copy(values, leaves[:])
	root, _, _ := membership.BuildTree(values)
	return root
}

func mergeAssignment(left, right [TreeSize]*big.Int) *MergeCircuit {
	merged := [TreeSize]*big.Int{}
	for i := 0; i < TreeSize; i++ {
		merged[i] = new(big.Int).Add(left[i], right[i])
	}
	a := &MergeCircuit{LeftRoot: treeRoot(left), RightRoot: treeRoot(right), MergedRoot: treeRoot(merged)}
	for i := 0; i < TreeSize; i++ {
		a.LeftLeaves[i] = left[i]
		a.RightLeaves[i] = right[i]
	}
	return a
}

func zeroTree() [TreeSize]*big.Int {
	var leaves [TreeSize]*big.Int
	for i := range leaves {
		leaves[i] = big.NewInt(0)
	}
	return leaves
}

func TestMergeCircuitUnionsDisjointNullifierTrees(t *testing.T) {
	left, right := zeroTree(), zeroTree()
	left[0], left[3] = big.NewInt(101), big.NewInt(103)
	right[1], right[6] = big.NewInt(201), big.NewInt(206)
	assert := test.NewAssert(t)
	assert.SolvingSucceeded(&MergeCircuit{}, mergeAssignment(left, right), test.WithCurves(ecc.BN254), test.NoFuzzing())
}

func TestMergeCircuitRejectsOverlappingIndex(t *testing.T) {
	left, right := zeroTree(), zeroTree()
	left[2] = big.NewInt(102)
	right[2] = big.NewInt(202)
	assert := test.NewAssert(t)
	assert.SolvingFailed(&MergeCircuit{}, mergeAssignment(left, right), test.WithCurves(ecc.BN254), test.NoFuzzing())
}

func TestMergeCircuitRejectsForgedMergedRoot(t *testing.T) {
	left, right := zeroTree(), zeroTree()
	left[0], right[1] = big.NewInt(100), big.NewInt(200)
	a := mergeAssignment(left, right)
	a.MergedRoot = big.NewInt(1)
	assert := test.NewAssert(t)
	assert.SolvingFailed(&MergeCircuit{}, a, test.WithCurves(ecc.BN254), test.NoFuzzing())
}

// Keep frontend imported in this file so the assignment type is checked against
// the circuit representation even if TreeSize changes with membership.Depth.
var _ frontend.Circuit = (*MergeCircuit)(nil)
