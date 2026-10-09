package pcd

import (
	"math/big"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	"github.com/consensys/gnark/std/math/emulated"
	"github.com/consensys/gnark/test"
)

func TestFinalPolicyCommitmentMatchesCircomlibVector(t *testing.T) {
	got, err := FinalPolicyCommitment(2)
	if err != nil {
		t.Fatal(err)
	}
	const want = "1791950082637333959260344209857081584058079814184145123235554669090060789867"
	if got.String() != want {
		t.Fatalf("Poseidon policy commitment = %s, want Circomlib vector %s", got, want)
	}
	if _, err := FinalPolicyCommitment(0); err == nil {
		t.Fatal("zero quorum must not have a policy commitment")
	}
}

func TestFinalPolicyCommitmentV2MatchesCircomlibVector(t *testing.T) {
	profileRoot, _, err := buildCalibrationProfileSetV2([]*big.Int{big.NewInt(1)})
	if err != nil {
		t.Fatal(err)
	}
	got, err := FinalPolicyCommitmentV2(2, profileRoot)
	if err != nil {
		t.Fatal(err)
	}
	// Independent circomlibjs calculation over the fixed-depth MiMC profile-set root.
	const want = "9789051968892630107623809391183968942606057283531623332225214493598474215761"
	if got.String() != want {
		t.Fatalf("V2 policy commitment = %s for profile-set root %s, want independent Circomlib vector %s", got, profileRoot, want)
	}
	otherRoot, _, err := buildCalibrationProfileSetV2([]*big.Int{big.NewInt(2)})
	if err != nil {
		t.Fatal(err)
	}
	otherProfile, err := FinalPolicyCommitmentV2(2, otherRoot)
	if err != nil {
		t.Fatal(err)
	}
	otherQuorum, err := FinalPolicyCommitmentV2(3, profileRoot)
	if err != nil {
		t.Fatal(err)
	}
	if got.Cmp(otherProfile) == 0 || got.Cmp(otherQuorum) == 0 {
		t.Fatal("V2 policy commitment does not bind both profile-set root and quorum")
	}
	profileSetRoot, _, err := buildCalibrationProfileSetV2([]*big.Int{big.NewInt(1), big.NewInt(2)})
	if err != nil {
		t.Fatal(err)
	}
	profileSetRootReordered, _, err := buildCalibrationProfileSetV2([]*big.Int{big.NewInt(2), big.NewInt(1)})
	if err != nil {
		t.Fatal(err)
	}
	if profileSetRoot.Cmp(profileSetRootReordered) != 0 {
		t.Fatal("profile-set root depends on caller ordering")
	}
	setCommitment, err := FinalPolicyCommitmentV2(2, profileSetRoot)
	if err != nil {
		t.Fatal(err)
	}
	if setCommitment.Cmp(got) == 0 {
		t.Fatal("V2 policy commitment did not bind the entire profile set")
	}
	for _, invalidRoot := range []*big.Int{
		nil,
		big.NewInt(-1),
		new(big.Int).Set(bn254ScalarModulus),
	} {
		if _, err := FinalPolicyCommitmentV2(2, invalidRoot); err == nil {
			t.Fatalf("invalid calibration profile-set root %v was accepted", invalidRoot)
		}
	}
	if _, err := FinalPolicyCommitmentV2(0, profileRoot); err == nil {
		t.Fatal("zero quorum must not have a V2 policy commitment")
	}
}

