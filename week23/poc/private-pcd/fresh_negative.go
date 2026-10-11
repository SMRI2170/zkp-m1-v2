package main

import (
	"fmt"
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
	recursion "github.com/consensys/gnark/std/recursion/groth16"
	"os"
	"path/filepath"
)

func init() {
	if len(os.Args) != 3 || os.Args[1] != "fresh-negative" {
		return
	}
	if err := freshNegative(os.Args[2]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	os.Exit(0)
}
func freshNegative(dir string) error {
	stage := filepath.Join(dir, "3")
	vk := groth16.NewVerifyingKey(ecc.BN254)
	proof := groth16.NewProof(ecc.BN254)
	if err := load(filepath.Join(stage, "vk.bin"), vk); err != nil {
		return err
	}
	if err := load(filepath.Join(stage, "proof.bin"), proof); err != nil {
		return err
	}
	for index, name := range []string{"version", "session", "rid", "bucket", "policy", "members", "consistent", "suspicious", "steps"} {
		pub, err := witness.New(ecc.BN254.ScalarField())
		if err != nil {
			return err
		}
		if err = load(filepath.Join(stage, "public.bin"), pub); err != nil {
			return err
		}
		values, ok := pub.Vector().(fr.Vector)
		if !ok || len(values) != 9 {
			return fmt.Errorf("schema")
		}
		values[index].SetUint64(values[index].Uint64() + 1)
		err = groth16.Verify(proof, vk, pub, recursion.GetNativeVerifierOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField()))
		emit(map[string]any{"phase": "fresh-negative-native-verifier", "case": name, "rejected": err != nil})
		if err == nil {
			return fmt.Errorf("native verifier accepted %s mutation", name)
		}
	}
	return nil
}
