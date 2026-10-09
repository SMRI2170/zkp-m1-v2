package pcd

import (
	"fmt"

	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bw6761"
	"github.com/consensys/gnark/std/math/emulated"
)

// BWStateToBN254 converts a BW6-761 public state to canonical BN254 elements
// inside a BLS12-377 circuit. The high BW6 limbs must be zero; otherwise a
// value outside BN254's range could be reduced when carried across the cycle.
func BWStateToBN254(api frontend.API, bw *emulated.Field[sw_bw6761.ScalarField], bn *emulated.Field[sw_bn254.ScalarField], state [stateWidth]emulated.Element[sw_bw6761.ScalarField]) ([stateWidth]*emulated.Element[sw_bn254.ScalarField], error) {
	var result [stateWidth]*emulated.Element[sw_bn254.ScalarField]
	for i := range state {
		source := bw.ReduceStrict(&state[i])
		if len(source.Limbs) < bn254LimbCount {
			return result, fmt.Errorf("BW6 state[%d] has too few limbs", i)
		}
		for j := bn254LimbCount; j < len(source.Limbs); j++ {
			api.AssertIsEqual(source.Limbs[j], 0)
		}
		candidate := bn.NewElement([]frontend.Variable{
			source.Limbs[0], source.Limbs[1], source.Limbs[2], source.Limbs[3],
		})
		// Do not reduce before the range check: reduction would accept p as
		// zero. This assertion is the canonicality boundary between curves.
		bn.AssertIsInRange(candidate)
		result[i] = bn.ReduceStrict(candidate)
	}
	return result, nil
}

// BN254StateToBLSLimbs is the exact BLS-leg public output layout.
func BN254StateToBLSLimbs(bn *emulated.Field[sw_bn254.ScalarField], state [stateWidth]*emulated.Element[sw_bn254.ScalarField]) ([encodedStateWidth]frontend.Variable, error) {
	return EncodeStateLimbs(bn, state)
}
