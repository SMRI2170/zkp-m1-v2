package main

import (
	"encoding/json"
	"io"
	"math/big"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/frontend"
	"uav/aggregator/pcd"
)

type finalPublicVectorCircuit struct {
	Values [9]frontend.Variable `gnark:",public"`
}

func (c *finalPublicVectorCircuit) Define(frontend.API) error { return nil }

func TestPCDPublicInputsPreserveFinalAttestationOrder(t *testing.T) {
	assignment := &finalPublicVectorCircuit{}
	want := make([]string, len(assignment.Values))
	for i := range assignment.Values {
		value := big.NewInt(int64(i + 10))
		assignment.Values[i] = value
		want[i] = value.String()
	}
	full, err := frontend.NewWitness(assignment, ecc.BN254.ScalarField())
	if err != nil {
		t.Fatalf("create final statement witness: %v", err)
	}
	public, err := full.Public()
	if err != nil {
		t.Fatalf("extract final public witness: %v", err)
	}
	got, err := pcdPublicInputs(public)
	if err != nil {
		t.Fatalf("encode final public inputs: %v", err)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("public inputs = %v, want protocol order %v", got, want)
	}
}

func TestPCDPublicInputsRejectNonBN254Witness(t *testing.T) {
	public, err := witness.New(ecc.BLS12_377.ScalarField())
	if err != nil {
		t.Fatalf("create wrong-curve witness: %v", err)
	}
	if _, err := pcdPublicInputs(public); err == nil {
		t.Fatal("expected a non-BN254 public witness to be rejected")
	}
}

func TestParseCalibrationProfileIDs(t *testing.T) {
	got, err := parseCalibrationProfileIDs("2, 1,4294967295")
	if err != nil {
		t.Fatalf("parse comma-separated profile IDs: %v", err)
	}
	want := []*big.Int{big.NewInt(2), big.NewInt(1), new(big.Int).SetUint64(0xffffffff)}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("parsed profile IDs = %v, want %v", got, want)
	}
	for _, invalid := range []string{"", "1,,2", "-1", "4294967296", "profile"} {
		if _, err := parseCalibrationProfileIDs(invalid); err == nil {
			t.Errorf("invalid calibration profile list %q was accepted", invalid)
		}
	}
}

func TestDecodeRosterManifestRequiresIndependentActiveRootByDefault(t *testing.T) {
	raw := readSyntheticRoster(t)
	var manifest rosterManifest
	if err := json.Unmarshal(raw, &manifest); err != nil {
		t.Fatalf("decode fixture manifest: %v", err)
	}
	if _, _, _, err := decodeRosterManifest(raw, "", false); err == nil || !strings.Contains(err.Error(), "--active-member-root is required") {
		t.Fatalf("manifest root was accepted as an implicit trust anchor: %v", err)
	}
	roster, activeRoot, status, err := decodeRosterManifest(raw, manifest.MemberRoot, false)
	if err != nil {
		t.Fatalf("decode roster with explicit registry root: %v", err)
	}
	if len(roster) != 3 || activeRoot.String() != manifest.MemberRoot || !strings.Contains(status, "explicit --active-member-root") {
		t.Fatalf("decoded roster/root/source = %d/%s/%q", len(roster), activeRoot, status)
	}
	wrongActiveRoot := new(big.Int).Add(mustDecimal(t, manifest.MemberRoot), big.NewInt(1)).String()
	if _, _, _, err := decodeRosterManifest(raw, wrongActiveRoot, false); err == nil || !strings.Contains(err.Error(), "does not match the active member root") {
		t.Fatalf("roster that disagrees with the supplied registry root was accepted: %v", err)
	}
	_, _, status, err = decodeRosterManifest(raw, "", true)
	if err != nil || !strings.Contains(status, "manifest test-only opt-in") {
		t.Fatalf("explicit offline test mode was rejected or misreported: status=%q err=%v", status, err)
	}
}

