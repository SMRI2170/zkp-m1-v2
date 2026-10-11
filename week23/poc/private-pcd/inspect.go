package main

import (
	"fmt"
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	"github.com/consensys/gnark/backend/witness"
	"os"
	"path/filepath"
	"strconv"
)

// Public-only receipt export after actual Groth16 verification; no assignment export.
func init() {
	if len(os.Args) != 4 || os.Args[1] != "inspect-verified" {
		return
	}
	stage, err := strconv.Atoi(os.Args[3])
	if err == nil {
		err = run("verify", os.Args[2], stage)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	pub, err := witness.New(ecc.BN254.ScalarField())
	if err == nil {
		err = load(filepath.Join(os.Args[2], strconv.Itoa(stage), "public.bin"), pub)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	v, ok := pub.Vector().(fr.Vector)
	if !ok || len(v) != 9 {
		fmt.Fprintln(os.Stderr, "public schema")
		os.Exit(1)
	}
	values := make([]string, len(v))
	for i := range v {
		values[i] = v[i].String()
	}
	emit(map[string]any{"verified": true, "public": values, "pid": os.Getpid()})
	os.Exit(0)
}