func TestDeriveFinalVerdict(t *testing.T) {
	tests := []struct {
		name       string
		consistent uint32
		suspicious uint32
		quorum     uint32
		want       FinalVerdict
		wantErr    bool
	}{
		{name: "trusted", consistent: 2, suspicious: 1, quorum: 2, want: VerdictTrusted},
		{name: "spoof suspected", suspicious: 2, quorum: 2, want: VerdictSpoofSuspected},
		{name: "undetermined", consistent: 1, suspicious: 1, quorum: 2, want: VerdictUndetermined},
		{name: "conflicting", consistent: 2, suspicious: 2, quorum: 2, wantErr: true},
		{name: "zero quorum", consistent: 2, quorum: 0, wantErr: true},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, err := DeriveFinalVerdict(tc.consistent, tc.suspicious, tc.quorum)
			if (err != nil) != tc.wantErr {
				t.Fatalf("DeriveFinalVerdict error = %v, wantErr %t", err, tc.wantErr)
			}
			if err == nil && got != tc.want {
				t.Fatalf("DeriveFinalVerdict = %d, want %d", got, tc.want)
			}
		})
	}
}

func TestFinalVerdictV2LabelsDoNotClaimTrustOrAuthenticity(t *testing.T) {
	tests := []struct {
		verdict FinalVerdict
		want    string
	}{
		{VerdictUndetermined, "INSUFFICIENT_EVIDENCE"},
		{VerdictNoInconsistencyObserved, "NO_INCONSISTENCY_OBSERVED"},
		{VerdictSpoofSuspected, "POSITION_INCONSISTENCY_SUSPECTED"},
		{FinalVerdict(255), "INVALID_VERDICT"},
	}
	for _, tc := range tests {
		if got := FinalVerdictV2Label(tc.verdict); got != tc.want {
			t.Errorf("FinalVerdictV2Label(%d) = %q, want %q", tc.verdict, got, tc.want)
		}
	}
	if VerdictNoInconsistencyObserved != VerdictTrusted {
		t.Fatal("renaming the V2 label must not change the legacy numeric ABI value")
	}
}

func TestFinalVerdictCircuitBindsCommitmentCountsAndVerdict(t *testing.T) {
	commitment, err := FinalPolicyCommitment(2)
	if err != nil {
		t.Fatal(err)
	}
	circuit := &FinalVerdictCircuit{}
	valid := &FinalVerdictCircuit{
		PolicyCommitment: commitment,
		ConsistentCount:  2,
		SuspiciousCount:  1,
		Verdict:          int(VerdictTrusted),
		MinimumQuorum:    2,
	}
	if err := test.IsSolved(circuit, valid, ecc.BN254.ScalarField()); err != nil {
		t.Fatalf("valid trusted statement did not satisfy circuit: %v", err)
	}

	wrongVerdict := *valid
	wrongVerdict.Verdict = int(VerdictUndetermined)
	assertCircuitRejects(t, circuit, &wrongVerdict)

	wrongThreshold := *valid
	wrongThreshold.MinimumQuorum = 3
	assertCircuitRejects(t, circuit, &wrongThreshold)

	conflicting := *valid
	conflicting.ConsistentCount = 2
	conflicting.SuspiciousCount = 2
	conflicting.Verdict = int(VerdictTrusted)
	assertCircuitRejects(t, circuit, &conflicting)

	badWidth := *valid
	badWidth.ConsistentCount = new(big.Int).Lsh(big.NewInt(1), 32)
	assertCircuitRejects(t, circuit, &badWidth)
}

