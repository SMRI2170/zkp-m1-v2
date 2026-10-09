package pcd

import (
	"math/big"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bw6761"
	"github.com/consensys/gnark/std/math/emulated"
	"github.com/consensys/gnark/test"
)

type bwToBLSAdapterCircuit struct {
	State [stateWidth]emulated.Element[sw_bw6761.ScalarField]
}

func (c *bwToBLSAdapterCircuit) Define(api frontend.API) error {
	bw, err := emulated.NewField[sw_bw6761.ScalarField](api)
	if err != nil {
		return err
	}
	bn, err := emulated.NewField[sw_bn254.ScalarField](api)
	if err != nil {
		return err
	}
	state, err := BWStateToBN254(api, bw, bn, c.State)
	if err != nil {
		return err
	}
	_, err = BN254StateToBLSLimbs(bn, state)
	return err
}

func TestBWStateAdapterRejectsValueOutsideBN254(t *testing.T) {
	valid := &bwToBLSAdapterCircuit{}
	for i := range valid.State {
		valid.State[i] = emulated.ValueOf[sw_bw6761.ScalarField](big.NewInt(int64(i + 1)))
	}
	valid.State[0] = emulated.ValueOf[sw_bw6761.ScalarField](new(big.Int).Sub(bn254ScalarModulus, big.NewInt(1)))
	assert := test.NewAssert(t)
	assert.SolvingSucceeded(&bwToBLSAdapterCircuit{}, valid, test.WithCurves(ecc.BLS12_377), test.NoFuzzing())

	invalid := *valid
	invalid.State[0] = emulated.ValueOf[sw_bw6761.ScalarField](new(big.Int).Set(bn254ScalarModulus))
	assert.SolvingFailed(&bwToBLSAdapterCircuit{}, &invalid, test.WithCurves(ecc.BLS12_377), test.NoFuzzing())
}
