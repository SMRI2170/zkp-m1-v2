package main

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	recursion "github.com/consensys/gnark/std/recursion/groth16"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"time"
)

func percentile(samples []float64, p float64) float64 {
	a := append([]float64(nil), samples...)
	sort.Float64s(a)
	pos := float64(len(a)-1) * p
	i := int(pos)
	if i >= len(a)-1 {
		return a[len(a)-1]
	}
	return a[i] + (a[i+1]-a[i])*(pos-float64(i))
}

// Immediately generated local disposable fixture keys; hash every artifact before measuring.
// This benchmark does not discover/reuse pcd3 setup caches.
func benchSingleton(dir string, stage int) error {
	p := filepath.Join(dir, strconv.Itoa(stage))
	ccs := groth16.NewCS(ecc.BN254)
	pk := groth16.NewProvingKey(ecc.BN254)
	vk := groth16.NewVerifyingKey(ecc.BN254)
	if e := load(filepath.Join(p, "ccs.bin"), ccs); e != nil {
		return e
	}
	if e := load(filepath.Join(p, "pk.bin"), pk); e != nil {
		return e
	}
	if e := load(filepath.Join(p, "vk.bin"), vk); e != nil {
		return e
	}
	hashes := map[string]string{}
	for _, name := range []string{"ccs.bin", "pk.bin", "vk.bin"} {
		b, e := os.ReadFile(filepath.Join(p, name))
		if e != nil {
			return e
		}
		h := sha256.Sum256(b)
		hashes[name] = hex.EncodeToString(h[:])
	}
	st := state(1)
	st.Members = 1 << (stage - 1)
	if stage == 3 {
		st.Consistent = 0
		st.Suspicious = 1
	}
	a := &Leaf{State: st, Observation: observation(stage), member: stage - 1}
	w, e := frontend.NewWitness(a, ecc.BN254.ScalarField())
	if e != nil {
		return e
	}
	pub, e := w.Public()
	if e != nil {
		return e
	}
	proves := []float64{}
	verifies := []float64{}
	for i := 0; i < 21; i++ {
		t := time.Now()
		proof, e := groth16.Prove(ccs, pk, w, recursion.GetNativeProverOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField()))
		if e != nil {
			return e
		}
		prove := float64(time.Since(t).Nanoseconds()) / 1e6
		t = time.Now()
		if e = groth16.Verify(proof, vk, pub, recursion.GetNativeVerifierOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField())); e != nil {
			return e
		}
		verify := float64(time.Since(t).Nanoseconds()) / 1e6
		if i > 0 {
			proves = append(proves, prove)
			verifies = append(verifies, verify)
		}
	}
	emit(map[string]any{"baseline": "singleton", "stage": stage, "warmup": 1, "n": 20, "percentile_method": "linear interpolation over sorted samples", "prove_p50_ms": percentile(proves, .5), "prove_p95_ms": percentile(proves, .95), "verify_p50_ms": percentile(verifies, .5), "verify_p95_ms": percentile(verifies, .95), "artifact_sha256": hashes, "condition": "shared local host; recursive setup may run concurrently"})
	if len(proves) != 20 {
		return fmt.Errorf("wrong samples")
	}
	return nil
}
