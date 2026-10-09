package pcd

import (
	"math/big"
	"os"
	"strings"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
)

func validFinalStatementV2(t *testing.T) [publicInputCountV2]*big.Int {
	t.Helper()
	profileSetRoot := big.NewInt(17)
	policy, err := FinalPolicyCommitmentV2(2, profileSetRoot)
	if err != nil {
		t.Fatal(err)
	}
	return [publicInputCountV2]*big.Int{
		big.NewInt(FinalPolicyV2Version), big.NewInt(424242), big.NewInt(100001), policy,
		profileSetRoot, big.NewInt(999), big.NewInt(777), big.NewInt(2), big.NewInt(1),
		big.NewInt(int64(VerdictNoInconsistencyObserved)),
	}
}

func TestFinalBNV2AssignmentSeparatesProtocolAndPolicy(t *testing.T) {
	state := validFinalStatementV2(t)
	state[0] = big.NewInt(FinalPolicyVersion)
	if _, err := FinalBNV2Assignment(nil, nil, state, 2); err == nil || !strings.Contains(err.Error(), "protocolVersion") {
		t.Fatalf("expected V2 finalizer to reject V1 state, got %v", err)
	}

	state = validFinalStatementV2(t)
	state[3] = new(big.Int).Set(state[3])
	state[3].Add(state[3], big.NewInt(1))
	if _, err := FinalBNV2Assignment(nil, nil, state, 2); err == nil || !strings.Contains(err.Error(), "policyCommitment") {
		t.Fatalf("expected V2 finalizer to reject an unbound profile/quorum, got %v", err)
	}
}

func TestFinalBNV2AssignmentValidatesPublicStatementBeforeProof(t *testing.T) {
	state := validFinalStatementV2(t)
	_, err := FinalBNV2Assignment(nil, nil, state, 2)
	if err == nil || !strings.Contains(err.Error(), "translate BW6 V2 root proof") {
		t.Fatalf("valid V2 public statement should pass host checks before missing proof is reported, got %v", err)
	}

	state[4] = new(big.Int).Set(bn254ScalarModulus)
	if _, err := FinalBNV2Assignment(nil, nil, state, 2); err == nil || !strings.Contains(err.Error(), "canonical BN254 scalar") {
		t.Fatalf("expected noncanonical profile-set root to be rejected, got %v", err)
	}

	state = validFinalStatementV2(t)
	state[4] = new(big.Int).Add(new(big.Int).Lsh(big.NewInt(1), 32), big.NewInt(17))
	state[3], err = FinalPolicyCommitmentV2(2, state[4])
	if err != nil {
		t.Fatal(err)
	}
	if _, err := FinalBNV2Assignment(nil, nil, state, 2); err == nil || !strings.Contains(err.Error(), "translate BW6 V2 root proof") {
		t.Fatalf("canonical profile-set root above uint32 should pass host checks, got %v", err)
	}
}

func TestValidatePCDProtocolVersion(t *testing.T) {
	for _, version := range []uint32{uint32(FinalPolicyVersion), uint32(FinalPolicyV2Version)} {
		if err := validatePCDProtocolVersion(version); err != nil {
			t.Errorf("supported version %d rejected: %v", version, err)
		}
	}
	for _, version := range []uint32{0, 3} {
		if err := validatePCDProtocolVersion(version); err == nil {
			t.Errorf("unsupported version %d accepted", version)
		}
	}
	if _, err := NewNodeBLSForProtocol(nil, nil, 3); err == nil {
		t.Error("NodeBLS accepted an unsupported protocol version")
	}
	if _, err := NewNodeBWForProtocol(nil, nil, 3); err == nil {
		t.Error("NodeBW accepted an unsupported protocol version")
	}
	if _, err := NewPromoteBLSForProtocol(nil, nil, 3); err == nil {
		t.Error("PromoteBLS accepted an unsupported protocol version")
	}
}

func TestRecursiveConstructorsPinBothProtocolVersions(t *testing.T) {
	bwCCS, err := frontend.Compile(ecc.BW6_761.ScalarField(), r1cs.NewBuilder, &orderedLeafCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	_, bwVK, err := groth16.Setup(bwCCS)
	if err != nil {
		t.Fatal(err)
	}
	nodeBLSV1, err := NewNodeBLS(bwCCS, bwVK)
	if err != nil {
		t.Fatal(err)
	}
	nodeBLSV2, err := NewNodeBLSForProtocol(bwCCS, bwVK, uint32(FinalPolicyV2Version))
	if err != nil {
		t.Fatal(err)
	}
	if nodeBLSV1.protocolVersion != uint32(FinalPolicyVersion) || nodeBLSV2.protocolVersion != uint32(FinalPolicyV2Version) {
		t.Fatalf("NodeBLS constructors did not pin versions: V1=%d V2=%d", nodeBLSV1.protocolVersion, nodeBLSV2.protocolVersion)
	}

	blsCCS, err := frontend.Compile(ecc.BLS12_377.ScalarField(), r1cs.NewBuilder, &encodedChildCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	_, blsVK, err := groth16.Setup(blsCCS)
	if err != nil {
		t.Fatal(err)
	}
	nodeBWV1, err := NewNodeBW(blsCCS, blsVK)
	if err != nil {
		t.Fatal(err)
	}
	nodeBWV2, err := NewNodeBWForProtocol(blsCCS, blsVK, uint32(FinalPolicyV2Version))
	if err != nil {
		t.Fatal(err)
	}
	if nodeBWV1.protocolVersion != uint32(FinalPolicyVersion) || nodeBWV2.protocolVersion != uint32(FinalPolicyV2Version) {
		t.Fatalf("NodeBW constructors did not pin versions: V1=%d V2=%d", nodeBWV1.protocolVersion, nodeBWV2.protocolVersion)
	}
	promoteV2, err := NewPromoteBLSForProtocol(bwCCS, bwVK, uint32(FinalPolicyV2Version))
	if err != nil {
		t.Fatal(err)
	}
	if promoteV2.protocolVersion != uint32(FinalPolicyV2Version) {
		t.Fatalf("PromoteBLS did not pin V2, got %d", promoteV2.protocolVersion)
	}
}

type finalBNV2TestRootCircuit struct {
	State [stateWidth]frontend.Variable `gnark:",public"`
}

func (c *finalBNV2TestRootCircuit) Define(api frontend.API) error {
	api.AssertIsEqual(c.State[stateVersion], FinalPolicyV2Version)
	return nil
}

func TestFinalBNV2CompilesToTenPublicInputs(t *testing.T) {
	if os.Getenv("RUN_FINAL_BN_V2_COMPILE") != "1" {
		t.Skip("set RUN_FINAL_BN_V2_COMPILE=1 to run the expensive recursive FinalBNV2 compile check")
	}
	innerCCS, err := frontend.Compile(ecc.BW6_761.ScalarField(), r1cs.NewBuilder, &finalBNV2TestRootCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	_, innerVK, err := groth16.Setup(innerCCS)
	if err != nil {
		t.Fatal(err)
	}
	circuit, err := NewFinalBNV2(innerCCS, innerVK)
	if err != nil {
		t.Fatal(err)
	}
	finalCCS, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, circuit)
	if err != nil {
		t.Fatalf("compile FinalBNV2 over BN254: %v", err)
	}
	if got := finalCCS.GetNbPublicVariables() - 1; got != publicInputCountV2 {
		t.Fatalf("FinalBNV2 exposes %d public inputs, want %d", got, publicInputCountV2)
	}
}
