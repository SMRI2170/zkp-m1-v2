package pcd

import (
	"math/big"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	"github.com/consensys/gnark/std/math/emulated"
	"github.com/consensys/gnark/test"
)

type stateLimbCircuit struct {
	Limbs [encodedStateWidth]frontend.Variable `gnark:",public"`
}

func (c *stateLimbCircuit) Define(api frontend.API) error {
	f, err := emulated.NewField[sw_bn254.ScalarField](api)
	if err != nil {
		return err
	}
	state, err := DecodeStateLimbs(f, c.Limbs)
	if err != nil {
		return err
	}
	_, err = EncodeStateLimbs(f, state)
	return err
}

func TestStateLimbCircuitAcceptsCanonicalBN254Boundary(t *testing.T) {
	var state [stateWidth]*big.Int
	for i := range state {
		state[i] = big.NewInt(int64(i + 1))
	}
	state[0] = new(big.Int).Sub(bn254ScalarModulus, big.NewInt(1))
	encoded, err := EncodeState(state)
	if err != nil {
		t.Fatal(err)
	}
	a := &stateLimbCircuit{}
	for i := range encoded {
		a.Limbs[i] = encoded[i]
	}
	assert := test.NewAssert(t)
	assert.SolvingSucceeded(&stateLimbCircuit{}, a, test.WithCurves(ecc.BLS12_377), test.NoFuzzing())

	a.Limbs[3] = new(big.Int).Set(bn254LimbLimit)
	assert.SolvingFailed(&stateLimbCircuit{}, a, test.WithCurves(ecc.BLS12_377), test.NoFuzzing())
}
