package main

import (
	"crypto/rand"
	"math/big"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	native "github.com/consensys/gnark-crypto/ecc/bn254/fr/mimc"
	signed "github.com/consensys/gnark-crypto/ecc/bn254/twistededwards/eddsa"
	ted "github.com/consensys/gnark-crypto/ecc/twistededwards"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/logger"
)

// Freshly sign every case so invalid geometry/ranges cannot fail solely because
// the signature belongs to a different observation. All key/assignment data stays in RAM.
func signedVector(t *testing.T, session, policy, rid uint64, xy [4]uint64, d2, r uint64) *Circuit {
	t.Helper()
	key, err := signed.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	c := &Circuit{Session: session, Policy: policy, RID: rid, Obs: make([]Observation, 1)}
	c.PK.Assign(ted.BN254, key.PublicKey.Bytes())
	msg := nativeHash(0x574B3234, 1, session, policy, rid, 0, xy[0], xy[1], xy[2], xy[3], d2, r)
	sig, err := key.Sign(msg, native.NewMiMC())
	if err != nil {
		t.Fatal(err)
	}
	c.Obs[0] = Observation{X1: xy[0], Y1: xy[1], X2: xy[2], Y2: xy[3], D2: d2, R: r}
	c.Obs[0].Sig.Assign(ted.BN254, sig)
	h := native.NewMiMC()
	for _, v := range []uint64{0x574B3234, 1, session, policy, rid} {
		var f fr.Element
		f.SetUint64(v)
		b := f.Bytes()
		if _, err = h.Write(b[:]); err != nil {
			t.Fatal(err)
		}
	}
	if _, err = h.Write(msg); err != nil {
		t.Fatal(err)
	}
	c.Root = new(big.Int).SetBytes(h.Sum(nil))
	return c
}

func TestFreshSignedIntegerBoundaries(t *testing.T) {
	logger.Disable()
	cs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &Circuit{Obs: make([]Observation, 1)})
	if err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		name                        string
		xy                          [4]uint64
		d2, r, session, policy, rid uint64
		valid                       bool
	}{
		{"zero_distance", [4]uint64{}, 0, 0, 23, 7, 101, true},
		{"square", [4]uint64{0, 0, 3, 4}, 25, 5, 23, 7, 101, true},
		{"below_next_square", [4]uint64{0, 0, 2, 3}, 13, 3, 23, 7, 101, true},
		{"maximum_coordinates", [4]uint64{0, 0, 65535, 65535}, 8589672450, 92680, 23, 7, 101, true},
		{"maximum_metadata", [4]uint64{0, 0, 3, 4}, 25, 5, 1<<32 - 1, 1<<16 - 1, ^uint64(0), true},
		{"coordinate_overflow", [4]uint64{0, 0, 65536, 0}, 4294967296, 65536, 23, 7, 101, false},
		{"d2_overflow", [4]uint64{0, 0, 65536, 65536}, 1 << 33, 92681, 23, 7, 101, false},
		{"root_too_small", [4]uint64{0, 0, 3, 4}, 25, 4, 23, 7, 101, false},
		{"root_too_large", [4]uint64{0, 0, 3, 4}, 25, 6, 23, 7, 101, false},
		{"session_overflow", [4]uint64{0, 0, 3, 4}, 25, 5, 1 << 32, 7, 101, false},
		{"policy_overflow", [4]uint64{0, 0, 3, 4}, 25, 5, 23, 1 << 16, 101, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			a := signedVector(t, tc.session, tc.policy, tc.rid, tc.xy, tc.d2, tc.r)
			w, e := frontend.NewWitness(a, ecc.BN254.ScalarField())
			if e != nil {
				t.Fatal(e)
			}
			solved := cs.IsSolved(w) == nil
			if solved != tc.valid {
				t.Fatalf("solver accepted=%v; expected=%v", solved, tc.valid)
			}
		})
	}
}

func TestAdditionalBatchBindings(t *testing.T) {
	logger.Disable()
	cs, e := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &Circuit{Obs: make([]Observation, 2)})
	if e != nil {
		t.Fatal(e)
	}
	a, e := makeAssignment(2)
	if e != nil {
		t.Fatal(e)
	}
	other, e := makeAssignment(2)
	if e != nil {
		t.Fatal(e)
	}
	for _, kind := range []string{"wrong_public_key", "other_signer_signature", "rid", "reordered_observations", "root"} {
		t.Run(kind, func(t *testing.T) {
			b := *a
			b.Obs = append([]Observation(nil), a.Obs...)
			switch kind {
			case "wrong_public_key":
				b.PK = other.PK
			case "other_signer_signature":
				b.Obs[0].Sig = other.Obs[0].Sig
			case "rid":
				b.RID = 102
			case "reordered_observations":
				b.Obs[0], b.Obs[1] = b.Obs[1], b.Obs[0]
			case "root":
				b.Root = 0
			}
			w, e := frontend.NewWitness(&b, ecc.BN254.ScalarField())
			if e != nil {
				t.Fatal(e)
			}
			if cs.IsSolved(w) == nil {
				t.Fatal("invalid binding accepted")
			}
		})
	}
}
