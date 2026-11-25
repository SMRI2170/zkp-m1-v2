package draft

import (
	"encoding/json"
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"os"
	"path/filepath"
	"testing"
)

func bindUncertain(c *UncertaintyCircuit) {
	p := []frontend.Variable{3202001, c.Mode3D, c.MaxAgeMS, c.MaxSpeedCMS}
	p = append(p, c.Bounds[:]...)
	for i := 0; i < Bins; i++ {
		p = append(p, c.Low[i], c.High[i])
	}
	c.PolicyDigest = hash(p...)
	v := []frontend.Variable{3202002, c.Session, c.FrameID, c.ClaimToken, c.PolicyDigest}
	v = append(v, c.Claim[:]...)
	v = append(v, c.ClaimTimeMS)
	v = append(v, c.Observer[:]...)
	v = append(v, c.ReceiverError[:]...)
	v = append(v, c.ClaimError[:]...)
	v = append(v, c.RSSI, c.ObservedTimeMS, c.FixTimeMS, c.ClockErrorMS, c.MotionRadius, c.HorizontalKnown, c.TimeKnown, c.AltitudeKnown, c.Nonce, c.Status)
	c.Commitment = hash(v...)
}
func uncertainFixture() UncertaintyCircuit {
	c := UncertaintyCircuit{Session: 7, FrameID: 8, ClaimToken: 9, Mode3D: 0, ClaimTimeMS: 100000, ObservedTimeMS: 100000, FixTimeMS: 100000, ClockErrorMS: 0, MotionRadius: 0, MaxAgeMS: 5000, MaxSpeedCMS: 0, RSSI: 9000, HorizontalKnown: 1, TimeKnown: 1, AltitudeKnown: 0, Nonce: 12345, Status: 0}
	c.Claim = [3]frontend.Variable{10000, 10000, 10000}
	c.Observer = [3]frontend.Variable{9000, 10000, 10000}
	c.ReceiverError = [3]frontend.Variable{100, 100, 0}
	c.ClaimError = [3]frontend.Variable{100, 100, 0}
	policy, err := SyntheticPolicy()
	if err != nil {
		panic(err)
	}
	for i := 0; i <= Bins; i++ {
		c.Bounds[i] = int(policy.Bounds[i])
	}
	for i := 0; i < Bins; i++ {
		c.Low[i] = int(policy.Low[i])
		c.High[i] = int(policy.High[i])
	}
	c.Mode3D = int(flag(policy.Mode3D))
	c.MaxAgeMS = int(policy.MaxAgeMS)
	c.MaxSpeedCMS = int(policy.MaxSpeedCMS)
	bindUncertain(&c)
	return c
}
func TestUncertaintyCircuit(t *testing.T) {
	cs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &UncertaintyCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		name   string
		valid  bool
		fn     func(*UncertaintyCircuit)
		rebind bool
	}{
		{"2d_consistent_across_bins", true, func(c *UncertaintyCircuit) {}, false},
		{"uncertainty_causes_hold", true, func(c *UncertaintyCircuit) { c.RSSI = 11500; c.Status = 2 }, true},
		{"all_possible_bins_alarm", true, func(c *UncertaintyCircuit) { c.RSSI = 13000; c.Status = 1 }, true},
		{"zero_error_boundary_alarm", true, func(c *UncertaintyCircuit) {
			c.ReceiverError = [3]frontend.Variable{0, 0, 0}
			c.ClaimError = c.ReceiverError
			c.RSSI = 11500
			c.Status = 1
		}, true},
		{"3d_unknown_vertical_hold", true, func(c *UncertaintyCircuit) { c.Mode3D = 1; c.Status = 2 }, true},
		{"3d_known_vertical_consistent", true, func(c *UncertaintyCircuit) {
			c.Mode3D = 1
			c.AltitudeKnown = 1
			c.ReceiverError[2] = 100
			c.ClaimError[2] = 100
		}, true},
		{"3d_height_changes_bin", true, func(c *UncertaintyCircuit) { c.Mode3D = 1; c.AltitudeKnown = 1; c.Observer[2] = 0; c.RSSI = 5000 }, true},
		{"2d_ignores_height", true, func(c *UncertaintyCircuit) { c.Observer[2] = 0 }, true},
		{"unknown_horizontal_hold", true, func(c *UncertaintyCircuit) { c.HorizontalKnown = 0; c.Status = 2 }, true},
		{"unknown_clock_hold", true, func(c *UncertaintyCircuit) { c.TimeKnown = 0; c.Status = 2 }, true},
		{"stale_hold", true, func(c *UncertaintyCircuit) { c.ObservedTimeMS = 110000; c.Status = 2 }, true},
		{"ceil_motion_radius", true, func(c *UncertaintyCircuit) { c.MaxSpeedCMS = 1; c.ClockErrorMS = 1; c.MotionRadius = 1 }, true},
		{"exact_motion_radius", true, func(c *UncertaintyCircuit) {
			c.MaxSpeedCMS = 1000
			c.ClockErrorMS = 1000
			c.MotionRadius = 1000
			c.Status = 2
			c.RSSI = 11500
		}, true},
		{"wrong_rounding_reject", false, func(c *UncertaintyCircuit) { c.MaxSpeedCMS = 1; c.ClockErrorMS = 1; c.MotionRadius = 0 }, true},
		{"oversized_rounding_reject", false, func(c *UncertaintyCircuit) { c.MaxSpeedCMS = 1; c.ClockErrorMS = 1; c.MotionRadius = 2 }, true},
		{"uncertain_cannot_claim_consistent", false, func(c *UncertaintyCircuit) { c.RSSI = 11500 }, true},
		{"unknown_altitude_cannot_claim_3d", false, func(c *UncertaintyCircuit) { c.Mode3D = 1 }, true},
		{"invalid_dimension_flag", false, func(c *UncertaintyCircuit) { c.Mode3D = 2 }, true},
		{"nonboolean_known_flag", false, func(c *UncertaintyCircuit) { c.TimeKnown = 2 }, true},
		{"negative_error", false, func(c *UncertaintyCircuit) { c.ReceiverError[0] = -1 }, false},
		{"error_overflow", false, func(c *UncertaintyCircuit) { c.ClaimError[0] = 1 << 20 }, true},
		{"changed_error_old_commitment", false, func(c *UncertaintyCircuit) { c.ReceiverError[0] = 101 }, false},
		{"changed_clock_old_commitment", false, func(c *UncertaintyCircuit) { c.ClockErrorMS = 1 }, false},
		{"changed_mode_old_policy", false, func(c *UncertaintyCircuit) { c.Mode3D = 1; c.AltitudeKnown = 1 }, false},
		{"changed_status", false, func(c *UncertaintyCircuit) { c.Status = 1 }, true},
	}
	for _, tt := range cases {
		t.Run(tt.name, func(t *testing.T) {
			c := uncertainFixture()
			tt.fn(&c)
			if tt.rebind {
				bindUncertain(&c)
			}
			w, err := frontend.NewWitness(&c, ecc.BN254.ScalarField())
			if err == nil {
				err = cs.IsSolved(w)
			}
			if (err == nil) != tt.valid {
				t.Fatalf("want valid=%v, err=%v", tt.valid, err)
			}
		})
	}
	if t.Failed() {
		t.Fatal("uncertainty checks failed; no summary written")
	}
	if p := os.Getenv("DRAFT_SUMMARY_PATH"); p != "" {
		data, _ := json.MarshalIndent(map[string]interface{}{"status": "SYNTHETIC_CONSTRAINT_CHECKS_ONLY", "test_cases": len(cases), "constraints": cs.GetNbConstraints(), "proof_generated": false, "field_witness_used": false}, "", "  ")
		if err := os.WriteFile(filepath.Join(filepath.Dir(p), "uncertainty-constraint-summary.json"), append(data, '\n'), 0644); err != nil {
			t.Fatal(err)
		}
	}
}
