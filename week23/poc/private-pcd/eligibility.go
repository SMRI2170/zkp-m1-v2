package main

import (
	"fmt"
	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	"github.com/consensys/gnark/backend/witness"
)

// Synthetic-clock host gate, separate from cryptographic verification.
// Policy fixture: valid from bucket 100001 through bucket+2 inclusive.
func eligible(pub witness.Witness, now uint64, seen bool) error {
	v, ok := pub.Vector().(fr.Vector)
	if !ok || len(v) != 9 {
		return fmt.Errorf("wrong public schema")
	}
	bucket := v[3].Uint64()
	if now < bucket || now-bucket > 2 {
		return fmt.Errorf("expired or future observation")
	}
	if seen {
		return fmt.Errorf("session/member replay")
	}
	return nil
}
func checkEligibility(pub witness.Witness, stage int) error {
	for _, tc := range []struct {
		name   string
		now    uint64
		seen   bool
		accept bool
	}{
		{"fresh", 100002, false, true}, {"expired", 100004, false, false}, {"future", 100000, false, false}, {"replay", 100002, true, false},
	} {
		err := eligible(pub, tc.now, tc.seen)
		emit(map[string]any{"stage": stage, "phase": "host-policy-test", "case": tc.name, "accepted": err == nil, "expected_accept": tc.accept, "clock": "synthetic"})
		if (err == nil) != tc.accept {
			return fmt.Errorf("host policy %s mismatch", tc.name)
		}
	}
	return nil
}
