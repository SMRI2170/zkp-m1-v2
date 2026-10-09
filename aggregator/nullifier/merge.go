package nullifier

import (
	"fmt"

	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/hash/mimc"

	"uav/aggregator/membership"
)

// TreeSize is fixed by the protocol's current membership depth. A merge keeps
// the leaf values private; only the three roots are public.
const TreeSize = 1 << membership.Depth

// MergeCircuit proves a canonical union of two session-nullifier trees. It is
// intentionally different from a hash(leftRoot, rightRoot): the complete
// private leaf vectors are opened inside the circuit, each vector is bound to
// its child root, and no index may be nonzero in both children. The resulting
// root is consequently the set union, not a relayer-claimed value.
//
// The child roots are expected to be public state from recursively verified
// child proofs. The leaves never become public, so this does not disclose which
// registered devices participated.
type MergeCircuit struct {
	LeftRoot   frontend.Variable `gnark:",public"`
	RightRoot  frontend.Variable `gnark:",public"`
	MergedRoot frontend.Variable `gnark:",public"`

	LeftLeaves  [TreeSize]frontend.Variable
	RightLeaves [TreeSize]frontend.Variable
}

func (c *MergeCircuit) Define(api frontend.API) error {
	leftRoot, err := RootCircuit(api, c.LeftLeaves)
	if err != nil {
		return err
	}
	rightRoot, err := RootCircuit(api, c.RightLeaves)
	if err != nil {
		return err
	}
	api.AssertIsEqual(leftRoot, c.LeftRoot)
	api.AssertIsEqual(rightRoot, c.RightRoot)

	var merged [TreeSize]frontend.Variable
	for i := 0; i < TreeSize; i++ {
		// In a field, a*b == 0 means at least one operand is zero. This
		// rejects duplicate participation at the same registered index,
		// including a duplicate with a differently forged nullifier value.
		api.AssertIsEqual(api.Mul(c.LeftLeaves[i], c.RightLeaves[i]), 0)
		merged[i] = api.Add(c.LeftLeaves[i], c.RightLeaves[i])
	}
	mergedRoot, err := RootCircuit(api, merged)
	if err != nil {
		return err
	}
	api.AssertIsEqual(mergedRoot, c.MergedRoot)
	return nil
}

// RootCircuit computes the fixed-depth MiMC root of a complete session-nullifier
// leaf vector. Empty entries are zero and the caller must bind the result to a
// public or recursively verified root.
func RootCircuit(api frontend.API, leaves [TreeSize]frontend.Variable) (frontend.Variable, error) {
	level := make([]frontend.Variable, TreeSize)
	copy(level, leaves[:])
	for len(level) > 1 {
		next := make([]frontend.Variable, len(level)/2)
		for i := range next {
			h, err := mimc.NewMiMC(api)
			if err != nil {
				return nil, fmt.Errorf("new MiMC at tree level: %w", err)
			}
			h.Write(level[2*i], level[2*i+1])
			next[i] = h.Sum()
		}
		level = next
	}
	return level[0], nil
}