func TestDecodeRosterManifestRejectsTamperedDuplicateAndNoncanonicalInputs(t *testing.T) {
	raw := readSyntheticRoster(t)
	var manifest rosterManifest
	if err := json.Unmarshal(raw, &manifest); err != nil {
		t.Fatalf("decode fixture manifest: %v", err)
	}
	root := manifest.MemberRoot

	t.Run("declared root mismatch", func(t *testing.T) {
		manifest.MemberRoot = new(big.Int).Add(mustDecimal(t, root), big.NewInt(1)).String()
		mutated, err := json.Marshal(manifest)
		if err != nil {
			t.Fatal(err)
		}
		if _, _, _, err := decodeRosterManifest(mutated, root, false); err == nil || !strings.Contains(err.Error(), "manifest memberRoot") {
			t.Fatalf("tampered declared root was accepted: %v", err)
		}
	})

	manifest.MemberRoot = root
	t.Run("duplicate enrolled key", func(t *testing.T) {
		manifest.Members[1] = manifest.Members[0]
		mutated, err := json.Marshal(manifest)
		if err != nil {
			t.Fatal(err)
		}
		if _, _, _, err := decodeRosterManifest(mutated, root, false); err == nil || !strings.Contains(err.Error(), "public key is duplicated") {
			t.Fatalf("duplicate roster key was accepted: %v", err)
		}
	})

	manifest.Members[1] = manifest.Members[0]
	manifest.Members[1].PublicKeyX = "0" + manifest.Members[1].PublicKeyX
	t.Run("noncanonical decimal", func(t *testing.T) {
		mutated, err := json.Marshal(manifest)
		if err != nil {
			t.Fatal(err)
		}
		if _, _, _, err := decodeRosterManifest(mutated, root, false); err == nil || !strings.Contains(err.Error(), "canonical decimal BN254 scalar") {
			t.Fatalf("noncanonical key encoding was accepted: %v", err)
		}
	})
}

func readSyntheticRoster(t *testing.T) []byte {
	t.Helper()
	path := filepath.Join("..", "..", "pcd", "testdata", "observer-roster-v1.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read synthetic roster fixture: %v", err)
	}
	return raw
}

func mustDecimal(t *testing.T, raw string) *big.Int {
	t.Helper()
	value, ok := new(big.Int).SetString(raw, 10)
	if !ok {
		t.Fatalf("invalid decimal fixture value %q", raw)
	}
	return value
}

func TestPlanDisclosesLegacyAuthenticationAndRSSIBindingGaps(t *testing.T) {
	warnings := strings.Join(planSecurityWarnings(), "\n")
	for _, required := range []string{
		"key-to-ID trust-root binding is NOT proven",
		"does not bind measured_range_cm or consistency_ok",
		"NOT observer-authenticated",
	} {
		if !strings.Contains(warnings, required) {
			t.Errorf("plan security warnings omit %q: %s", required, warnings)
		}
	}
}

func TestPrintPlanV2UsesNonOverclaimingDecisionLabel(t *testing.T) {
	batch := &pcd.PreparedObserverBatchV2{
		Observers:                  make([]pcd.PreparedObserverV2, 3),
		MemberRoot:                 big.NewInt(11),
		MergedNullRoot:             big.NewInt(12),
		CalibrationProfileSetRoot:  big.NewInt(13),
		PolicyCommitment:           big.NewInt(14),
		AllowedCalibrationProfiles: []*big.Int{big.NewInt(1), big.NewInt(2)},
	}
	batch.FinalStatement[7] = big.NewInt(2)
	batch.FinalStatement[8] = big.NewInt(1)
	batch.FinalStatement[9] = big.NewInt(int64(pcd.VerdictNoInconsistencyObserved))

	reader, writer, err := os.Pipe()
	if err != nil {
		t.Fatalf("create output pipe: %v", err)
	}
	previousStdout := os.Stdout
	os.Stdout = writer
	printPlanV2(batch, "synthetic test roster")
	if err := writer.Close(); err != nil {
		t.Fatalf("close output pipe: %v", err)
	}
	os.Stdout = previousStdout
	output, err := io.ReadAll(reader)
	if err != nil {
		t.Fatalf("read plan output: %v", err)
	}
	if err := reader.Close(); err != nil {
		t.Fatalf("close plan output: %v", err)
	}
	for _, required := range []string{
		"decision=NO_INCONSISTENCY_OBSERVED (verdict=1)",
		"V2 groups the claimed RID only",
		"does not authenticate the aircraft or verify a DRIP trust chain",
	} {
		if !strings.Contains(string(output), required) {
			t.Errorf("V2 plan overclaims or omits required boundary %q: %s", required, output)
		}
	}
}

func TestSourceFingerprintIncludesCircuitAndEmbeddedInputs(t *testing.T) {
	fingerprint, err := sourceFingerprint()
	if err != nil {
		t.Fatalf("compute source fingerprint: %v", err)
	}
	if len(fingerprint) != 64 {
		t.Fatalf("SHA-256 fingerprint has length %d, want 64", len(fingerprint))
	}
	files, err := sourceFingerprintFiles()
	if err != nil {
		t.Fatalf("list fingerprint inputs: %v", err)
	}
	for _, required := range []string{
		"go.mod",
		"go.sum",
		"cmd/pcd3/main.go",
		"cmd/pcd3/v2_pipeline.go",
		"cmd/pcd3/proof_cache.go",
		"pcd/bridge_bw.go",
		"pcd/policy.go",
		"pcd/circomlib_poseidon_t4_constants.json",
		"membership/membership.go",
		"nullifier/merge.go",
	} {
		found := false
		for _, file := range files {
			if strings.HasSuffix(file, required) {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("source fingerprint omits %s", required)
		}
	}
}
