package pcd

import (
	"fmt"
	"math/big"

	"github.com/consensys/gnark-crypto/ecc"
)

// BN254 values cannot be emitted as one BLS12-377 scalar: BN254 has a 254-bit
// scalar field while BLS12-377 has a 253-bit scalar field. Four 64-bit limbs
// preserve the canonical BN254 representation across that boundary.
const (
	bn254LimbBits     = 64
	bn254LimbCount    = 4
	encodedStateWidth = stateWidth * bn254LimbCount
)

type EncodedState [encodedStateWidth]*big.Int

var (
	bn254ScalarModulus = ecc.BN254.ScalarField()
	bn254LimbLimit     = new(big.Int).Lsh(big.NewInt(1), bn254LimbBits)
)

// EncodeState turns the nine canonical final-attestation values into a fixed
// little-endian limb layout. Every output limb is below 2^64, so it fits in a
// BLS12-377 scalar without reduction.
func EncodeState(state [stateWidth]*big.Int) (EncodedState, error) {
	var encoded EncodedState
	for i, value := range state {
		if value == nil || value.Sign() < 0 || value.Cmp(bn254ScalarModulus) >= 0 {
			return encoded, fmt.Errorf("state[%d] is not a canonical BN254 scalar", i)
		}
		v := new(big.Int).Set(value)
		for j := 0; j < bn254LimbCount; j++ {
			encoded[i*bn254LimbCount+j] = new(big.Int).And(v, new(big.Int).Sub(bn254LimbLimit, big.NewInt(1)))
			v.Rsh(v, bn254LimbBits)
		}
	}
	return encoded, nil
}

// DecodeState validates the limb bounds and returns the original canonical
// BN254 values. It rejects noncanonical encodings instead of silently reducing
// them modulo a field, which is vital when public inputs cross curve fields.
func DecodeState(encoded EncodedState) ([stateWidth]*big.Int, error) {
	var state [stateWidth]*big.Int
	for i := 0; i < stateWidth; i++ {
		value := big.NewInt(0)
		for j := 0; j < bn254LimbCount; j++ {
			limb := encoded[i*bn254LimbCount+j]
			if limb == nil || limb.Sign() < 0 || limb.Cmp(bn254LimbLimit) >= 0 {
				return state, fmt.Errorf("state[%d] limb[%d] is outside 64-bit range", i, j)
			}
			term := new(big.Int).Lsh(new(big.Int).Set(limb), uint(j*bn254LimbBits))
			value.Add(value, term)
		}
		if value.Cmp(bn254ScalarModulus) >= 0 {
			return state, fmt.Errorf("state[%d] is not a canonical BN254 scalar", i)
		}
		state[i] = value
	}
	return state, nil
}
