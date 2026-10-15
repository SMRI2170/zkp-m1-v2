package main

import (
	"encoding/json"
	"fmt"
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/logger"
	"math/big"
	"testing"
)

type PublicWire struct {
	Count   uint8       `json:"count"`
	Session uint64      `json:"session"`
	Policy  uint64      `json:"policy"`
	RID     uint64      `json:"rid"`
	Root    [32]byte    `json:"root"`
	PK      [2][32]byte `json:"pk"`
}
type ObservationWire struct {
	Values    [6]uint64   `json:"values"`
	Signature [3][32]byte `json:"signature"`
}
type BatchWire struct {
	Public       PublicWire        `json:"public"`
	Observations []ObservationWire `json:"observations"`
}

func bigValue(v interface{}) *big.Int {
	switch x := v.(type) {
	case int:
		return big.NewInt(int64(x))
	case uint64:
		return new(big.Int).SetUint64(x)
	case *big.Int:
		return new(big.Int).Set(x)
	case []byte:
		return new(big.Int).SetBytes(x)
	default:
		panic("unsupported fixture value")
	}
}
func bytes32(v interface{}) [32]byte {
	var out [32]byte
	bigValue(v).FillBytes(out[:])
	return out
}
func wire(a *Circuit) BatchWire {
	p := PublicWire{Count: uint8(len(a.Obs)), Session: bigValue(a.Session).Uint64(), Policy: bigValue(a.Policy).Uint64(), RID: bigValue(a.RID).Uint64(), Root: bytes32(a.Root), PK: [2][32]byte{bytes32(a.PK.A.X), bytes32(a.PK.A.Y)}}
	b := BatchWire{Public: p, Observations: make([]ObservationWire, len(a.Obs))}
	for i, o := range a.Obs {
		b.Observations[i] = ObservationWire{Values: [6]uint64{bigValue(o.X1).Uint64(), bigValue(o.Y1).Uint64(), bigValue(o.X2).Uint64(), bigValue(o.Y2).Uint64(), bigValue(o.D2).Uint64(), bigValue(o.R).Uint64()}, Signature: [3][32]byte{bytes32(o.Sig.R.X), bytes32(o.Sig.R.Y), bytes32(o.Sig.S)}}
	}
	return b
}

// Test binary stdout is piped directly to the Rust verifier; never write vectors to Git/logs.
func TestEmitInterop(t *testing.T) {
	logger.Disable()
	for _, n := range []int{1, 2, 4} {
		cs, e := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &Circuit{Obs: make([]Observation, n)})
		if e != nil {
			t.Fatal(e)
		}
		a, e := makeAssignment(n)
		if e != nil {
			t.Fatal(e)
		}
		other, e := makeAssignment(n)
		if e != nil {
			t.Fatal(e)
		}
		kinds := []string{"normal", "session", "policy", "rid", "root", "coordinate", "root_low", "root_high", "signature_s", "wrong_pk", "other_signature", "count_truncated"}
		if n > 1 {
			kinds = append(kinds, "reordered", "duplicate")
		}
		for _, kind := range kinds {
			b := *a
			b.Obs = append([]Observation(nil), a.Obs...)
			switch kind {
			case "session":
				b.Session = 24
			case "policy":
				b.Policy = 8
			case "rid":
				b.RID = 102
			case "root":
				b.Root = 0
			case "coordinate":
				b.Obs[0].X2 = 4
			case "root_low":
				b.Obs[0].R = 4
			case "root_high":
				b.Obs[0].R = 6
			case "signature_s":
				b.Obs[0].Sig.S = 0
			case "wrong_pk":
				b.PK = other.PK
			case "other_signature":
				b.Obs[0].Sig = other.Obs[0].Sig
			case "reordered":
				b.Obs[0], b.Obs[1] = b.Obs[1], b.Obs[0]
			case "duplicate":
				b.Obs[1] = b.Obs[0]
			}
			w, e := frontend.NewWitness(&b, ecc.BN254.ScalarField())
			if e != nil {
				t.Fatal(e)
			}
			accepted := cs.IsSolved(w) == nil
			if kind == "count_truncated" {
				accepted = false
			}
			if accepted != (kind == "normal") {
				t.Fatalf("unexpected baseline result: n=%d %s accepted=%v", n, kind, accepted)
			}
			value := wire(&b)
			if kind == "count_truncated" {
				value.Observations = value.Observations[:n-1]
			}
			result := map[string]interface{}{"case": kind, "batch": value, "expected": accepted, "go_rejection_scope": "constraint solver, except count_truncated is envelope shape"}
			encoded, e := json.Marshal(result)
			if e != nil {
				t.Fatal(e)
			}
			fmt.Println(string(encoded))
		}
	}
}
