package pcd

import (
	"math/big"
	"testing"
)

func TestStateEncodingRoundTripAtBN254Boundary(t *testing.T) {
	var state [stateWidth]*big.Int
	for i := range state {
		state[i] = big.NewInt(int64(i + 1))
	}
	state[0] = new(big.Int).Sub(bn254ScalarModulus, big.NewInt(1))
	encoded, err := EncodeState(state)
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := DecodeState(encoded)
	if err != nil {
		t.Fatal(err)
	}
	for i := range state {
		if state[i].Cmp(decoded[i]) != 0 {
			t.Fatalf("state[%d] changed during limb encoding", i)
		}
	}
}

func TestStateEncodingRejectsNonCanonicalAndOversizedLimbs(t *testing.T) {
	var state [stateWidth]*big.Int
	for i := range state {
		state[i] = big.NewInt(0)
	}
	state[0] = new(big.Int).Set(bn254ScalarModulus)
	if _, err := EncodeState(state); err == nil {
		t.Fatal("expected BN254 modulus itself to be rejected")
	}

	state[0] = big.NewInt(0)
	encoded, err := EncodeState(state)
	if err != nil {
		t.Fatal(err)
	}
	encoded[0] = new(big.Int).Set(bn254LimbLimit)
	if _, err := DecodeState(encoded); err == nil {
		t.Fatal("expected a 65-bit limb to be rejected")
	}
}
