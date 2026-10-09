package pcd

import (
	"math/big"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	"github.com/consensys/gnark/std/math/emulated"
	"github.com/consensys/gnark/test"

	"uav/aggregator/membership"
	"uav/aggregator/nullifier"
)

type nullifierUnionCircuit struct {
	LeftRoot   emulated.Element[sw_bn254.ScalarField] `gnark:",public"`
	RightRoot  emulated.Element[sw_bn254.ScalarField] `gnark:",public"`
	MergedRoot emulated.Element[sw_bn254.ScalarField] `gnark:",public"`
	Left       [nullifier.TreeSize]emulated.Element[sw_bn254.ScalarField]
	Right      [nullifier.TreeSize]emulated.Element[sw_bn254.ScalarField]
}

func (c *nullifierUnionCircuit) Define(api frontend.API) error {
	f, err := emulated.NewField[sw_bn254.ScalarField](api)
	if err != nil {
		return err
	}
	_, err = assertNullifierSetUnion(api, f, c.Left, c.Right, &c.LeftRoot, &c.RightRoot, &c.MergedRoot)
	return err
}

func nativeNullifierRoot(leaves [nullifier.TreeSize]*big.Int) *big.Int {
	level := make([]*big.Int, nullifier.TreeSize)
	for i := range leaves {
		if leaves[i] == nil {
			level[i] = new(big.Int)
		} else {
			level[i] = new(big.Int).Set(leaves[i])
		}
	}
	for len(level) > 1 {
		next := make([]*big.Int, len(level)/2)
		for i := range next {
			next[i] = membership.MimcHash(level[2*i], level[2*i+1])
		}
		level = next
	}
	return level[0]
}

func TestEmulatedNullifierSetUnionAcceptsDisjointObserverSlots(t *testing.T) {
	left := [nullifier.TreeSize]*big.Int{}
	right := [nullifier.TreeSize]*big.Int{}
	left[2], right[11] = big.NewInt(41), big.NewInt(73)
	merged := left
	merged[11] = new(big.Int).Set(right[11])
	assignment := &nullifierUnionCircuit{
		LeftRoot:   emulated.ValueOf[sw_bn254.ScalarField](nativeNullifierRoot(left)),
		RightRoot:  emulated.ValueOf[sw_bn254.ScalarField](nativeNullifierRoot(right)),
		MergedRoot: emulated.ValueOf[sw_bn254.ScalarField](nativeNullifierRoot(merged)),
	}
	assignment.Left, _ = assignNullifierLeaves(left)
	assignment.Right, _ = assignNullifierLeaves(right)
	if err := test.IsSolved(&nullifierUnionCircuit{}, assignment, ecc.BW6_761.ScalarField()); err != nil {
		t.Fatalf("disjoint nullifier sets failed to union: %v", err)
	}
}

func TestEmulatedNullifierSetUnionRejectsDuplicateAndForgedUnion(t *testing.T) {
	left := [nullifier.TreeSize]*big.Int{}
	right := [nullifier.TreeSize]*big.Int{}
	left[2], right[2] = big.NewInt(41), big.NewInt(73)
	assignment := &nullifierUnionCircuit{
		LeftRoot:   emulated.ValueOf[sw_bn254.ScalarField](nativeNullifierRoot(left)),
		RightRoot:  emulated.ValueOf[sw_bn254.ScalarField](nativeNullifierRoot(right)),
		MergedRoot: emulated.ValueOf[sw_bn254.ScalarField](nativeNullifierRoot(left)),
	}
	assignment.Left, _ = assignNullifierLeaves(left)
	assignment.Right, _ = assignNullifierLeaves(right)
	if err := test.IsSolved(&nullifierUnionCircuit{}, assignment, ecc.BW6_761.ScalarField()); err == nil {
		t.Fatal("duplicate nullifier slot unexpectedly satisfied the union")
	}

	right[2] = nil
	assignment.Right, _ = assignNullifierLeaves(right)
	assignment.RightRoot = emulated.ValueOf[sw_bn254.ScalarField](nativeNullifierRoot(right))
	assignment.MergedRoot = emulated.ValueOf[sw_bn254.ScalarField](big.NewInt(123))
	if err := test.IsSolved(&nullifierUnionCircuit{}, assignment, ecc.BW6_761.ScalarField()); err == nil {
		t.Fatal("forged union root unexpectedly satisfied the union")
	}
}
