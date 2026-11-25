package draft

import (
	"crypto/rand"
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/consensys/gnark-crypto/ecc"
	nativeed "github.com/consensys/gnark-crypto/ecc/bn254/twistededwards/eddsa"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"os"
	"path/filepath"
	"runtime"
	"sync"
	"sync/atomic"
	"syscall"
	"testing"
	"time"
)

func TestModelEndToEnd(t *testing.T) {
	if os.Getenv("DRAFT_RUN_MODEL_PROOF") != "1" {
		t.Skip("opt-in resource-gated model proof/benchmark")
	}
	key, err := nativeed.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	start := time.Now()
	cs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &SignedModelCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	compileUS := time.Since(start).Microseconds()
	start = time.Now()
	pk, vk, err := groth16.Setup(cs)
	if err != nil {
		t.Fatal(err)
	}
	setupUS := time.Since(start).Microseconds()
	store, err := OpenReceiptStore(privateStoreTemp(t))
	if err != nil {
		t.Fatal(err)
	}
	var rows [][]string
	for i := uint64(1); i <= 3; i++ {
		started := time.Now()
		signStart := time.Now()
		c, e := modelFixture(t, key, i, i, true)
		signUS := time.Since(signStart).Microseconds()
		w, err := frontend.NewWitness(&c, ecc.BN254.ScalarField())
		if err != nil {
			t.Fatal(err)
		}
		public, err := w.Public()
		if err != nil {
			t.Fatal(err)
		}
		start = time.Now()
		proof, err := groth16.Prove(cs, pk, w)
		if err != nil {
			t.Fatal(err)
		}
		proveUS := time.Since(start).Microseconds()
		start = time.Now()
		v, err := VerifyModelProof(proof, vk, public, e, 150000)
		if err != nil {
			t.Fatal(err)
		}
		verifyUS := time.Since(start).Microseconds()
		start = time.Now()
		if err = store.commit(v); err != nil {
			t.Fatal(err)
		}
		storeUS := time.Since(start).Microseconds()
		pc, wc := countOnlyWriter{}, countOnlyWriter{}
		if _, err = proof.WriteTo(&pc); err != nil {
			t.Fatal(err)
		}
		if _, err = public.WriteTo(&wc); err != nil {
			t.Fatal(err)
		}
		rows = append(rows, []string{fmt.Sprint(i), fmt.Sprint(signUS), fmt.Sprint(proveUS), fmt.Sprint(verifyUS), fmt.Sprint(storeUS), fmt.Sprint(time.Since(started).Microseconds()), fmt.Sprint(pc.n), fmt.Sprint(wc.n)})
		if i == 1 {
			deny := e
			deny.AllowResearchProfile = false
			if _, err = VerifyModelProof(proof, vk, public, deny, 150000); err == nil {
				t.Fatal("unadopted model used without research opt-in")
			}
			if _, err = VerifyModelProof(proof, vk, public, e, 99999); err == nil {
				t.Fatal("future claim admitted")
			}
			if _, err = VerifyModelProof(proof, vk, public, e, 200001); err == nil {
				t.Fatal("expired claim admitted")
			}
			bad := c
			bad.Core.Status = 2
			bw, err := frontend.NewWitness(&bad, ecc.BN254.ScalarField(), frontend.PublicOnly())
			if err != nil {
				t.Fatal(err)
			}
			if _, err = VerifyModelProof(proof, vk, bw, e, 150000); err == nil {
				t.Fatal("public replacement accepted")
			}
			concurrent, err := OpenReceiptStore(privateStoreTemp(t))
			if err != nil {
				t.Fatal(err)
			}
			var accepted, badErrors atomic.Int32
			var wg sync.WaitGroup
			for j := 0; j < 8; j++ {
				wg.Add(1)
				go func() {
					defer wg.Done()
					err := concurrent.VerifyAndStore(proof, vk, public, e, 150000)
					if err == nil {
						accepted.Add(1)
					} else if !errors.Is(err, ErrDuplicateReceipt) {
						badErrors.Add(1)
					}
				}()
			}
			wg.Wait()
			if accepted.Load() != 1 || badErrors.Load() != 0 {
				t.Fatal("real proof concurrent admission failed", accepted.Load(), badErrors.Load())
			}
			if err = store.VerifyAndStore(proof, vk, public, e, 150000); !errors.Is(err, ErrDuplicateReceipt) {
				t.Fatal("real replay not rejected", err)
			}
		}
	}
	// Same recorded source, new receipt ID, and a fresh valid signature/proof.
	reissued, e := modelFixture(t, key, 4, 1, true)
	rw, err := frontend.NewWitness(&reissued, ecc.BN254.ScalarField())
	if err != nil {
		t.Fatal(err)
	}
	rp, err := groth16.Prove(cs, pk, rw)
	if err != nil {
		t.Fatal(err)
	}
	rpub, err := rw.Public()
	if err != nil {
		t.Fatal(err)
	}
	if err = store.VerifyAndStore(rp, vk, rpub, e, 150000); !errors.Is(err, ErrDuplicateObservation) {
		t.Fatal("re-signed same source escaped dedup", err)
	}
	reopened, err := OpenReceiptStore(store.root)
	if err != nil {
		t.Fatal(err)
	}
	if n, err := reopened.Count(); err != nil || n != 3 {
		t.Fatal(n, err)
	}
	if t.Failed() {
		t.Fatal("model flow failed")
	}
	var usage syscall.Rusage
	syscall.Getrusage(syscall.RUSAGE_SELF, &usage)
	rss := int64(usage.Maxrss)
	if runtime.GOOS != "darwin" {
		rss *= 1024
	}
	var memory runtime.MemStats
	runtime.ReadMemStats(&memory)
	summary := map[string]interface{}{"statement": ModelStatementID, "status": "EXECUTED_SYNTHETIC_MODEL_FLOW", "constraints": cs.GetNbConstraints(), "compile_us": compileUS, "setup_us": setupUS, "benchmark_samples_shared_setup_same_process": 3, "additional_reissue_proof_checks": 1, "real_proof_concurrent_requests": 8, "accepted_unique_receipts_after_reopen": 3, "same_source_new_record_rejected": true, "research_opt_in_enforced": true, "keys_proofs_witnesses_persisted": false, "peak_process_rss_bytes": rss, "go_heap_inuse_bytes_at_end": memory.HeapInuse, "go_sys_bytes_at_end": memory.Sys, "field_data_used": false, "evm_or_recursive_path": false}
	if path := os.Getenv("DRAFT_SUMMARY_PATH"); path != "" {
		root := filepath.Dir(path)
		b, _ := json.MarshalIndent(summary, "", "  ")
		if err = os.WriteFile(filepath.Join(root, "model-e2e-summary.json"), append(b, '\n'), 0644); err != nil {
			t.Fatal(err)
		}
		file, err := os.Create(filepath.Join(root, "model-benchmark.csv"))
		if err != nil {
			t.Fatal(err)
		}
		writer := csv.NewWriter(file)
		writer.Write([]string{"sample", "assignment_and_sign_us", "prove_us", "joint_verify_us", "durable_commit_us", "full_flow_us", "proof_bytes_count_only", "public_witness_bytes_count_only"})
		writer.WriteAll(rows)
		writer.Flush()
		err = writer.Error()
		file.Close()
		if err != nil {
			t.Fatal(err)
		}
	}
}
