package draft

import (
	"encoding/json"
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"math/big"
	"os"
	"path/filepath"
	"testing"
)

func TestCalibratedEnvelope(t *testing.T) {
	p, err := FrozenEnvelope()
	if err != nil {
		t.Fatal(err)
	}
	cs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &CalibratedCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	counts := [3]int{}
	tested := 0
	for _, d := range []uint64{0, 435, 600, 1000, 2000, 3800, 5000} {
		for _, r := range []uint64{6000, 8000, 9000, 10000, 11000, 14000} {
			o := EnvelopeInput{Claim: [2]uint64{10000, 10000}, Observer: [2]uint64{10000 - d, 10000}, RSSI: r, Eligible: true}
			status, err := EvaluateEnvelope(p, o)
			if err != nil {
				t.Fatal(err)
			}
			counts[status]++
			c, err := EnvelopeAssignment(p, o, integerContext())
			if err != nil {
				t.Fatal(err)
			}
			w, err := frontend.NewWitness(&c, ecc.BN254.ScalarField())
			if err != nil {
				t.Fatal(err)
			}
			if err = cs.IsSolved(w); err != nil {
				t.Fatal("native/circuit mismatch", err)
			}
			tested++
		}
	}
	for i, n := range counts {
		if n == 0 {
			t.Fatalf("status%d missing", i)
		}
	}
	base := EnvelopeInput{Claim: [2]uint64{10000, 10000}, Observer: [2]uint64{9000, 10000}, RSSI: 9000, Eligible: true}
	negatives := []struct {
		name   string
		mutate func(*CalibratedCircuit)
	}{
		{"wrong_status_even_with_rebound_commitment", func(c *CalibratedCircuit) {
			status := uint64(1)
			if c.Status.(uint64) == 1 {
				status = 0
			}
			c.Status = status
			ctx := integerContext()
			v := append(ints(3206002), ctx.Session, ctx.FrameID, ctx.ClaimToken, c.PolicyDigest.(*big.Int))
			v = append(v, ints(base.Claim[0], base.Claim[1], base.Observer[0], base.Observer[1], base.ReceiverRadius, base.ClaimRadius, base.RSSI, 1)...)
			v = append(v, ctx.Nonce, new(big.Int).SetUint64(status))
			c.Commitment, _ = FieldHash(v...)
		}},
		{"changed_profile_old_digest", func(c *CalibratedCircuit) { c.OuterHigh[2] = int(p.OuterHigh[2]) - 1 }},
		{"nonboolean_eligibility", func(c *CalibratedCircuit) { c.Eligible = 2 }},
		{"zero_nonce", func(c *CalibratedCircuit) { c.Nonce = 0 }},
		{"coordinate_overflow", func(c *CalibratedCircuit) { c.Observer[0] = 1 << 20 }},
		{"negative_radius", func(c *CalibratedCircuit) { c.ReceiverRadius = -1 }},
	}
	for _, tt := range negatives {
		t.Run(tt.name, func(t *testing.T) {
			c, err := EnvelopeAssignment(p, base, integerContext())
			if err != nil {
				t.Fatal(err)
			}
			tt.mutate(&c)
			w, err := frontend.NewWitness(&c, ecc.BN254.ScalarField())
			if err == nil {
				err = cs.IsSolved(w)
			}
			if err == nil {
				t.Fatal("bad input accepted")
			}
		})
	}
	if t.Failed() {
		t.Fatal("envelope tests failed")
	}
	if path := os.Getenv("DRAFT_SUMMARY_PATH"); path != "" {
		b, _ := json.MarshalIndent(map[string]interface{}{"synthetic_positive_cases": tested, "negative_cases": len(negatives), "statuses_consistent_alarm_hold": counts, "constraints": cs.GetNbConstraints(), "proof_generated": false}, "", "  ")
		if err := os.WriteFile(filepath.Join(filepath.Dir(path), "calibrated-constraint-summary.json"), append(b, '\n'), 0644); err != nil {
			t.Fatal(err)
		}
	}
}

func TestEnvelopeJSONMissing(t *testing.T) {
	valid := EnvelopeInput{Claim: [2]uint64{100, 200}, Observer: [2]uint64{10, 20}, ReceiverRadius: 0, ClaimRadius: 0, RSSI: 9000, Eligible: true, ExpectedStatus: 0}
	data, err := json.Marshal(valid)
	if err != nil {
		t.Fatal(err)
	}
	var decoded EnvelopeInput
	if err = json.Unmarshal(data, &decoded); err != nil {
		t.Fatal(err)
	}
	var fields map[string]json.RawMessage
	if err = json.Unmarshal(data, &fields); err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"receiver_radius_cm", "claim_radius_cm", "rssi", "eligible", "expected_status"} {
		clone := map[string]json.RawMessage{}
		for k, v := range fields {
			clone[k] = v
		}
		delete(clone, key)
		bad, _ := json.Marshal(clone)
		if json.Unmarshal(bad, &decoded) == nil {
			t.Fatalf("missing %s became zero", key)
		}
	}
	fields["claim"] = json.RawMessage(`[1,2,3]`)
	bad, _ := json.Marshal(fields)
	if json.Unmarshal(bad, &decoded) == nil {
		t.Fatal("3D input truncated to 2D")
	}
}
