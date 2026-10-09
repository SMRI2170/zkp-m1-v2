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

type nativeBWToBN254Circuit struct {
	Value    frontend.Variable `gnark:",public"`
	Expected frontend.Variable `gnark:",public"`
}

func (c *nativeBWToBN254Circuit) Define(api frontend.API) error {
	field, err := emulated.NewField[sw_bn254.ScalarField](api)
	if err != nil {
		return err
	}
	got := nativeBWScalarToBN254(api, field, c.Value)
	api.AssertIsEqual(packBN254Element(api, field, got), c.Expected)
	return nil
}

func TestNativeBWScalarToBN254UsesCanonicalLimbRange(t *testing.T) {
	valid := &nativeBWToBN254Circuit{Value: 42, Expected: 42}
	if err := test.IsSolved(&nativeBWToBN254Circuit{}, valid, ecc.BW6_761.ScalarField()); err != nil {
		t.Fatalf("canonical BN254 value failed conversion from BW6: %v", err)
	}
	modulus := new(big.Int).Set(bn254ScalarModulus)
	invalid := &nativeBWToBN254Circuit{Value: modulus, Expected: modulus}
	if err := test.IsSolved(&nativeBWToBN254Circuit{}, invalid, ecc.BW6_761.ScalarField()); err == nil {
		t.Fatal("noncanonical BN254 scalar unexpectedly passed BW6 conversion")
	}
}
