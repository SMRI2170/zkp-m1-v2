// Synthetic integer Euclidean distance; disposable local-only setup.
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
	"github.com/consensys/gnark/backend/plonk"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/constraint"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/frontend/cs/scs"
	"github.com/consensys/gnark/logger"
	"github.com/consensys/gnark/test/unsafekzg"
)

var sourceDigest string // Baked in from main.go/go.mod/go.sum by the host build.
type Circuit struct {
	D2             frontend.Variable `gnark:",public"`
	R              frontend.Variable `gnark:",public"`
	X1, Y1, X2, Y2 frontend.Variable
}

func (c *Circuit) Define(api frontend.API) error {
	for _, v := range []frontend.Variable{c.X1, c.Y1, c.X2, c.Y2} {
		api.ToBinary(v, 16)
	}
	api.ToBinary(c.D2, 33)
	api.ToBinary(c.R, 17)
	dx, dy := api.Sub(c.X1, c.X2), api.Sub(c.Y1, c.Y2)
	api.AssertIsEqual(c.D2, api.Add(api.Mul(dx, dx), api.Mul(dy, dy)))
	// Nonnegative slack bounds implement r² <= d² < (r+1)² without field comparisons.
	api.ToBinary(api.Sub(c.D2, api.Mul(c.R, c.R)), 18)
	api.ToBinary(api.Sub(api.Mul(api.Add(c.R, 1), api.Add(c.R, 1)), c.D2, 1), 18)
	return nil
}

var backend string

func setup(cs constraint.ConstraintSystem) (io.WriterTo, io.WriterTo, error) {
	if backend == "groth16" {
		return groth16.Setup(cs)
	}
	s, l, e := unsafekzg.NewSRS(cs)
	if e != nil {
		return nil, nil, e
	}
	return plonk.Setup(cs, s, l)
}

type wire interface {
	io.WriterTo
	io.ReaderFrom
}

