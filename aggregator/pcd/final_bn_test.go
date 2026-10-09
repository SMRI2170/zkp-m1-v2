package pcd

import (
	"math/big"
	"os"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bw6761"
	"github.com/consensys/gnark/std/math/emulated"
	"github.com/consensys/gnark/test"
)

// This small test root stands in for a released NodeBW circuit. It lets the
// finalizer regression test exercise a real BW6 Groth16 proof and pinned key
// without running the full leaf-to-PCD setup ceremony.
type finalBNTestRootCircuit struct {
	State [stateWidth]frontend.Variable `gnark:",public"`
}

func (c *finalBNTestRootCircuit) Define(api frontend.API) error {
	api.AssertIsEqual(c.State[stateVersion], 1)
	return nil
}

func TestFinalBNWrapsPinnedBW6RootInV1Order(t *testing.T) {
	innerCCS, err := frontend.Compile(ecc.BW6_761.ScalarField(), r1cs.NewBuilder, &finalBNTestRootCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	innerPK, innerVK, err := groth16.Setup(innerCCS)
	if err != nil {
		t.Fatal(err)
	}

	minimumQuorum := uint32(2)
	policy, err := FinalPolicyCommitment(minimumQuorum)
	if err != nil {
		t.Fatal(err)
	}
	droneID := big.NewInt(424242)
	timeBucket := big.NewInt(100001)
	memberRoot := big.NewInt(999)
	nullifierRoot := big.NewInt(777)
	consistentCount := big.NewInt(2)
	suspiciousCount := big.NewInt(1)
	rootState := [stateWidth]frontend.Variable{
		1,
		droneID,
		timeBucket,
		policy,
		memberRoot,
		emptyNullifierRoot(),
		nullifierRoot,
		consistentCount,
		suspiciousCount,
	}
	innerWitness, err := frontend.NewWitness(&finalBNTestRootCircuit{State: rootState}, ecc.BW6_761.ScalarField())
	if err != nil {
		t.Fatal(err)
	}
	rootProof, err := groth16.Prove(innerCCS, innerPK, innerWitness)
	if err != nil {
		t.Fatal(err)
	}
	rootPublic, err := innerWitness.Public()
	if err != nil {
		t.Fatal(err)
	}
	finalState := [publicInputCountV1]*big.Int{
		big.NewInt(1), droneID, timeBucket, policy, memberRoot, nullifierRoot,
		consistentCount, suspiciousCount, big.NewInt(int64(VerdictTrusted)),
	}
	assignment, err := FinalBNAssignment(rootProof, rootPublic, finalState, minimumQuorum)
	if err != nil {
		t.Fatal(err)
	}
	circuit, err := NewFinalBN(innerCCS, innerVK)
	if err != nil {
		t.Fatal(err)
	}
	if err := test.IsSolved(circuit, assignment, ecc.BN254.ScalarField()); err != nil {
		t.Fatalf("valid BW6 root did not satisfy FinalBN: %v", err)
	}

	wrongVerdict := *assignment
	wrongVerdict.Verdict = int(VerdictSpoofSuspected)
	assertFinalBNRejects(t, circuit, &wrongVerdict)

	wrongNullifierRoot := *assignment
	wrongNullifierRoot.NullifierRoot = big.NewInt(778)
	assertFinalBNRejects(t, circuit, &wrongNullifierRoot)

	wrongInitialRoot := *assignment
	wrongInitialRoot.RootState.Public = append([]emulated.Element[sw_bw6761.ScalarField](nil), assignment.RootState.Public...)
	wrongInitialRoot.RootState.Public[stateOldNullifierRoot] = emulated.ValueOf[sw_bw6761.ScalarField](big.NewInt(1))
	assertFinalBNRejects(t, circuit, &wrongInitialRoot)
}

func assertFinalBNRejects(t *testing.T, circuit, assignment *FinalBN) {
	t.Helper()
	if err := test.IsSolved(circuit, assignment, ecc.BN254.ScalarField()); err == nil {
		t.Fatal("invalid FinalBN assignment unexpectedly satisfied the circuit")
	}
}

func TestFinalBNAssignmentRejectsInvalidPublicStatement(t *testing.T) {
	state := [publicInputCountV1]*big.Int{
		big.NewInt(1), big.NewInt(424242), big.NewInt(100001), big.NewInt(0),
		big.NewInt(999), big.NewInt(777), big.NewInt(2), big.NewInt(1), big.NewInt(1),
	}
	if _, err := FinalBNAssignment(nil, nil, state, 2); err == nil {
		t.Fatal("expected mismatched policy commitment to be rejected")
	}
	if _, err := FinalBNAssignment(nil, nil, state, 0); err == nil {
		t.Fatal("expected zero minimum quorum to be rejected")
	}
}

func TestFinalBNCompilesToNinePublicInputs(t *testing.T) {
	if os.Getenv("RUN_FINAL_BN_COMPILE") != "1" {
		t.Skip("set RUN_FINAL_BN_COMPILE=1 to run the expensive recursive-circuit compile check")
	}
	innerCCS, err := frontend.Compile(ecc.BW6_761.ScalarField(), r1cs.NewBuilder, &finalBNTestRootCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	_, innerVK, err := groth16.Setup(innerCCS)
	if err != nil {
		t.Fatal(err)
	}
	circuit, err := NewFinalBN(innerCCS, innerVK)
	if err != nil {
		t.Fatal(err)
	}
	finalCCS, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, circuit)
	if err != nil {
		t.Fatalf("compile FinalBN over BN254: %v", err)
	}
	if got := finalCCS.GetNbPublicVariables() - 1; got != publicInputCountV1 {
		t.Fatalf("FinalBN exposes %d public inputs, want %d", got, publicInputCountV1)
	}
}
