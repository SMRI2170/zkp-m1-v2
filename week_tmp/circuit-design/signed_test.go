package draft

import (
	"crypto/rand"
	"encoding/json"
	"math/big"
	"os"
	"path/filepath"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	native "github.com/consensys/gnark-crypto/ecc/bn254/fr/mimc"
	nativecurve "github.com/consensys/gnark-crypto/ecc/bn254/twistededwards"
	nativeed "github.com/consensys/gnark-crypto/ecc/bn254/twistededwards/eddsa"
	ted "github.com/consensys/gnark-crypto/ecc/twistededwards"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
)

func signFixture(t *testing.T, c *SignedCircuit, key *nativeed.PrivateKey) {
	t.Helper()
	message, err := SignatureMessage(c.Observation.Commitment.(*big.Int), key.PublicKey, big.NewInt(int64(c.RecordID.(int))), uint64(c.ExpiresMS.(int)))
	if err != nil {
		t.Fatal(err)
	}
	sig, err := key.Sign(message, native.NewMiMC())
	if err != nil {
		t.Fatal(err)
	}
	ok, err := key.PublicKey.Verify(sig, message, native.NewMiMC())
	if err != nil || !ok {
		t.Fatal("native signature invalid", err)
	}
	c.ObserverKey.Assign(ted.BN254, key.PublicKey.Bytes())
	c.Signature.Assign(ted.BN254, sig)
}
func TestSignedCircuit(t *testing.T) {
	key, err := nativeed.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	other, err := nativeed.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	base := SignedCircuit{Observation: uncertainFixture(), RecordID: 1, ExpiresMS: 200000}
	signFixture(t, &base, key)
	cs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &SignedCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		name  string
		valid bool
		fn    func(*SignedCircuit)
	}{
		{"signed_consistent", true, func(c *SignedCircuit) {}},
		{"other_observer_correct_signature_needs_external_admission", true, func(c *SignedCircuit) { signFixture(t, c, other) }},
		{"static_circuit_does_not_know_verifier_now", true, func(c *SignedCircuit) { c.ExpiresMS = 110000; signFixture(t, c, key) }},
		{"signed_alarm", true, func(c *SignedCircuit) {
			c.Observation.RSSI = 13000
			c.Observation.Status = 1
			bindUncertain(&c.Observation)
			signFixture(t, c, key)
		}},
		{"signed_hold", true, func(c *SignedCircuit) {
			c.Observation.RSSI = 11500
			c.Observation.Status = 2
			bindUncertain(&c.Observation)
			signFixture(t, c, key)
		}},
		{"alter_rssi_rebind_keep_signature", false, func(c *SignedCircuit) { c.Observation.RSSI = 9001; bindUncertain(&c.Observation) }},
		{"alter_position_rebind_keep_signature", false, func(c *SignedCircuit) { c.Observation.Observer[0] = 8999; bindUncertain(&c.Observation) }},
		{"alter_error_rebind_keep_signature", false, func(c *SignedCircuit) { c.Observation.ReceiverError[0] = 101; bindUncertain(&c.Observation) }},
		{"alter_clock_rebind_keep_signature", false, func(c *SignedCircuit) { c.Observation.ClockErrorMS = 1; bindUncertain(&c.Observation) }},
		{"alter_known_flag_rebind_keep_signature", false, func(c *SignedCircuit) { c.Observation.AltitudeKnown = 1; bindUncertain(&c.Observation) }},
		{"alter_session_rebind_keep_signature", false, func(c *SignedCircuit) { c.Observation.Session = 8; bindUncertain(&c.Observation) }},
		{"alter_policy_rebind_keep_signature", false, func(c *SignedCircuit) { c.Observation.High[0] = 11999; bindUncertain(&c.Observation) }},
		{"alter_claim_rebind_keep_signature", false, func(c *SignedCircuit) { c.Observation.ClaimToken = 10; bindUncertain(&c.Observation) }},
		{"alter_record_id", false, func(c *SignedCircuit) { c.RecordID = 2 }},
		{"zero_record_id", false, func(c *SignedCircuit) { c.RecordID = 0; signFixture(t, c, key) }},
		{"alter_expiry", false, func(c *SignedCircuit) { c.ExpiresMS = 200001 }},
		{"signed_expiry_before_observation", false, func(c *SignedCircuit) { c.ExpiresMS = 99999; signFixture(t, c, key) }},
		{"different_observer_keep_signature", false, func(c *SignedCircuit) { c.ObserverKey.Assign(ted.BN254, other.PublicKey.Bytes()) }},
		{"identity_public_key", false, func(c *SignedCircuit) { c.ObserverKey.A.X = 0; c.ObserverKey.A.Y = 1 }},
		{"order2_public_key", false, func(c *SignedCircuit) {
			c.ObserverKey.A.X = 0
			c.ObserverKey.A.Y = new(big.Int).Sub(ecc.BN254.ScalarField(), big.NewInt(1))
		}},
		{"identity_R", false, func(c *SignedCircuit) { c.Signature.R.X = 0; c.Signature.R.Y = 1 }},
		{"order2_R", false, func(c *SignedCircuit) {
			c.Signature.R.X = 0
			c.Signature.R.Y = new(big.Int).Sub(ecc.BN254.ScalarField(), big.NewInt(1))
		}},
		{"offcurve_public_key", false, func(c *SignedCircuit) { c.ObserverKey.A.X = 1; c.ObserverKey.A.Y = 1 }},
		{"noncanonical_scalar", false, func(c *SignedCircuit) { order := tedOrder(); c.Signature.S = order }},
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
				t.Fatalf("want valid=%v err=%v", tt.valid, err)
			}
		})
	}
	if t.Failed() {
		t.Fatal("signature constraints failed")
	}
	if p := os.Getenv("DRAFT_SUMMARY_PATH"); p != "" {
		b, _ := json.MarshalIndent(map[string]interface{}{"status": "SYNTHETIC_SIGNED_CONSTRAINTS_ONLY", "test_cases": len(cases), "constraints": cs.GetNbConstraints(), "public_variables_including_constant": cs.GetNbPublicVariables(), "secret_variables": cs.GetNbSecretVariables(), "ephemeral_signer_keys_in_memory_only": true, "proof_generated": false, "field_signature_used": false}, "", "  ")
		if err := os.WriteFile(filepath.Join(filepath.Dir(p), "signed-constraint-summary.json"), append(b, '\n'), 0644); err != nil {
			t.Fatal(err)
		}
	}
}

func tedOrder() *big.Int { p := nativecurve.GetEdwardsCurve(); return new(big.Int).Set(&p.Order) }
