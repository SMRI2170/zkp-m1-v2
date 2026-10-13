package main

import (
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/constraint"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/frontend/cs/scs"
	"math/big"
	"math/rand"
	"testing"
)

// Independent arbitrary-precision oracle, not the benchmark's binary-search helper.
func TestIntegerDistanceRelation(t *testing.T) {
	for name, b := range map[string]frontend.NewBuilder{"groth16": r1cs.NewBuilder[constraint.U64], "plonk": scs.NewBuilder[constraint.U64]} {
		t.Run(name, func(t *testing.T) {
			cs, err := frontend.Compile(ecc.BN254.ScalarField(), b, &Circuit{})
			if err != nil {
				t.Fatal(err)
			}
			rng := rand.New(rand.NewSource(24))
			inputs := append([][4]int{}, cases...)
			for i := 0; i < 100; i++ {
				inputs = append(inputs, [4]int{rng.Intn(65536), rng.Intn(65536), rng.Intn(65536), rng.Intn(65536)})
			}
			for _, a := range inputs {
				dx := big.NewInt(int64(a[0] - a[2]))
				dy := big.NewInt(int64(a[1] - a[3]))
				d := new(big.Int).Add(new(big.Int).Mul(dx, dx), new(big.Int).Mul(dy, dy))
				r := new(big.Int).Sqrt(d)
				di, ri := int(d.Int64()), int(r.Int64())
				rd, rr := reference(a)
				if rd != di || rr != ri {
					t.Fatal("reference mismatch")
				}
				for _, v := range []struct {
					c  *Circuit
					ok bool
				}{{assign(a, di, ri), true}, {assign(a, di+1, ri), false}, {assign(a, di, ri+1), false}, {assign(a, di, ri-1), false}} {
					w, e := frontend.NewWitness(v.c, ecc.BN254.ScalarField())
					if e != nil {
						t.Fatal(e)
					}
					if (cs.IsSolved(w) == nil) != v.ok {
						t.Fatalf("relation soundness mismatch for %v", a)
					}
				}
			}
			for _, a := range [][4]int{{-1, 0, 0, 0}, {65536, 0, 0, 0}} {
				d, r := reference(a)
				w, e := frontend.NewWitness(assign(a, d, r), ecc.BN254.ScalarField())
				if e != nil {
					t.Fatal(e)
				}
				if cs.IsSolved(w) == nil {
					t.Fatal("coordinate range accepted")
				}
			}
		})
	}
}
