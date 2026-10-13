// Local-only toy Groth16 benchmark. Not an RSSI, session, or aircraft proof.
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
	"runtime"
	"runtime/debug"
	"sort"
	"syscall"
	"time"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/logger"
)

var sourceDigest string // Baked in from main.go/go.mod/go.sum by the host build.
type Circuit struct {
	Y frontend.Variable `gnark:",public"`
	X frontend.Variable
}

func (c *Circuit) Define(api frontend.API) error {
	api.ToBinary(c.X, 8)
	api.AssertIsEqual(c.Y, api.Add(api.Mul(c.X, c.X, c.X), c.X, 5))
	return nil
}

type Artifact struct {
	SHA256 string `json:"sha256"`
	Bytes  int64  `json:"bytes"`
}
type Manifest struct {
	SourceDigest string              `json:"source_digest"`
	Files        map[string]Artifact `json:"files"`
}

func emit(v any) {
	if err := json.NewEncoder(os.Stdout).Encode(v); err != nil {
		panic(err)
	}
}
func encode(v io.WriterTo) ([]byte, error) {
	var b bytes.Buffer
	_, err := v.WriteTo(&b)
	return b.Bytes(), err
}
func digest(data []byte) string { h := sha256.Sum256(data); return hex.EncodeToString(h[:]) }
func save(path string, data []byte) error {
	f, e := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if e != nil {
		return e
	}
	defer f.Close()
	_, e = f.Write(data)
	return e
}
func load(path string, v io.ReaderFrom) error {
	f, e := os.Open(path)
	if e != nil {
		return e
	}
	defer f.Close()
	_, e = v.ReadFrom(f)
	return e
}
func assign(x, y int) *Circuit { return &Circuit{X: x, Y: y} }
func percentile(xs []float64, p float64) float64 {
	a := append([]float64(nil), xs...)
	sort.Float64s(a)
	f := float64(len(a)-1) * p
	i := int(f)
	if i+1 == len(a) {
		return a[i]
	}
	return a[i] + (a[i+1]-a[i])*(f-float64(i))
}
func peakRSS() int64 {
	var r syscall.Rusage
	if syscall.Getrusage(syscall.RUSAGE_SELF, &r) != nil {
		return -1
	}
	if runtime.GOOS == "darwin" {
		return r.Maxrss
	}
	return r.Maxrss * 1024
}
func run() error {
	logger.Disable()
	if sourceDigest == "" {
		return fmt.Errorf("build must bake sourceDigest")
	}
	if len(os.Args) != 3 {
		return fmt.Errorf("use setup|bench PRIVATE_FIXTURE")
	}
	mode, dir := os.Args[1], os.Args[2]
	start := time.Now()
	cs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &Circuit{})
	if err != nil {
		return err
	}
	compileMS := float64(time.Since(start).Microseconds()) / 1000
	csBytes, err := encode(cs)
	if err != nil {
		return err
	}
	if mode == "setup" {
		if err = os.Mkdir(dir, 0700); err != nil {
			return err
		}
		start = time.Now()
		pk, vk, err := groth16.Setup(cs)
		if err != nil {
			return err
		}
		setupMS := float64(time.Since(start).Microseconds()) / 1000
		m := Manifest{SourceDigest: sourceDigest, Files: map[string]Artifact{}}
		for name, obj := range map[string]io.WriterTo{"cs.bin": cs, "pk.bin": pk, "vk.bin": vk} {
			b, e := encode(obj)
			if e != nil {
				return e
			}
			if e = save(filepath.Join(dir, name), b); e != nil {
				return e
			}
			m.Files[name] = Artifact{digest(b), int64(len(b))}
		}
		b, err := json.MarshalIndent(m, "", "  ")
		if err != nil {
			return err
		}
		if err = save(filepath.Join(dir, "manifest.json"), append(b, '\n')); err != nil {
			return err
		}
		emit(map[string]any{"phase": "setup", "host_os": runtime.GOOS, "host_arch": runtime.GOARCH, "compile_ms": compileMS, "setup_ms": setupMS, "constraints": cs.GetNbConstraints(), "artifacts": m.Files, "source_digest": sourceDigest, "fixture": "disposable local-only; never deploy/publish"})
		return nil
	}
	if mode != "bench" {
		return fmt.Errorf("unknown mode")
	}
	for _, path := range []string{dir, filepath.Join(dir, "manifest.json")} {
		info, err := os.Stat(path)
		if err != nil {
			return err
		}
		want := os.FileMode(0600)
		if path == dir {
			want = 0700
		}
		if info.Mode().Perm() != want {
			return fmt.Errorf("private fixture permission mismatch")
		}
	}
	b, err := os.ReadFile(filepath.Join(dir, "manifest.json"))
	if err != nil {
		return err
	}
	var m Manifest
	if err = json.Unmarshal(b, &m); err != nil {
		return err
	}
	if m.SourceDigest != sourceDigest || len(m.Files) != 3 {
		return fmt.Errorf("fixture source/shape mismatch")
	}
	for _, name := range []string{"cs.bin", "pk.bin", "vk.bin"} {
		p := filepath.Join(dir, name)
		s, e := os.Stat(p)
		if e != nil {
			return e
		}
		if s.Mode().Perm() != 0600 {
			return fmt.Errorf("private artifact mode mismatch")
		}
		data, e := os.ReadFile(p)
		if e != nil {
			return e
		}
		a, ok := m.Files[name]
		if !ok || a.SHA256 != digest(data) || a.Bytes != int64(len(data)) {
			return fmt.Errorf("artifact mismatch")
		}
	}
	if m.Files["cs.bin"].SHA256 != digest(csBytes) {
		return fmt.Errorf("current compiled CS differs from cached CS")
	}
	pk := groth16.NewProvingKey(ecc.BN254)
	vk := groth16.NewVerifyingKey(ecc.BN254)
	start = time.Now()
	if err = load(filepath.Join(dir, "pk.bin"), pk); err != nil {
		return err
	}
	if err = load(filepath.Join(dir, "vk.bin"), vk); err != nil {
		return err
	}
	loadMS := float64(time.Since(start).Microseconds()) / 1000
	info, _ := debug.ReadBuildInfo()
	emit(map[string]any{"phase": "start", "os": runtime.GOOS, "arch": runtime.GOARCH, "go": info.GoVersion, "gomaxprocs": runtime.GOMAXPROCS(0), "visible_cpus": runtime.NumCPU(), "source_digest": sourceDigest, "constraints": cs.GetNbConstraints(), "compile_ms": compileMS, "key_load_ms": loadMS, "scope": "8-bit private x; public y=x^3+x+5; no RSSI/session/IVC", "fixture_hashes_verified": true, "compiled_cs_match": true})
	var prove, verify, wit []float64
	for i := -1; i < 20; i++ {
		x := []int{0, 3, 17}[(i+1)%3]
		y := x*x*x + x + 5
		start = time.Now()
		w, err := frontend.NewWitness(assign(x, y), ecc.BN254.ScalarField())
		if err != nil {
			return err
		}
		wms := float64(time.Since(start).Microseconds()) / 1000
		pub, err := w.Public()
		if err != nil {
			return err
		}
		start = time.Now()
		proof, err := groth16.Prove(cs, pk, w)
		if err != nil {
			return err
		}
		pms := float64(time.Since(start).Microseconds()) / 1000
		start = time.Now()
		if err = groth16.Verify(proof, vk, pub); err != nil {
			return err
		}
		vms := float64(time.Since(start).Microseconds()) / 1000
		if i >= 0 {
			prove = append(prove, pms)
			verify = append(verify, vms)
			wit = append(wit, wms)
		}
		proofBytes, err := encode(proof)
		if err != nil {
			return err
		}
		publicBytes, err := encode(pub)
		if err != nil {
			return err
		}
		emit(map[string]any{"phase": "sample", "iteration": i, "warmup": i < 0, "witness_ms": wms, "prove_ms": pms, "verify_ms": vms, "proof_bytes": len(proofBytes), "public_bytes": len(publicBytes), "verified": true})
		if i == -1 {
			badW, err := frontend.NewWitness(assign(x, y+1), ecc.BN254.ScalarField())
			if err != nil {
				return err
			}
			badPub, err := badW.Public()
			if err != nil {
				return err
			}
			if groth16.Verify(proof, vk, badPub) == nil {
				return fmt.Errorf("changed public value accepted")
			}
			mutated := append([]byte(nil), proofBytes...)
			mutated[0] ^= 1
			badProof := groth16.NewProof(ecc.BN254)
			_, decodeErr := badProof.ReadFrom(bytes.NewReader(mutated))
			rejected := decodeErr != nil
			if !rejected {
				rejected = groth16.Verify(badProof, vk, pub) != nil
			}
			if !rejected {
				return fmt.Errorf("tampered proof accepted")
			}
			if _, err = groth16.Prove(cs, pk, badW); err == nil {
				return fmt.Errorf("incorrect output witness accepted")
			}
			rangeW, err := frontend.NewWitness(assign(256, 256*256*256+256+5), ecc.BN254.ScalarField())
			if err != nil {
				return err
			}
			if _, err = groth16.Prove(cs, pk, rangeW); err == nil {
				return fmt.Errorf("out-of-range private input accepted")
			}
			emit(map[string]any{"phase": "negative", "changed_public_rejected": true, "tampered_proof_rejected": true, "tampered_proof_decode_rejected": decodeErr != nil, "incorrect_output_witness_rejected": true, "out_of_range_input_rejected": true})
		}
	}
	emit(map[string]any{"phase": "summary", "samples": 20, "warmups": 1, "percentile_definition": "linear interpolation of sorted samples", "prove_p50_ms": percentile(prove, .50), "prove_p95_ms": percentile(prove, .95), "prove_p99_ms": percentile(prove, .99), "verify_p50_ms": percentile(verify, .50), "verify_p95_ms": percentile(verify, .95), "witness_p50_ms": percentile(wit, .50), "process_peak_rss_bytes": peakRSS(), "all_verified": true, "private_assignment_cached": false, "proofs_saved": false})
	return nil
}
func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
