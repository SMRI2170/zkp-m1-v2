package draft

import (
	"encoding/json"
	"math/big"
	"math/rand"
	"os"
	"path/filepath"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
)

func integerFixture() IntegerObservation {
	return IntegerObservation{Claim: [3]uint64{10000, 10000, 10000}, Observer: [3]uint64{9000, 10000, 10000}, ReceiverError: [3]uint64{100, 100, 0}, ClaimError: [3]uint64{100, 100, 0}, ClaimTimeMS: 100000, ObservedTimeMS: 100000, FixTimeMS: 100000, RSSI: 9000, HorizontalKnown: true, TimeKnown: true}
}
func integerContext() StatementContext {
	return StatementContext{big.NewInt(7), big.NewInt(8), big.NewInt(9), big.NewInt(12345)}
}
func TestIntegerParity(t *testing.T) {
	p, err := SyntheticPolicy()
	if err != nil {
		t.Fatal(err)
	}
	cs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &UncertaintyCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	rng := rand.New(rand.NewSource(32025))
	counts := [3]int{}
	for i := 0; i < 96; i++ {
		o := integerFixture()
		policy := p
		policy.Mode3D = i%2 == 1
		policy.MaxSpeedCMS = uint64([]int{0, 100, 500}[i%3])
		o.AltitudeKnown = i%7 != 0
		o.TimeKnown = i%11 != 0
		o.RSSI = []uint64{9000, 11500, 13000, 8000, 11000, 7000}[i%6]
		o.Observer[0] = uint64(8900 + rng.Intn(201))
		o.ObservedTimeMS += uint64(rng.Intn(250))
		o.ClockErrorMS = uint64(rng.Intn(20))
		for j := 0; j < 3; j++ {
			o.ReceiverError[j] = uint64(rng.Intn(101))
			o.ClaimError[j] = uint64(rng.Intn(101))
		}
		if i == 0 {
			policy.Mode3D = true
			policy.MaxSpeedCMS = 0
			o.TimeKnown = true
			o.AltitudeKnown = true
			o.Observer = [3]uint64{}
			o.Claim = [3]uint64{MaxCoordinate, MaxCoordinate, MaxCoordinate}
			o.ReceiverError = o.Claim
			o.ClaimError = o.Claim
			o.RSSI = 9000
		}
		r, err := EvaluateInteger(policy, o)
		if err != nil {
			t.Fatal(i, err)
		}
		counts[r.Status]++
		c, err := BuildUncertaintyAssignment(policy, o, integerContext())
		if err != nil {
			t.Fatal(i, err)
		}
		w, err := frontend.NewWitness(&c, ecc.BN254.ScalarField())
		if err != nil {
			t.Fatal(err)
		}
		if err = cs.IsSolved(w); err != nil {
			t.Fatalf("parity[%d] reference status=%d: %v", i, r.Status, err)
		}
	}
	for i, n := range counts {
		if n == 0 {
			t.Fatalf("status %d never exercised", i)
		}
	}
	if p := os.Getenv("DRAFT_SUMMARY_PATH"); p != "" {
		b, _ := json.MarshalIndent(map[string]interface{}{"scope": "same integer model, synthetic only; not adoption of field log model", "deterministic_cases": 96, "statuses_consistent_alarm_hold": counts, "native_and_circuit_match": true}, "", "  ")
		if err := os.WriteFile(filepath.Join(filepath.Dir(p), "integer-parity-summary.json"), append(b, '\n'), 0644); err != nil {
			t.Fatal(err)
		}
	}
}
func TestIntegerRanges(t *testing.T) {
	p, err := SyntheticPolicy()
	if err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		name string
		fn   func(*IntegerPolicy, *IntegerObservation)
	}{
		{"coordinate", func(p *IntegerPolicy, o *IntegerObservation) { o.Claim[0] = 1 << 20 }},
		{"error_even_inactive_z", func(p *IntegerPolicy, o *IntegerObservation) { o.ClaimError[2] = 1 << 20 }},
		{"time", func(p *IntegerPolicy, o *IntegerObservation) { o.ClaimTimeMS = 1 << 48 }},
		{"clock", func(p *IntegerPolicy, o *IntegerObservation) { o.ClockErrorMS = 1 << 32 }},
		{"rssi", func(p *IntegerPolicy, o *IntegerObservation) { o.RSSI = 16001 }},
		{"empty_bin", func(p *IntegerPolicy, o *IntegerObservation) { p.Bounds[2] = p.Bounds[1] }},
		{"high", func(p *IntegerPolicy, o *IntegerObservation) { p.High[0] = 16001 }},
		{"wide_product_does_not_wrap", func(p *IntegerPolicy, o *IntegerObservation) {
			p.MaxSpeedCMS = 65535
			o.ObservedTimeMS = (1 << 48) - 1
			o.FixTimeMS = 0
			o.ClaimTimeMS = 0
		}},
	}
	for _, tt := range cases {
		t.Run(tt.name, func(t *testing.T) {
			policy, o := p, integerFixture()
			tt.fn(&policy, &o)
			if _, err := EvaluateInteger(policy, o); err == nil {
				t.Fatal("invalid input accepted")
			}
		})
	}
}
func TestIntegerCeiling(t *testing.T) {
	p, _ := SyntheticPolicy()
	o := integerFixture()
	p.MaxSpeedCMS = 1
	o.ClockErrorMS = 1
	r, err := EvaluateInteger(p, o)
	if err != nil || r.MotionRadiusCM != 1 {
		t.Fatal("ceil mismatch", err, r)
	}
}
