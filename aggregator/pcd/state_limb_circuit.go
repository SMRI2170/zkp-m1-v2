package pcd

import (
	"fmt"

	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	"github.com/consensys/gnark/std/math/emulated"
)

// DecodeStateLimbs is the in-circuit counterpart of DecodeState. Each group
// of four public 64-bit limbs is reconstructed as one canonical BN254 scalar.
// ReduceStrict both checks limb widths and rejects values at or above the
// BN254 modulus; callers must use this at every BLS12-377 boundary.
func DecodeStateLimbs(f *emulated.Field[sw_bn254.ScalarField], limbs [encodedStateWidth]frontend.Variable) ([stateWidth]*emulated.Element[sw_bn254.ScalarField], error) {
	var state [stateWidth]*emulated.Element[sw_bn254.ScalarField]
	for i := 0; i < stateWidth; i++ {
		offset := i * bn254LimbCount
		e := f.NewElement([]frontend.Variable{
			limbs[offset], limbs[offset+1], limbs[offset+2], limbs[offset+3],
		})
		state[i] = f.ReduceStrict(e)
	}
	return state, nil
}

// EncodeStateLimbs emits the canonical 64-bit limbs of nine BN254 values for
// use as BLS12-377 public inputs.
func EncodeStateLimbs(f *emulated.Field[sw_bn254.ScalarField], state [stateWidth]*emulated.Element[sw_bn254.ScalarField]) ([encodedStateWidth]frontend.Variable, error) {
	var limbs [encodedStateWidth]frontend.Variable
	for i := 0; i < stateWidth; i++ {
		if state[i] == nil {
			return limbs, fmt.Errorf("state[%d] is nil", i)
		}
		e := f.ReduceStrict(state[i])
		if len(e.Limbs) != bn254LimbCount {
			return limbs, fmt.Errorf("state[%d] has %d limbs, expected %d", i, len(e.Limbs), bn254LimbCount)
		}
		copy(limbs[i*bn254LimbCount:(i+1)*bn254LimbCount], e.Limbs)
	}
	return limbs, nil
}