func keys() (wire, wire) {
	if backend == "groth16" {
		return groth16.NewProvingKey(ecc.BN254), groth16.NewVerifyingKey(ecc.BN254)
	}
	return plonk.NewProvingKey(ecc.BN254), plonk.NewVerifyingKey(ecc.BN254)
}
func proveCS(cs constraint.ConstraintSystem, pk wire, w witness.Witness) (wire, error) {
	if backend == "groth16" {
		return groth16.Prove(cs, pk.(groth16.ProvingKey), w)
	}
	return plonk.Prove(cs, pk.(plonk.ProvingKey), w)
}
func verifyProof(p wire, vk wire, w witness.Witness) error {
	if backend == "groth16" {
		return groth16.Verify(p.(groth16.Proof), vk.(groth16.VerifyingKey), w)
	}
	return plonk.Verify(p.(plonk.Proof), vk.(plonk.VerifyingKey), w)
}
func newProof() wire {
	if backend == "groth16" {
		return groth16.NewProof(ecc.BN254)
	}
	return plonk.NewProof(ecc.BN254)
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
func assign(a [4]int, d, r int) *Circuit {
	return &Circuit{X1: a[0], Y1: a[1], X2: a[2], Y2: a[3], D2: d, R: r}
}
func reference(a [4]int) (int, int) {
	dx, dy := a[0]-a[2], a[1]-a[3]
	d := dx*dx + dy*dy
	r := 0
	lo, hi := 0, 92682
	for lo <= hi {
		m := (lo + hi) / 2
		if m*m <= d {
			r = m
			lo = m + 1
		} else {
			hi = m - 1
		}
	}
	return d, r
}

var cases = [][4]int{{0, 0, 0, 0}, {0, 0, 3, 4}, {3, 4, 0, 0}, {0, 0, 1, 1}, {0, 0, 65535, 65535}, {65535, 0, 0, 65535}, {100, 100, 101, 100}}

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
	if len(os.Args) != 4 {
		return fmt.Errorf("use setup|bench groth16|plonk PRIVATE_FIXTURE")
	}
	mode, dir := os.Args[1], os.Args[3]
	backend = os.Args[2]
	if backend != "groth16" && backend != "plonk" {
		return fmt.Errorf("unknown backend")
	}
	var builder frontend.NewBuilder = r1cs.NewBuilder[constraint.U64]
	if backend == "plonk" {
		builder = scs.NewBuilder[constraint.U64]
	}
	start := time.Now()
	cs, err := frontend.Compile(ecc.BN254.ScalarField(), builder, &Circuit{})
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
		pk, vk, err := setup(cs)
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
	pk, vk := keys()
	start = time.Now()
	if err = load(filepath.Join(dir, "pk.bin"), pk); err != nil {
		return err
	}
	if err = load(filepath.Join(dir, "vk.bin"), vk); err != nil {
		return err
	}
	loadMS := float64(time.Since(start).Microseconds()) / 1000
	info, _ := debug.ReadBuildInfo()
	emit(map[string]any{"phase": "start", "os": runtime.GOOS, "arch": runtime.GOARCH, "go": info.GoVersion, "gomaxprocs": runtime.GOMAXPROCS(0), "visible_cpus": runtime.NumCPU(), "backend": backend, "source_digest": sourceDigest, "constraints": cs.GetNbConstraints(), "compile_ms": compileMS, "key_load_ms": loadMS, "scope": "u16 private coordinates; public d2 u33 and floor sqrt u17; no sensor/RID claim", "fixture_hashes_verified": true, "compiled_cs_match": true})
	var prove, verify, wit []float64
	for i := -1; i < 20; i++ {
		a := cases[(i+1)%len(cases)]
		d, r := reference(a)
		start = time.Now()
		w, err := frontend.NewWitness(assign(a, d, r), ecc.BN254.ScalarField())
		if err != nil {
			return err
		}
		wms := float64(time.Since(start).Microseconds()) / 1000
		pub, err := w.Public()
		if err != nil {
			return err
		}
		start = time.Now()
		proof, err := proveCS(cs, pk, w)
		if err != nil {
			return err
		}
		pms := float64(time.Since(start).Microseconds()) / 1000
		start = time.Now()
		if err = verifyProof(proof, vk, pub); err != nil {
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
		emit(map[string]any{"phase": "sample", "iteration": i, "warmup": i < 0, "witness_ms": wms, "prove_ms": pms, "verify_ms": vms, "proof_bytes": len(proofBytes), "public_bytes": len(publicBytes), "verified": true, "case_id": (i + 1) % len(cases)})
		if i == -1 {
			badW, err := frontend.NewWitness(assign(a, d+1, r), ecc.BN254.ScalarField())
			if err != nil {
				return err
			}
			badPub, err := badW.Public()
			if err != nil {
				return err
			}
			if verifyProof(proof, vk, badPub) == nil {
				return fmt.Errorf("changed public value accepted")
			}
			mutated := append([]byte(nil), proofBytes...)
			mutated[0] ^= 1
			badProof := newProof()
			_, decodeErr := badProof.ReadFrom(bytes.NewReader(mutated))
			rejected := decodeErr != nil
			if !rejected {
				rejected = verifyProof(badProof, vk, pub) != nil
			}
			if !rejected {
				return fmt.Errorf("tampered proof accepted")
			}
			if _, err = proveCS(cs, pk, badW); err == nil {
				return fmt.Errorf("incorrect output witness accepted")
			}
			rangeW, err := frontend.NewWitness(assign([4]int{65536, 0, 0, 0}, 4294967296, 65536), ecc.BN254.ScalarField())
			if err != nil {
				return err
			}
			if _, err = proveCS(cs, pk, rangeW); err == nil {
				return fmt.Errorf("out-of-range private input accepted")
			}
			for _, bad := range []*Circuit{
				assign(a, d, r+1), assign([4]int{-1, 0, 0, 0}, 1, 1),
				assign([4]int{0, 0, 3, 4}, 24, 4), assign([4]int{0, 0, 3, 4}, 26, 5),
				assign([4]int{0, 0, 3, 4}, 25, 4), assign([4]int{0, 0, 3, 4}, 25, 6),
				assign([4]int{0, 0, 0, 0}, 0, 131072),
			} {
				bw, e := frontend.NewWitness(bad, ecc.BN254.ScalarField())
				if e != nil {
					return e
				}
				if _, e = proveCS(cs, pk, bw); e == nil {
					return fmt.Errorf("Euclidean invalid witness accepted")
				}
			}
			emit(map[string]any{"phase": "negative", "euclidean_extra_invalid_witnesses_rejected": 7, "changed_public_rejected": true, "tampered_proof_rejected": true, "tampered_proof_decode_rejected": decodeErr != nil, "incorrect_output_witness_rejected": true, "out_of_range_input_rejected": true})
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
