package main

import (
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/logger"
	"testing"
)

func TestSignedBatchBindings(t *testing.T) {
	logger.Disable()
	template := &Circuit{Obs: make([]Observation, 2)}
	cs, e := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, template)
	if e != nil {
		t.Fatal(e)
	}
	a, e := makeAssignment(2)
	if e != nil {
		t.Fatal(e)
	}
	w, e := frontend.NewWitness(a, ecc.BN254.ScalarField())
	if e != nil || cs.IsSolved(w) != nil {
		t.Fatal("valid signed batch rejected", e)
	}
	for _, kind := range []string{"session", "policy", "coordinate", "signature", "duplicate"} {
		b := *a
		b.Obs = append([]Observation(nil), a.Obs...)
		switch kind {
		case "session":
			b.Session = 24
		case "policy":
			b.Policy = 8
		case "coordinate":
			b.Obs[0].X2 = 4
		case "signature":
			b.Obs[0].Sig.S = 0
		case "duplicate":
			b.Obs[1] = b.Obs[0]
		}
		w, e = frontend.NewWitness(&b, ecc.BN254.ScalarField())
		if e != nil {
			t.Fatal(e)
		}
		if cs.IsSolved(w) == nil {
			t.Fatal("unbound", kind)
		}
	}
}
