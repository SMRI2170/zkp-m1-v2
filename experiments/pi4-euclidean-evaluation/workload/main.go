// Synthetic observer-signed statement workload; RAM-only disposable local setup.
package main

import (
	"bytes"
	"crypto/rand"
	"encoding/json"
	"flag"
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	native "github.com/consensys/gnark-crypto/ecc/bn254/fr/mimc"
	signed "github.com/consensys/gnark-crypto/ecc/bn254/twistededwards/eddsa"
	ted "github.com/consensys/gnark-crypto/ecc/twistededwards"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/logger"
	"github.com/consensys/gnark/std/algebra/native/twistededwards"
	"github.com/consensys/gnark/std/hash/mimc"
	"github.com/consensys/gnark/std/signature/eddsa"
	"math/big"
	"os"
	"runtime"
	"time"
)

type Observation struct {
	X1, Y1, X2, Y2, D2, R frontend.Variable
	Sig                   eddsa.Signature
}
type Circuit struct {
	Session, Policy, RID, Root frontend.Variable `gnark:",public"`
	PK                         eddsa.PublicKey   `gnark:",public"`
	Obs                        []Observation
}

func (c *Circuit) Define(api frontend.API) error {
	api.ToBinary(c.Session, 32)
	api.ToBinary(c.Policy, 16)
	api.ToBinary(c.RID, 64)
	curve, e := twistededwards.NewEdCurve(api, ted.BN254)
	if e != nil {
		return e
	}
	aggregate, e := mimc.NewMiMC(api)
	if e != nil {
		return e
	}
	aggregate.Write(0x574B3234, len(c.Obs), c.Session, c.Policy, c.RID)
	for i, o := range c.Obs {
		for _, v := range []frontend.Variable{o.X1, o.Y1, o.X2, o.Y2} {
			api.ToBinary(v, 16)
		}
		api.ToBinary(o.D2, 33)
		api.ToBinary(o.R, 17)
		dx, dy := api.Sub(o.X1, o.X2), api.Sub(o.Y1, o.Y2)
		api.AssertIsEqual(o.D2, api.Add(api.Mul(dx, dx), api.Mul(dy, dy)))
		api.ToBinary(api.Sub(o.D2, api.Mul(o.R, o.R)), 18)
		api.ToBinary(api.Sub(api.Mul(api.Add(o.R, 1), api.Add(o.R, 1)), o.D2, 1), 18)
		h, e := mimc.NewMiMC(api)
		if e != nil {
			return e
		}
		h.Write(0x574B3234, len(c.Obs), c.Session, c.Policy, c.RID, i, o.X1, o.Y1, o.X2, o.Y2, o.D2, o.R)
		msg := h.Sum()
		sigHash, e := mimc.NewMiMC(api)
		if e != nil {
			return e
		}
		if e = eddsa.Verify(curve, o.Sig, msg, c.PK, &sigHash); e != nil {
			return e
		}
		aggregate.Write(msg)
	}
	api.AssertIsEqual(c.Root, aggregate.Sum())
	return nil
}
func nativeHash(values ...uint64) []byte {
	h := native.NewMiMC()
	for _, v := range values {
		var x fr.Element
		x.SetUint64(v)
		b := x.Bytes()
		if _, e := h.Write(b[:]); e != nil {
			panic(e)
		}
	}
	return h.Sum(nil)
}
func makeAssignment(n int) (*Circuit, error) {
	key, e := signed.GenerateKey(rand.Reader)
	if e != nil {
		return nil, e
	}
	c := &Circuit{Session: 23, Policy: 7, RID: 101, Obs: make([]Observation, n)}
	c.PK.Assign(ted.BN254, key.PublicKey.Bytes())
	aggregate := native.NewMiMC()
	for _, v := range []uint64{0x574B3234, uint64(n), 23, 7, 101} {
		var x fr.Element
		x.SetUint64(v)
		b := x.Bytes()
		aggregate.Write(b[:])
	}
	for i := range c.Obs {
		msg := nativeHash(0x574B3234, uint64(n), 23, 7, 101, uint64(i), 0, 0, 3, 4, 25, 5)
		sig, e := key.Sign(msg, native.NewMiMC())
		if e != nil {
			return nil, e
		}
		c.Obs[i] = Observation{X1: 0, Y1: 0, X2: 3, Y2: 4, D2: 25, R: 5}
		c.Obs[i].Sig.Assign(ted.BN254, sig)
		aggregate.Write(msg)
	}
	c.Root = new(big.Int).SetBytes(aggregate.Sum(nil))
	return c, nil
}
func emit(v any) {
	if e := json.NewEncoder(os.Stdout).Encode(v); e != nil {
		panic(e)
	}
}

