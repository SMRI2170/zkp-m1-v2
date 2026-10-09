package pcd

import (
	"os"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
)

type bridgeBWV2CompileLeaf struct {
	Signals [leafPublicSignalCountV2]frontend.Variable `gnark:",public"`
}

func (c *bridgeBWV2CompileLeaf) Define(api frontend.API) error {
	api.AssertIsEqual(c.Signals[leafObservationEligibleV2], 1)
	return nil
}

func TestBridgeBWV2ConstructorRequires8SignalLeaf(t *testing.T) {
	leafCCS, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &bridgeBWV2CompileLeaf{})
	if err != nil {
		t.Fatal(err)
	}
	leafPK, leafVK, err := groth16.Setup(leafCCS)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := NewBridgeBWV2(leafCCS, leafVK); err != nil {
		t.Fatalf("V2 bridge rejected 8-signal leaf layout: %v", err)
	}
	assignment := &bridgeBWV2CompileLeaf{}
	for i := range assignment.Signals {
		assignment.Signals[i] = 0
	}
	assignment.Signals[leafObservationEligibleV2] = 1
	witness, err := frontend.NewWitness(assignment, ecc.BN254.ScalarField())
	if err != nil {
		t.Fatal(err)
	}
	proof, err := groth16.Prove(leafCCS, leafPK, witness)
	if err != nil {
		t.Fatal(err)
	}
	public, err := witness.Public()
	if err != nil {
		t.Fatal(err)
	}
	if _, err := NewBridgeBWV2FromSample(leafVK, proof, public); err != nil {
		t.Fatalf("sample V2 bridge rejected an 8-signal proof: %v", err)
	}
	if _, err := NewBridgeBW(leafCCS, leafVK); err == nil {
		t.Fatal("V1 bridge accepted the 8-signal V2 leaf layout")
	}
}

// This expensive compile-only check validates the entire BridgeBWV2.Define
// relation and 8-signal recursive verifier shape. The dummy leaf VK is only
// used for compile shape; actual Circom V2 VK import/shape is checked by the
// proof integration test. It does not run an outer setup or create a proof.
func TestBridgeBWV2CompileOnly(t *testing.T) {
	if os.Getenv("RUN_BRIDGE_BW6_COMPILE") != "1" {
		t.Skip("set RUN_BRIDGE_BW6_COMPILE=1 to compile the expensive V2 BW6 bridge")
	}
	leafCCS, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &bridgeBWV2CompileLeaf{})
	if err != nil {
		t.Fatal(err)
	}
	_, leafVK, err := groth16.Setup(leafCCS)
	if err != nil {
		t.Fatal(err)
	}
	bridge, err := NewBridgeBWV2(leafCCS, leafVK)
	if err != nil {
		t.Fatal(err)
	}
	ccs, err := frontend.Compile(ecc.BW6_761.ScalarField(), r1cs.NewBuilder, bridge)
	if err != nil {
		t.Fatalf("compile BridgeBWV2: %v", err)
	}
	t.Logf("BridgeBWV2 compiled with dummy 8-signal VK shape: %d constraints, %d public inputs", ccs.GetNbConstraints(), ccs.GetNbPublicVariables()-1)
}
