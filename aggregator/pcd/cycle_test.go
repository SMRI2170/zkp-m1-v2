// Package pcd contains production-oriented recursion experiments.  This test
// is intentionally small: it proves that the curve-cycle primitive required by
// final-attestation-v1 works with the pinned gnark version before the much
// larger leaf/nullifier circuits are placed inside it.
package pcd

import (
	"math/big"
	"os"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/constraint"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	"github.com/consensys/gnark/std/math/emulated"
	"github.com/consensys/gnark/test"

	"uav/aggregator/membership"
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
}

type bridgeLeafCircuit struct {
	Signals [leafPublicSignalCount]frontend.Variable `gnark:",public"`
	Secret  frontend.Variable
}

func (c *bridgeLeafCircuit) Define(api frontend.API) error {
	// A minimal satisfiable BN254 leaf with the production public-signal shape.
	// The actual Remote ID and RSSI constraints remain in the Circom leaf and
	// are connected through this same fixed-key interface in Issue #4.
	api.AssertIsEqual(c.Signals[leafWithin30AndDetected], 1)
	api.AssertIsEqual(c.Signals[leafDroneAuthOK], 1)
	return nil
}

func TestBridgeBWRequiresCanonicalLeafLayout(t *testing.T) {
	ccs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &bridgeLeafCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	_, vk, err := groth16.Setup(ccs)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := NewBridgeBW(ccs, vk); err != nil {
		t.Fatalf("expected canonical 18-signal leaf to be accepted: %v", err)
	}

	wrongCCS, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &leafCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	_, wrongVK, err := groth16.Setup(wrongCCS)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := NewBridgeBW(wrongCCS, wrongVK); err == nil {
		t.Fatal("expected BridgeBW to reject a leaf with the wrong public-signal layout")
	}
}

type mimcBN254Circuit struct {
	A      emulated.Element[sw_bn254.ScalarField]
	B      emulated.Element[sw_bn254.ScalarField]
	Result emulated.Element[sw_bn254.ScalarField] `gnark:",public"`
}

func (c *mimcBN254Circuit) Define(api frontend.API) error {
	f, err := emulated.NewField[sw_bn254.ScalarField](api)
	if err != nil {
		return err
	}
	f.AssertIsEqual(mimcBN254(f, &c.A, &c.B), &c.Result)
	return nil
}

func TestEmulatedBN254MiMCMatchesMembershipRoot(t *testing.T) {
	a, b := big.NewInt(123), big.NewInt(456)
	expected := membership.MimcHash(a, b)
	assignment := &mimcBN254Circuit{
		A:      emulated.ValueOf[sw_bn254.ScalarField](a),
		B:      emulated.ValueOf[sw_bn254.ScalarField](b),
		Result: emulated.ValueOf[sw_bn254.ScalarField](expected),
	}
	assert := test.NewAssert(t)
	assert.SolvingSucceeded(&mimcBN254Circuit{}, assignment, test.WithCurves(ecc.BW6_761), test.NoFuzzing())
	assignment.Result = emulated.ValueOf[sw_bn254.ScalarField](big.NewInt(1))
	assert.SolvingFailed(&mimcBN254Circuit{}, assignment, test.WithCurves(ecc.BW6_761), test.NoFuzzing())
}

