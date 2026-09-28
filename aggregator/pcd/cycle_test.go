// Package pcd contains production-oriented recursion experiments.  This test
// is intentionally small: it proves that the curve-cycle primitive required by
// final-attestation-v1 works with the pinned gnark version before the much
// larger leaf/nullifier circuits are placed inside it.
package pcd

import (
	"math/big"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/constraint"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/test"
)

// leafCircuit is a deliberately tiny valid proof statement.  Replacing it with
// the attestation bridge is Issue #4 work; keeping this relation small makes
// failures in the curve-cycle plumbing unambiguous.
type leafCircuit struct {
	Secret frontend.Variable
	Public frontend.Variable `gnark:",public"`
}

func (c *leafCircuit) Define(api frontend.API) error {
	api.AssertIsEqual(api.Mul(c.Secret, c.Secret), c.Public)
	return nil
}

func makeBLSLeafProof(t *testing.T) (constraint.ConstraintSystem, groth16.VerifyingKey, witness.Witness, groth16.Proof) {
	t.Helper()
	ccs, err := frontend.Compile(ecc.BLS12_377.ScalarField(), r1cs.NewBuilder, &leafCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	pk, vk, err := groth16.Setup(ccs)
	if err != nil {
		t.Fatal(err)
	}
	w, err := frontend.NewWitness(&leafCircuit{Secret: 7, Public: 49}, ecc.BLS12_377.ScalarField())
	if err != nil {
		t.Fatal(err)
	}
	p, err := groth16.Prove(ccs, pk, w)
	if err != nil {
		t.Fatal(err)
	}
	pub, err := w.Public()
	if err != nil {
		t.Fatal(err)
	}
	if err := groth16.Verify(p, vk, pub); err != nil {
		t.Fatal(err)
	}
	return ccs, vk, pub, p
}

func TestBLS12ProofCanBeVerifiedInsideBW6Circuit(t *testing.T) {
	innerCCS, innerVK, innerPublicWitness, innerProof := makeBLSLeafProof(t)
	template, err := NewPinnedBLS12ProofCircuit(innerCCS, innerVK)
	if err != nil {
		t.Fatal(err)
	}
	assignment, err := PinnedBLS12ProofAssignment(innerProof, innerPublicWitness)
	if err != nil {
		t.Fatal(err)
	}

	assert := test.NewAssert(t)
	assert.SolvingSucceeded(template, assignment, test.WithCurves(ecc.BW6_761), test.NoFuzzing())

	// A valid proof generated under another verification key must not be
	// accepted. This guards against accidentally turning the key into a
	// relayer-controlled recursive witness again.
	_, _, otherPublicWitness, otherProof := makeBLSLeafProof(t)
	otherAssignment, err := PinnedBLS12ProofAssignment(otherProof, otherPublicWitness)
	if err != nil {
		t.Fatal(err)
	}
	assert.SolvingFailed(template, otherAssignment, test.WithCurves(ecc.BW6_761), test.NoFuzzing())
}

type orderedLeafCircuit struct {
	Version, Drone, Bucket, Policy, Member, OldRoot, NewRoot, Consistent, Suspicious frontend.Variable `gnark:",public"`
	Nonce                                                                            frontend.Variable
}

func (c *orderedLeafCircuit) Define(api frontend.API) error {
	api.AssertIsEqual(c.Version, 1)
	api.AssertIsEqual(c.NewRoot, api.Add(c.OldRoot, c.Nonce))
	api.AssertIsEqual(api.Add(c.Consistent, c.Suspicious), 1)
	return nil
}
func orderedProof(t *testing.T, ccs constraint.ConstraintSystem, pk groth16.ProvingKey, s [stateWidth]*big.Int, nonce int) (witness.Witness, groth16.Proof) {
	t.Helper()
	a := &orderedLeafCircuit{Version: s[0], Drone: s[1], Bucket: s[2], Policy: s[3], Member: s[4], OldRoot: s[5], NewRoot: s[6], Consistent: s[7], Suspicious: s[8], Nonce: nonce}
	w, err := frontend.NewWitness(a, ecc.BLS12_377.ScalarField())
	if err != nil {
		t.Fatal(err)
	}
	p, err := groth16.Prove(ccs, pk, w)
	if err != nil {
		t.Fatal(err)
	}
	pub, err := w.Public()
	if err != nil {
		t.Fatal(err)
	}
	return pub, p
}
func TestNodeBWMergesTwoPinnedOrderedChildren(t *testing.T) {
	templateLeaf := &orderedLeafCircuit{}
	ccs, err := frontend.Compile(ecc.BLS12_377.ScalarField(), r1cs.NewBuilder, templateLeaf)
	if err != nil {
		t.Fatal(err)
	}
	pk, vk, err := groth16.Setup(ccs)
	if err != nil {
		t.Fatal(err)
	}
	left := [stateWidth]*big.Int{big.NewInt(1), big.NewInt(9), big.NewInt(10), big.NewInt(11), big.NewInt(12), big.NewInt(100), big.NewInt(107), big.NewInt(1), big.NewInt(0)}
	right := [stateWidth]*big.Int{big.NewInt(1), big.NewInt(9), big.NewInt(10), big.NewInt(11), big.NewInt(12), big.NewInt(107), big.NewInt(112), big.NewInt(0), big.NewInt(1)}
	lw, lp := orderedProof(t, ccs, pk, left, 7)
	rw, rp := orderedProof(t, ccs, pk, right, 5)
	node, err := NewNodeBW(ccs, vk)
	if err != nil {
		t.Fatal(err)
	}
	out := [stateWidth]*big.Int{big.NewInt(1), big.NewInt(9), big.NewInt(10), big.NewInt(11), big.NewInt(12), big.NewInt(100), big.NewInt(112), big.NewInt(1), big.NewInt(1)}
	a, err := NodeBWAssignment(lp, lw, rp, rw, out)
	if err != nil {
		t.Fatal(err)
	}
	assert := test.NewAssert(t)
	assert.SolvingSucceeded(node, a, test.WithCurves(ecc.BW6_761), test.NoFuzzing())
	bad := *a
	bad.NewNullifierRoot = big.NewInt(113)
	assert.SolvingFailed(node, &bad, test.WithCurves(ecc.BW6_761), test.NoFuzzing())
}
