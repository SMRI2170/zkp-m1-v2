package draft

import (
	"crypto/rand"
	"encoding/json"
	"github.com/consensys/gnark-crypto/ecc"
	native "github.com/consensys/gnark-crypto/ecc/bn254/fr/mimc"
	nativeed "github.com/consensys/gnark-crypto/ecc/bn254/twistededwards/eddsa"
	ted "github.com/consensys/gnark-crypto/ecc/twistededwards"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"math/big"
	"os"
	"path/filepath"
	"testing"
)

func modelFixture(t *testing.T, key *nativeed.PrivateKey, record, sourceSeq uint64, timeKnown bool) (SignedModelCircuit, ModelContext) {
	t.Helper()
	p, err := FrozenEnvelope()
	if err != nil {
		t.Fatal(err)
	}
	o := EnvelopeInput{Claim: [2]uint64{10000, 10000}, Observer: [2]uint64{9000, 10000}, RSSI: 10000, Eligible: timeKnown}
	core, err := EnvelopeAssignment(p, o, integerContext())
	if err != nil {
		t.Fatal(err)
	}
	c := SignedModelCircuit{Core: core}
	source, err := CanonicalSource("synthetic-run", "synthetic-boot", 100100000+sourceSeq, []byte{1, 2, 3})
	if err != nil {
		t.Fatal(err)
	}
	msg, err := ModelSignatureMessage(&c, key.PublicKey, record, 100000, 200000, 5000, 100100, 1, timeKnown, true, source)
	if err != nil {
		t.Fatal(err)
	}
	sig, err := key.Sign(msg, native.NewMiMC())
	if err != nil {
		t.Fatal(err)
	}
	c.Signature.Assign(ted.BN254, sig)
	e := ModelContext{ExpectedContext: ExpectedContext{Session: big.NewInt(7), FrameID: big.NewInt(8), ClaimToken: big.NewInt(9), PolicyDigest: c.StatementPolicy.(*big.Int), Observer: key.PublicKey, SessionStartMS: 90000, SessionEndMS: 250000}, AllowResearchProfile: true}
	return c, e
}
func TestSignedModelConstraints(t *testing.T) {
	key, err := nativeed.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	base, _ := modelFixture(t, key, 1, 1, true)
	cs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &SignedModelCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		name  string
		valid bool
		fn    func(*SignedModelCircuit)
	}{
		{"signed_current_model", true, func(c *SignedModelCircuit) {}},
		{"signed_time_unknown_hold", true, func(c *SignedModelCircuit) { *c, _ = modelFixture(t, key, 1, 1, false) }},
		{"rssi_replacement", false, func(c *SignedModelCircuit) { c.Core.RSSI = 10001 }},
		{"radius_replacement", false, func(c *SignedModelCircuit) { c.Core.ReceiverRadius = 1 }},
		{"time_replacement", false, func(c *SignedModelCircuit) { c.ObservedTimeMS = 100101 }},
		{"clock_replacement", false, func(c *SignedModelCircuit) { c.ClockErrorMS = 2 }},
		{"source_replacement", false, func(c *SignedModelCircuit) { c.SourceDigest[0] = 1 }},
		{"record_replacement", false, func(c *SignedModelCircuit) { c.RecordID = 2 }},
		{"expiry_replacement", false, func(c *SignedModelCircuit) { c.ExpiresMS = 200001 }},
		{"quality_cannot_be_lied_about", false, func(c *SignedModelCircuit) { c.TimeKnown = 0 }},
		{"invalid_quality", false, func(c *SignedModelCircuit) { c.HorizontalKnown = 2 }},
		{"policy_replacement", false, func(c *SignedModelCircuit) { c.MaxAgeMS = 6000 }},
		{"old_model_domain", false, func(c *SignedModelCircuit) { c.StatementPolicy = 1 }},
		{"nullifier_replacement", false, func(c *SignedModelCircuit) { c.Nullifier = 1 }},
		{"source_empty", false, func(c *SignedModelCircuit) { c.SourceDigest[0] = 0; c.SourceDigest[1] = 0 }},
		{"source_oversized", false, func(c *SignedModelCircuit) { c.SourceDigest[0] = new(big.Int).Lsh(big.NewInt(1), 128) }},
	}
	for _, tt := range cases {
		t.Run(tt.name, func(t *testing.T) {
			c := base
			tt.fn(&c)
			w, err := frontend.NewWitness(&c, ecc.BN254.ScalarField())
			if err == nil {
				err = cs.IsSolved(w)
			}
			if (err == nil) != tt.valid {
				t.Fatalf("valid=%v err=%v", tt.valid, err)
			}
		})
	}
	if t.Failed() {
		t.Fatal("new statement tests failed")
	}
	if path := os.Getenv("DRAFT_SUMMARY_PATH"); path != "" {
		b, _ := json.MarshalIndent(map[string]interface{}{"statement": ModelStatementID, "constraint_cases": len(cases), "constraints": cs.GetNbConstraints(), "public_variables_including_constant": cs.GetNbPublicVariables(), "research_profile_only": true}, "", "  ")
		if err := os.WriteFile(filepath.Join(filepath.Dir(path), "signed-model-constraints.json"), append(b, '\n'), 0644); err != nil {
			t.Fatal(err)
		}
	}
}
func TestSourceNullifierStability(t *testing.T) {
	key, err := nativeed.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	a, _ := modelFixture(t, key, 1, 1, true)
	b, _ := modelFixture(t, key, 2, 1, true)
	c, _ := modelFixture(t, key, 3, 2, true)
	if a.Nullifier.(*big.Int).Cmp(b.Nullifier.(*big.Int)) != 0 {
		t.Fatal("receipt reissue escaped observation nullifier")
	}
	if a.Nullifier.(*big.Int).Cmp(c.Nullifier.(*big.Int)) == 0 {
		t.Fatal("different declared API observation collided")
	}
	if _, err := CanonicalSource("", "boot", 1, []byte{1}); err == nil {
		t.Fatal("incomplete source allowed")
	}
}