func TestFinalVerdictV2CircuitBindsProfileQuorumAndVersion(t *testing.T) {
	profileRoot, _, err := buildCalibrationProfileSetV2([]*big.Int{big.NewInt(1), big.NewInt(2)})
	if err != nil {
		t.Fatal(err)
	}
	otherRoot, _, err := buildCalibrationProfileSetV2([]*big.Int{big.NewInt(1)})
	if err != nil {
		t.Fatal(err)
	}
	commitment, err := FinalPolicyCommitmentV2(2, profileRoot)
	if err != nil {
		t.Fatal(err)
	}
	circuit := &FinalVerdictV2Circuit{}
	valid := &FinalVerdictV2Circuit{
		ProtocolVersion:           FinalPolicyV2Version,
		PolicyCommitment:          commitment,
		ConsistentCount:           2,
		SuspiciousCount:           1,
		Verdict:                   int(VerdictTrusted),
		MinimumQuorum:             2,
		CalibrationProfileSetRoot: profileRoot,
	}
	if err := test.IsSolved(circuit, valid, ecc.BN254.ScalarField()); err != nil {
		t.Fatalf("valid V2 final policy statement did not satisfy the circuit: %v", err)
	}

	wrongProfileSet := *valid
	wrongProfileSet.CalibrationProfileSetRoot = otherRoot
	assertV2CircuitRejects(t, circuit, &wrongProfileSet)
	wrongVersion := *valid
	wrongVersion.ProtocolVersion = FinalPolicyVersion
	assertV2CircuitRejects(t, circuit, &wrongVersion)
	wrongQuorum := *valid
	wrongQuorum.MinimumQuorum = 3
	assertV2CircuitRejects(t, circuit, &wrongQuorum)
	conflicting := *valid
	conflicting.ConsistentCount = 2
	conflicting.SuspiciousCount = 2
	assertV2CircuitRejects(t, circuit, &conflicting)
	badProfileSetRoot := *valid
	badProfileSetRoot.CalibrationProfileSetRoot = bn254ScalarModulus
	assertV2CircuitRejects(t, circuit, &badProfileSetRoot)
}

type finalPolicyV2EmulatedTestCircuit struct {
	PolicyCommitment          frontend.Variable `gnark:",public"`
	MinimumQuorum             frontend.Variable
	CalibrationProfileSetRoot frontend.Variable
}

func (c *finalPolicyV2EmulatedTestCircuit) Define(api frontend.API) error {
	field, err := emulated.NewField[sw_bn254.ScalarField](api)
	if err != nil {
		return err
	}
	profileRoot := nativeBWScalarToBN254(api, field, c.CalibrationProfileSetRoot)
	got := finalPolicyCommitmentV2Emulated(api, field, c.MinimumQuorum, profileRoot)
	want := field.NewElement(c.PolicyCommitment)
	field.AssertIsInRange(want)
	field.AssertIsEqual(got, want)
	return nil
}

func TestFinalPolicyV2CommitmentMatchesInsideBW6NativeField(t *testing.T) {
	profileRoot, _, err := buildCalibrationProfileSetV2([]*big.Int{big.NewInt(1), big.NewInt(2)})
	if err != nil {
		t.Fatal(err)
	}
	otherRoot, _, err := buildCalibrationProfileSetV2([]*big.Int{big.NewInt(1)})
	if err != nil {
		t.Fatal(err)
	}
	commitment, err := FinalPolicyCommitmentV2(2, profileRoot)
	if err != nil {
		t.Fatal(err)
	}
	circuit := &finalPolicyV2EmulatedTestCircuit{}
	valid := &finalPolicyV2EmulatedTestCircuit{
		PolicyCommitment:          commitment,
		MinimumQuorum:             2,
		CalibrationProfileSetRoot: profileRoot,
	}
	if err := test.IsSolved(circuit, valid, ecc.BW6_761.ScalarField()); err != nil {
		t.Fatalf("BN254 Poseidon policy commitment did not match inside BW6: %v", err)
	}

	wrongProfileSet := *valid
	wrongProfileSet.CalibrationProfileSetRoot = otherRoot
	if err := test.IsSolved(circuit, &wrongProfileSet, ecc.BW6_761.ScalarField()); err == nil {
		t.Fatal("BW6 circuit accepted a commitment for a different profile set")
	}
}

func assertV2CircuitRejects(t *testing.T, circuit, assignment *FinalVerdictV2Circuit) {
	t.Helper()
	if err := test.IsSolved(circuit, assignment, ecc.BN254.ScalarField()); err == nil {
		t.Fatal("invalid V2 final policy assignment unexpectedly satisfied the circuit")
	}
}

func assertCircuitRejects(t *testing.T, circuit, assignment *FinalVerdictCircuit) {
	t.Helper()
	if err := test.IsSolved(circuit, assignment, ecc.BN254.ScalarField()); err == nil {
		t.Fatal("invalid final-verdict assignment unexpectedly satisfied the circuit")
	}
}