var epoch = time.Now()

func mark(stage string, i int) {
	emit(map[string]any{"phase": "phase_marker", "sample_id": i, "stage": stage, "wall_time_ns": time.Now().UnixNano(), "clock_us": time.Since(epoch).Microseconds()})
}
func main() {
	n := flag.Int("count", 1, "synthetic signed observations")
	arrivalMS := flag.Int("arrival-ms", 0, "synthetic batch arrival interval; 0 disables live queue")
	flag.Parse()
	if *arrivalMS != 0 && *arrivalMS != 1000 {
		panic("supported arrival intervals: 0 or 1000ms")
	}
	if *n != 1 && *n != 2 && *n != 4 {
		panic("supported counts: 1,2,4")
	}
	runtime.GOMAXPROCS(1)
	logger.Disable()
	emit(map[string]any{"phase": "start", "framework": "gnark Groth16 observation workload", "os": runtime.GOOS, "arch": runtime.GOARCH, "observation_count": *n, "zk": true})
	t := time.Now()
	template := &Circuit{Obs: make([]Observation, *n)}
	cs, e := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, template)
	if e != nil {
		panic(e)
	}
	compile := time.Since(t).Seconds() * 1000
	t = time.Now()
	pk, vk, e := groth16.Setup(cs)
	if e != nil {
		panic(e)
	}
	setup := time.Since(t).Seconds() * 1000
	var vkbuf bytes.Buffer
	if _, e = vk.WriteTo(&vkbuf); e != nil {
		panic(e)
	}
	emit(map[string]any{"phase": "keys", "compile_ms": compile, "setup_ms": setup, "vk_bytes": vkbuf.Len(), "constraints": cs.GetNbConstraints(), "setup_scope": "disposable local-only RAM; never release keys"})
	assign, e := makeAssignment(*n)
	if e != nil {
		panic(e)
	}
	emit(map[string]any{"phase": "collection_protocol", "repeat_count": 3, "warmup_count": 1, "case_id": 1, "mode": "same synthetic signed batch within process", "observation_count": *n})
	seen := map[string]bool{}
	type token struct {
		Index int
		At    time.Time
	}
	incoming := make(chan token, 3)
	for i := 0; i < 4; i++ {
		if i == 1 && *arrivalMS > 0 {
			go func() {
				start := time.Now()
				for j := 0; j < 3; j++ {
					target := start.Add(time.Duration(j*(*arrivalMS)) * time.Millisecond)
					time.Sleep(time.Until(target))
					now := time.Now()
					emit(map[string]any{"phase": "input_arrival", "repetition": j, "wall_time_ns": now.UnixNano(), "scheduled_time_ns": target.UnixNano(), "arrival_jitter_ms": now.Sub(target).Seconds() * 1000, "observation_count": *n, "arrival_unit": "synthetic batch", "measured_load_test": true})
					incoming <- token{j, now}
				}
			}()
		}
		if i > 0 && *arrivalMS > 0 {
			item := <-incoming
			if item.Index != i-1 {
				panic("FIFO ordering failure")
			}
			emit(map[string]any{"phase": "input_dequeue", "repetition": item.Index, "wall_time_ns": time.Now().UnixNano(), "arrival_time_ns": item.At.UnixNano(), "wait_ms": time.Since(item.At).Seconds() * 1000, "queue_depth_after_dequeue": len(incoming), "measured_load_test": true})
		}

		mark("witness_start", i)
		t = time.Now()
		w, e := frontend.NewWitness(assign, ecc.BN254.ScalarField())
		if e != nil {
			panic(e)
		}
		pub, e := w.Public()
		if e != nil {
			panic(e)
		}
		wms := time.Since(t).Seconds() * 1000
		mark("prove_start", i)
		t = time.Now()
		proof, e := groth16.Prove(cs, pk, w)
		if e != nil {
			panic(e)
		}
		pms := time.Since(t).Seconds() * 1000
		mark("verify_start", i)
		t = time.Now()
		if e = groth16.Verify(proof, vk, pub); e != nil {
			panic(e)
		}
		vms := time.Since(t).Seconds() * 1000
		mark("verify_end", i)
		var buf, public bytes.Buffer
		proof.WriteTo(&buf)
		pub.WriteTo(&public)
		different := !seen[buf.String()]
		seen[buf.String()] = true // RAM-only diagnostic; bodies never emitted/saved.
		for _, field := range []string{"session", "root"} {
			bad := *assign
			if field == "session" {
				bad.Session = 24
			} else {
				bad.Root = new(big.Int).Add(assign.Root.(*big.Int), big.NewInt(1))
			}
			bw, _ := frontend.NewWitness(&bad, ecc.BN254.ScalarField())
			bp, _ := bw.Public()
			if groth16.Verify(proof, vk, bp) == nil {
				panic("modified public accepted")
			}
		}
		raw := buf.Bytes()
		fake := groth16.NewProof(ecc.BN254)
		r := append([]byte(nil), raw...)
		r[0] ^= 1
		_, err := fake.ReadFrom(bytes.NewReader(r))
		if err == nil && groth16.Verify(fake, vk, pub) == nil {
			panic("modified proof accepted")
		}
		var repetition any
		if i > 0 {
			repetition = i - 1
		}
		emit(map[string]any{"phase": "sample", "case_id": 1, "sample_id": i, "warmup": i == 0, "repetition": repetition, "observation_count": *n, "verified": true, "witness_ms": wms, "prove_ms": pms, "verify_ms": vms, "proof_bytes": buf.Len(), "public_input_bytes": public.Len(), "proof_randomness_new": different, "changed_public_rejected": true, "changed_root_rejected": true, "tampered_proof_rejected": true, "tamper_scope": "decoder or verifier rejection", "proofs_saved": false})
	}
	negative := 0
	for _, kind := range []string{"session", "policy", "coordinate", "signature", "duplicate"} {
		if kind == "duplicate" && *n == 1 {
			continue
		}
		bad := *assign
		bad.Obs = append([]Observation(nil), assign.Obs...)
		switch kind {
		case "session":
			bad.Session = 24
		case "policy":
			bad.Policy = 8
		case "coordinate":
			bad.Obs[0].X2 = 4
		case "signature":
			bad.Obs[0].Sig.S = 0
		case "duplicate":
			bad.Obs[1] = bad.Obs[0]
		}
		w, e := frontend.NewWitness(&bad, ecc.BN254.ScalarField())
		if e != nil {
			panic(e)
		}
		if cs.IsSolved(w) == nil {
			panic("invalid workload accepted: " + kind)
		}
		negative++
		emit(map[string]any{"phase": "workload_negative", "kind": kind, "scope": "constraint solver rejection, not forced invalid proof", "rejected": true})
	}
	emit(map[string]any{"phase": "summary", "samples": 4, "all_verified": true, "invalid_cases_rejected": negative, "proofs_saved": false})
}
