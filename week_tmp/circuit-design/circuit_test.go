package draft

import (
	"encoding/json"
	"math/big"
	"os"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	native "github.com/consensys/gnark-crypto/ecc/bn254/fr/mimc"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
)

func hash(values ...frontend.Variable) *big.Int {
	h := native.NewMiMC()
	for _, v := range values {
		var x big.Int
		switch n := v.(type) {
		case int:
			x.SetInt64(int64(n))
		case int64:
			x.SetInt64(n)
		case *big.Int:
			x.Set(n)
		default:
			panic("unsupported test scalar")
		}
		b := x.FillBytes(make([]byte, 32))
		if _, err := h.Write(b); err != nil {
			panic(err)
		}
	}
	return new(big.Int).SetBytes(h.Sum(nil))
}
func bind(c *Circuit) {
	p := []frontend.Variable{PolicyDomain, c.MaxAge, c.MaxAccuracy}
	p = append(p, c.Bounds[:]...)
	for i := 0; i < Bins; i++ {
		p = append(p, c.Low[i], c.High[i])
	}
	c.PolicyDigest = hash(p...)
	v := []frontend.Variable{ObservationDomain, c.Session, c.FrameID, c.ClaimToken, c.PolicyDigest}
	v = append(v, c.Claim[:]...)
	v = append(v, c.ClaimTime)
	v = append(v, c.Observer[:]...)
	v = append(v, c.RSSI, c.ObservedTime, c.Accuracy, c.Nonce, c.Status)
	c.Commitment = hash(v...)
}
func fixture() Circuit {
	c := Circuit{Session: 7, FrameID: 8, ClaimToken: 9, ClaimTime: 1000, ObservedTime: 1002, MaxAge: 5, MaxAccuracy: 100, Accuracy: 50, Nonce: 12345, RSSI: 9000, Status: 0}
	c.Claim = [3]frontend.Variable{10000, 10000, 10000}
	c.Observer = [3]frontend.Variable{9000, 10000, 10000}
	c.Bounds = [Bins + 1]frontend.Variable{0, 1000000, 4000000, 100000000, MaxDistanceSquared + 1}
	// Arbitrary SYNTHETIC intervals, not a calibrated radio model.
	c.Low = [Bins]frontend.Variable{8000, 8000, 6000, 4000}
	c.High = [Bins]frontend.Variable{12000, 11000, 10000, 9500}
	bind(&c)
	return c
}
func TestCircuit(t *testing.T) {
	if path := os.Getenv("DRAFT_SUMMARY_PATH"); path != "" {
		if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
			t.Fatal(err)
		}
	}
	cs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &Circuit{})
	if err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		name   string
		valid  bool
		mutate func(*Circuit)
		rebind bool
	}{
		{"consistent_boundary_second_bin", true, func(c *Circuit) {}, false},
		{"alarm", true, func(c *Circuit) { c.RSSI = 12000; c.Status = 1 }, true},
		{"lower_endpoint_inclusive", true, func(c *Circuit) { c.RSSI = 8000 }, true},
		{"upper_endpoint_inclusive", true, func(c *Circuit) { c.RSSI = 11000 }, true},
		{"one_below_interval", true, func(c *Circuit) { c.RSSI = 7999; c.Status = 1 }, true},
		{"age_boundary", true, func(c *Circuit) { c.ObservedTime = 1005 }, true},
		{"age_before_claim_boundary", true, func(c *Circuit) { c.ObservedTime = 995 }, true},
		{"stale_hold", true, func(c *Circuit) { c.ObservedTime = 1006; c.Status = 2 }, true},
		{"stale_earlier_hold", true, func(c *Circuit) { c.ObservedTime = 994; c.Status = 2 }, true},
		{"inaccurate_hold", true, func(c *Circuit) { c.Accuracy = 101; c.Status = 2 }, true},
		{"accuracy_boundary", true, func(c *Circuit) { c.Accuracy = 100 }, true},
		{"max_coordinate_no_wrap", true, func(c *Circuit) {
			c.Claim = [3]frontend.Variable{MaxCoordinate, MaxCoordinate, MaxCoordinate}
			c.Observer = [3]frontend.Variable{0, 0, 0}
		}, true},
		{"zero_distance", true, func(c *Circuit) { c.Observer = c.Claim }, true},
		{"wrong_alarm", false, func(c *Circuit) { c.Status = 1 }, true},
		{"hide_alarm_as_consistent", false, func(c *Circuit) { c.RSSI = 12000 }, true},
		{"hide_stale_as_consistent", false, func(c *Circuit) { c.ObservedTime = 1006 }, true},
		{"false_hold", false, func(c *Circuit) { c.Status = 2 }, true},
		{"unrecognised_status", false, func(c *Circuit) { c.Status = 3 }, true},
		{"negative_coordinate", false, func(c *Circuit) { c.Observer[0] = -1 }, false},
		{"coordinate_overflow", false, func(c *Circuit) { c.Claim[0] = 1 << CoordinateBits }, true},
		{"time_overflow", false, func(c *Circuit) { c.ObservedTime = int64(1) << 32; c.Status = 2 }, true},
		{"accuracy_overflow", false, func(c *Circuit) { c.Accuracy = 65536; c.Status = 2 }, true},
		{"rssi_overflow", false, func(c *Circuit) { c.RSSI = 16001; c.Status = 1 }, true},
		{"nonce_zero", false, func(c *Circuit) { c.Nonce = 0 }, true},
		{"nonce_overflow", false, func(c *Circuit) { c.Nonce = new(big.Int).Lsh(big.NewInt(1), 128) }, true},
		{"unordered_bounds", false, func(c *Circuit) { c.Bounds[2] = 500000 }, true},
		{"empty_bin", false, func(c *Circuit) { c.Bounds[2] = 1000000 }, true},
		{"incomplete_domain", false, func(c *Circuit) { c.Bounds[4] = 100000001 }, true},
		{"invalid_interval", false, func(c *Circuit) { c.Low[1] = 12000 }, true},
		{"policy_endpoint_overflow", false, func(c *Circuit) { c.High[1] = 16001 }, true},
		{"changed_session_old_commitment", false, func(c *Circuit) { c.Session = 8 }, false},
		{"changed_claim_old_commitment", false, func(c *Circuit) { c.Claim[1] = 10001 }, false},
		{"changed_frame_old_commitment", false, func(c *Circuit) { c.FrameID = 10 }, false},
		{"changed_rid_token_old_commitment", false, func(c *Circuit) { c.ClaimToken = 10 }, false},
		{"changed_rssi_old_commitment", false, func(c *Circuit) { c.RSSI = 9001 }, false},
		{"changed_policy_old_digest", false, func(c *Circuit) { c.Low[0] = 8001 }, false},
	}
	// Distinct interval endpoints make a wrong bin selection observable.
	cases = append(cases, []struct {
		name   string
		valid  bool
		mutate func(*Circuit)
		rebind bool
	}{
		{"below_first_bin_boundary", true, func(c *Circuit) { c.Observer[0] = 9001; c.RSSI = 12000 }, true},
		{"at_first_bin_boundary_alarm", true, func(c *Circuit) { c.RSSI = 12000; c.Status = 1 }, true},
		{"at_second_bin_boundary", true, func(c *Circuit) { c.Observer[0] = 8000; c.RSSI = 7000 }, true},
		{"before_second_bin_boundary_alarm", true, func(c *Circuit) { c.Observer[0] = 8001; c.RSSI = 7000; c.Status = 1 }, true},
		{"at_third_bin_boundary", true, func(c *Circuit) { c.Observer[0] = 0; c.RSSI = 5000 }, true},
		{"changed_observer_old_commitment", false, func(c *Circuit) { c.Observer[0] = 8999 }, false},
		{"changed_time_old_commitment", false, func(c *Circuit) { c.ObservedTime = 1003 }, false},
		{"changed_nonce_old_commitment", false, func(c *Circuit) { c.Nonce = 12346 }, false},
	}...)
	for _, tt := range cases {
		t.Run(tt.name, func(t *testing.T) {
			c := fixture()
			tt.mutate(&c)
			if tt.rebind {
				bind(&c)
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
		t.Fatal("constraint test failed; summary not written")
	}
	summary := map[string]interface{}{"status": "CONSTRAINTS_ONLY_SYNTHETIC", "test_cases": len(cases), "constraints": cs.GetNbConstraints(), "public_variables_including_constant": cs.GetNbPublicVariables(), "secret_variables": cs.GetNbSecretVariables(), "groth16_setup_executed": false, "proof_generated": false, "evm_verification_executed": false, "field_data_used": false}
	if path := os.Getenv("DRAFT_SUMMARY_PATH"); path != "" {
		b, _ := json.MarshalIndent(summary, "", "  ")
		if err := os.WriteFile(path, append(b, '\n'), 0644); err != nil {
			t.Fatal(err)
		}
	}
}