func (c *orderedLeafCircuit) Define(api frontend.API) error {
	api.AssertIsEqual(c.Version, 1)
	api.AssertIsEqual(c.OldRoot, emptyNullifierRoot())
	api.AssertIsEqual(api.Add(c.Consistent, c.Suspicious), 1)
	return nil
}
func orderedProof(t *testing.T, ccs constraint.ConstraintSystem, pk groth16.ProvingKey, field *big.Int, s [stateWidth]*big.Int) (witness.Witness, groth16.Proof) {
	t.Helper()
	a := &orderedLeafCircuit{Version: s[0], Drone: s[1], Bucket: s[2], Policy: s[3], Member: s[4], OldRoot: s[5], NewRoot: s[6], Consistent: s[7], Suspicious: s[8]}
	w, err := frontend.NewWitness(a, field)
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

func observerNullifierSet(index int, value int64) NullifierLeaves {
	var leaves NullifierLeaves
	leaves[index] = big.NewInt(value)
	return leaves
}

func mergedObserverState(left, right NullifierLeaves, consistent, suspicious int64) [stateWidth]*big.Int {
	merged := left
	for i, value := range right {
		if value != nil {
			if merged[i] != nil {
				merged[i] = new(big.Int).Add(merged[i], value)
			} else {
				merged[i] = new(big.Int).Set(value)
			}
		}
	}
	return [stateWidth]*big.Int{
		big.NewInt(1), big.NewInt(9), big.NewInt(10), big.NewInt(11), big.NewInt(12),
		new(big.Int).Set(emptyNullifierRoot()), nativeNullifierRoot(merged),
		big.NewInt(consistent), big.NewInt(suspicious),
	}
}

type encodedChildCircuit struct {
	State [encodedStateWidth]frontend.Variable `gnark:",public"`
}

func (c *encodedChildCircuit) Define(api frontend.API) error {
	api.AssertIsEqual(c.State[0], 1)
	return nil
}

func encodedStateProof(t *testing.T, ccs constraint.ConstraintSystem, pk groth16.ProvingKey, state [stateWidth]*big.Int) (witness.Witness, groth16.Proof) {
	t.Helper()
	encoded, err := EncodeState(state)
	if err != nil {
		t.Fatal(err)
	}
	a := &encodedChildCircuit{}
	for i := range encoded {
		a.State[i] = encoded[i]
	}
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
func TestNodeBWBinaryUnionOfDisjointChildren(t *testing.T) {
	templateLeaf := &encodedChildCircuit{}
	ccs, err := frontend.Compile(ecc.BLS12_377.ScalarField(), r1cs.NewBuilder, templateLeaf)
	if err != nil {
		t.Fatal(err)
	}
	pk, vk, err := groth16.Setup(ccs)
	if err != nil {
		t.Fatal(err)
	}
	leftSet, rightSet := observerNullifierSet(2, 41), observerNullifierSet(11, 73)
	left := mergedObserverState(leftSet, NullifierLeaves{}, 1, 0)
	right := mergedObserverState(NullifierLeaves{}, rightSet, 0, 1)
	lw, lp := encodedStateProof(t, ccs, pk, left)
	rw, rp := encodedStateProof(t, ccs, pk, right)
	node, err := NewNodeBW(ccs, vk)
	if err != nil {
		t.Fatal(err)
	}
	out := mergedObserverState(leftSet, rightSet, 1, 1)
	setWitness := NullifierSetWitness{Left: leftSet, Right: rightSet}
	a, err := NodeBWAssignment(lp, lw, rp, rw, out, setWitness)
	if err != nil {
		t.Fatal(err)
	}
	if err := test.IsSolved(node, a, ecc.BW6_761.ScalarField()); err != nil {
		t.Fatalf("independent disjoint observer trees did not merge: %v", err)
	}

	bad := *a
	bad.NewNullifierRoot = new(big.Int).Add(out[stateNewNullifierRoot], big.NewInt(1))
	if err := test.IsSolved(node, &bad, ecc.BW6_761.ScalarField()); err == nil {
		t.Fatal("wrong merged nullifier root unexpectedly satisfied NodeBW")
	}

	duplicateSet := observerNullifierSet(2, 73)
	duplicateRight := mergedObserverState(NullifierLeaves{}, duplicateSet, 0, 1)
	dw, dp := encodedStateProof(t, ccs, pk, duplicateRight)
	duplicateMerged := mergedObserverState(leftSet, duplicateSet, 1, 1)
	duplicateAssignment, err := NodeBWAssignment(lp, lw, dp, dw, duplicateMerged,
		NullifierSetWitness{Left: leftSet, Right: duplicateSet})
	if err != nil {
		t.Fatal(err)
	}
	if err := test.IsSolved(node, duplicateAssignment, ecc.BW6_761.ScalarField()); err == nil {
		t.Fatal("duplicate observer slot unexpectedly satisfied NodeBW")
	}

	mixedSession := right
	mixedSession[stateDrone] = big.NewInt(99)
	mixedWitness, mixedProof := encodedStateProof(t, ccs, pk, mixedSession)
	mixedAssignment, err := NodeBWAssignment(lp, lw, mixedProof, mixedWitness, out, setWitness)
	if err != nil {
		t.Fatal(err)
	}
	if err := test.IsSolved(node, mixedAssignment, ecc.BW6_761.ScalarField()); err == nil {
		t.Fatal("different-session child unexpectedly satisfied NodeBW")
	}

	wrongCountSet := observerNullifierSet(2, 41)
	wrongCountSet[3] = big.NewInt(97)
	wrongCountState := mergedObserverState(wrongCountSet, NullifierLeaves{}, 1, 0)
	wrongCountWitness, wrongCountProof := encodedStateProof(t, ccs, pk, wrongCountState)
	wrongCountOut := mergedObserverState(wrongCountSet, rightSet, 1, 1)
	wrongCountAssignment, err := NodeBWAssignment(wrongCountProof, wrongCountWitness, rp, rw,
		wrongCountOut, NullifierSetWitness{Left: wrongCountSet, Right: rightSet})
	if err != nil {
		t.Fatal(err)
	}
	if err := test.IsSolved(node, wrongCountAssignment, ecc.BW6_761.ScalarField()); err == nil {
		t.Fatal("child count inconsistent with occupied nullifier slots unexpectedly satisfied NodeBW")
	}
}

func TestNodeBLSBinaryUnionOfDisjointChildren(t *testing.T) {
	if os.Getenv("RUN_RECURSIVE_PCD_HEAVY") != "1" {
		t.Skip("set RUN_RECURSIVE_PCD_HEAVY=1 to run the BLS12-377 recursive verification integration test")
	}
	templateLeaf := &orderedLeafCircuit{}
	ccs, err := frontend.Compile(ecc.BW6_761.ScalarField(), r1cs.NewBuilder, templateLeaf)
	if err != nil {
		t.Fatal(err)
	}
	pk, vk, err := groth16.Setup(ccs)
	if err != nil {
		t.Fatal(err)
	}
	leftSet, rightSet := observerNullifierSet(2, 41), observerNullifierSet(11, 73)
	left := mergedObserverState(leftSet, NullifierLeaves{}, 1, 0)
	right := mergedObserverState(NullifierLeaves{}, rightSet, 0, 1)
	lw, lp := orderedProof(t, ccs, pk, ecc.BW6_761.ScalarField(), left)
	rw, rp := orderedProof(t, ccs, pk, ecc.BW6_761.ScalarField(), right)
	node, err := NewNodeBLS(ccs, vk)
	if err != nil {
		t.Fatal(err)
	}
	out := mergedObserverState(leftSet, rightSet, 1, 1)
	a, err := NodeBLSAssignment(lp, lw, rp, rw, out, NullifierSetWitness{Left: leftSet, Right: rightSet})
	if err != nil {
		t.Fatal(err)
	}
	if err := test.IsSolved(node, a, ecc.BLS12_377.ScalarField()); err != nil {
		t.Fatalf("independent disjoint observer trees did not merge in NodeBLS: %v", err)
	}

	bad := *a
	bad.State[4*bn254LimbCount] = big.NewInt(99)
	if err := test.IsSolved(node, &bad, ecc.BLS12_377.ScalarField()); err == nil {
		t.Fatal("altered memberRoot unexpectedly satisfied NodeBLS")
	}

	mixedSession := right
	mixedSession[stateBucket] = big.NewInt(11)
	mixedWitness, mixedProof := orderedProof(t, ccs, pk, ecc.BW6_761.ScalarField(), mixedSession)
	mixedAssignment, err := NodeBLSAssignment(lp, lw, mixedProof, mixedWitness, out,
		NullifierSetWitness{Left: leftSet, Right: rightSet})
	if err != nil {
		t.Fatal(err)
	}
	if err := test.IsSolved(node, mixedAssignment, ecc.BLS12_377.ScalarField()); err == nil {
		t.Fatal("different-session child unexpectedly satisfied NodeBLS")
	}
}
