package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	recursion "github.com/consensys/gnark/std/recursion/groth16"
)

// Explicit experiment entry point; the original stage/setup commands stay unchanged.
func init() {
	if len(os.Args) > 1 && os.Args[1] == "fork-prove" {
		if len(os.Args) != 5 {
			fmt.Fprintln(os.Stderr, "fork-prove FIXTURE_BASE NEW_OUTPUT normal|outlier")
			os.Exit(2)
		}
		if err := forkProve(os.Args[2], os.Args[3], os.Args[4]); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		os.Exit(0)
	}
}

func forkProve(base, out, variant string) error {
	if variant != "normal" && variant != "outlier" {
		return fmt.Errorf("unknown observation variant")
	}
	// No blind setup-cache reuse: check the original circuit/dependency source hashes,
	// rebuild its CCS, compare serialized CCS, and record hashes of all loaded artifacts.
	root, err := os.Getwd()
	if err != nil {
		return err
	}
	var manifest struct {
		Sources map[string]string `json:"research_sources_sha256"`
	}
	m, err := os.ReadFile(filepath.Join(root, "week23/manifests/sources.json"))
	if err != nil {
		return err
	}
	if err = json.Unmarshal(m, &manifest); err != nil {
		return err
	}
	for _, name := range []string{"main.go", "relations.go", "go.mod", "go.sum"} {
		path := "poc/private-pcd/" + name
		data, e := os.ReadFile(filepath.Join(root, "week23", path))
		if e != nil {
			return e
		}
		h := sha256.Sum256(data)
		if manifest.Sources[path] != hex.EncodeToString(h[:]) {
			return fmt.Errorf("source/dependency metadata mismatch: %s; fixtures preserved", name)
		}
	}
	hashes := map[string]string{}
	for _, stage := range []string{"2", "3"} {
		for _, name := range []string{"ccs", "pk", "vk", "proof", "public"} {
			path := filepath.Join(base, stage, name+".bin")
			f, e := os.Open(path)
			if e != nil {
				return e
			}
			h := sha256.New()
			_, e = io.Copy(h, f)
			f.Close()
			if e != nil {
				return e
			}
			hashes[stage+"/"+name] = hex.EncodeToString(h.Sum(nil))
		}
	}
	prev := filepath.Join(base, "2")
	prevVK, prevProof := groth16.NewVerifyingKey(ecc.BN254), groth16.NewProof(ecc.BN254)
	prevPub, err := witness.New(ecc.BN254.ScalarField())
	if err != nil {
		return err
	}
	prevCCS := groth16.NewCS(ecc.BN254)
	for name, v := range map[string]io.ReaderFrom{"vk": prevVK, "proof": prevProof, "public": prevPub, "ccs": prevCCS} {
		if err = load(filepath.Join(prev, name+".bin"), v); err != nil {
			return err
		}
	}
	if err = groth16.Verify(prevProof, prevVK, prevPub, recursion.GetNativeVerifierOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField())); err != nil {
		return err
	}
	pvk, err := recursion.ValueOfVerifyingKeyFixed[sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl](prevVK)
	if err != nil {
		return err
	}
	pp, err := recursion.ValueOfProof[sw_bn254.G1Affine, sw_bn254.G2Affine](prevProof)
	if err != nil {
		return err
	}
	pu, err := recursion.ValueOfWitness[sw_bn254.ScalarField](prevPub)
	if err != nil {
		return err
	}
	circuit := &Chain{PrevProof: recursion.PlaceholderProof[sw_bn254.G1Affine, sw_bn254.G2Affine](prevCCS), PrevPublic: recursion.PlaceholderWitness[sw_bn254.ScalarField](prevCCS), vk: pvk, stage: 3}
	ccs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, circuit)
	if err != nil {
		return err
	}
	var rebuilt bytes.Buffer
	if _, err = ccs.WriteTo(&rebuilt); err != nil {
		return err
	}
	stored, err := os.ReadFile(filepath.Join(base, "3", "ccs.bin"))
	if err != nil {
		return err
	}
	if !bytes.Equal(rebuilt.Bytes(), stored) {
		return fmt.Errorf("rebuilt CCS differs; setup fixtures preserved, not reused")
	}
	pk, vk := groth16.NewProvingKey(ecc.BN254), groth16.NewVerifyingKey(ecc.BN254)
	if err = load(filepath.Join(base, "3", "pk.bin"), pk); err != nil {
		return err
	}
	if err = load(filepath.Join(base, "3", "vk.bin"), vk); err != nil {
		return err
	}
	obs, st := observation(3), state(3)
	if variant == "normal" {
		obs.Range = 300
		st.Consistent = 3
		st.Suspicious = 0
	}
	assignment := &Chain{State: st, Observation: obs, PrevProof: pp, PrevPublic: pu, vk: pvk, stage: 3}
	w, err := frontend.NewWitness(assignment, ecc.BN254.ScalarField())
	if err != nil {
		return err
	}
	t := time.Now()
	proof, err := groth16.Prove(ccs, pk, w, recursion.GetNativeProverOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField()))
	if err != nil {
		return err
	}
	proveMS := time.Since(t).Milliseconds()
	pub, err := w.Public()
	if err != nil {
		return err
	}
	if err = groth16.Verify(proof, vk, pub, recursion.GetNativeVerifierOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField())); err != nil {
		return err
	}
	if err = os.Mkdir(out, 0700); err != nil {
		return err
	}
	for name, v := range map[string]io.WriterTo{"proof": proof, "public": pub} {
		if err = save(filepath.Join(out, name+".bin"), v); err != nil {
			return err
		}
	}
	emit(map[string]any{"phase": "fork-prove", "variant": variant, "pid": os.Getpid(), "verified": true, "prove_ms": proveMS, "state": st, "source_hashes_match": true, "rebuilt_ccs_identical": true, "fixture_artifact_sha256": hashes, "private_assignment_cached": false, "scope": "two C continuations from the same B; fixed roster; no unique-history consensus"})
	return nil
}
