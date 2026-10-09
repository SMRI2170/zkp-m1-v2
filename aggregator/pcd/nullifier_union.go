package pcd

import (
	"fmt"
	"math/big"

	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	"github.com/consensys/gnark/std/math/emulated"

	"uav/aggregator/nullifier"
)

// NullifierLeaves is the private, fixed-size opening of a session's
// registered-observer participation tree. Values are zero for nonparticipants
// and the session nullifier for participants. The vector is never public.
type NullifierLeaves [nullifier.TreeSize]*big.Int

// NullifierSetWitness contains private openings for independently accumulated
// child states. A single observer report is exactly one occupied slot.
type NullifierSetWitness struct {
	Left  NullifierLeaves
	Right NullifierLeaves
}

type NullifierSetCounts struct {
	Left  frontend.Variable
	Right frontend.Variable
	Total frontend.Variable
}

// assertNullifierSetUnion proves that two independently accumulated child
// trees share the same initial root, contain no overlapping occupied index,
// and combine to one canonical union root. This is intentionally an expensive
// fixed-capacity PoC gadget; it does not accept a relayer-claimed hash(left,
// right) as a substitute for the actual set union.
func assertNullifierSetUnion(
	api frontend.API,
	f *emulated.Field[sw_bn254.ScalarField],
	leftLeaves, rightLeaves [nullifier.TreeSize]emulated.Element[sw_bn254.ScalarField],
	leftRoot, rightRoot, mergedRoot *emulated.Element[sw_bn254.ScalarField],
) (NullifierSetCounts, error) {
	var counts NullifierSetCounts
	if f == nil || leftRoot == nil || rightRoot == nil || mergedRoot == nil {
		return counts, fmt.Errorf("nullifier union requires a BN254 field and three roots")
	}
	f.AssertIsInRange(leftRoot)
	f.AssertIsInRange(rightRoot)
	f.AssertIsInRange(mergedRoot)
	f.AssertIsEqual(emulatedNullifierRoot(api, f, leftLeaves), leftRoot)
	f.AssertIsEqual(emulatedNullifierRoot(api, f, rightLeaves), rightRoot)

	counts.Left = 0
	counts.Right = 0
	var merged [nullifier.TreeSize]emulated.Element[sw_bn254.ScalarField]
	for i := 0; i < nullifier.TreeSize; i++ {
		left := f.ReduceStrict(&leftLeaves[i])
		right := f.ReduceStrict(&rightLeaves[i])
		// Nullifiers are nonzero. Their product can be zero only if at least
		// one child has an empty slot at this registered-observer index.
		f.AssertIsEqual(f.Mul(left, right), f.Zero())
		leftPresent := api.Sub(1, f.IsZero(left))
		rightPresent := api.Sub(1, f.IsZero(right))
		counts.Left = api.Add(counts.Left, leftPresent)
		counts.Right = api.Add(counts.Right, rightPresent)
		merged[i] = *f.Add(left, right)
	}
	counts.Total = api.Add(counts.Left, counts.Right)
	f.AssertIsEqual(emulatedNullifierRoot(api, f, merged), mergedRoot)
	return counts, nil
}

func assignNullifierLeaves(values NullifierLeaves) ([nullifier.TreeSize]emulated.Element[sw_bn254.ScalarField], error) {
	var leaves [nullifier.TreeSize]emulated.Element[sw_bn254.ScalarField]
	for i, value := range values {
		if value == nil {
			leaves[i] = emulated.ValueOf[sw_bn254.ScalarField](0)
			continue
		}
		if value.Sign() < 0 || value.Cmp(bn254ScalarModulus) >= 0 {
			return leaves, fmt.Errorf("nullifier leaf %d is not a canonical BN254 scalar", i)
		}
		leaves[i] = emulated.ValueOf[sw_bn254.ScalarField](value)
	}
	return leaves, nil
}

func emulatedNullifierRoot(
	api frontend.API,
	f *emulated.Field[sw_bn254.ScalarField],
	leaves [nullifier.TreeSize]emulated.Element[sw_bn254.ScalarField],
) *emulated.Element[sw_bn254.ScalarField] {
	level := make([]*emulated.Element[sw_bn254.ScalarField], nullifier.TreeSize)
	for i := range leaves {
		level[i] = f.ReduceStrict(&leaves[i])
	}
	for len(level) > 1 {
		next := make([]*emulated.Element[sw_bn254.ScalarField], len(level)/2)
		for i := range next {
			next[i] = mimcBN254(f, level[2*i], level[2*i+1])
		}
		level = next
	}
	return level[0]
}
