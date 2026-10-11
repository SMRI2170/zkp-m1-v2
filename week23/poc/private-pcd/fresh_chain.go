package main

// New independent prover processes over deliberately inspected, unchanged setup
// fixtures. The transferred objects contain proof/public only, not assignments.
import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	recursion "github.com/consensys/gnark/std/recursion/groth16"
)

func init() {
	if len(os.Args) > 1 && os.Args[1] == "fresh-chain" {
		if len(os.Args) != 5 {
			fmt.Fprintln(os.Stderr, "fresh-chain INSPECTED_FIXTURES NEW_OUTPUT STAGE")
			os.Exit(2)
		}
		stage, e := strconv.Atoi(os.Args[4])
		if e == nil {
			e = freshChain(os.Args[2], os.Args[3], stage)
		}
		if e != nil {
			fmt.Fprintln(os.Stderr, e)
			os.Exit(1)
		}
		os.Exit(0)
	}
}
func digestFile(path string) (string, error) {
	f, e := os.Open(path)
	if e != nil {
		return "", e
	}
	defer f.Close()
	h := sha256.New()
	if _, e = io.Copy(h, f); e != nil {
		return "", e
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}
func freshObservation(stage int) Observation {
	lat, lon, alt := 812345000+stage*600, 914567800+stage*800, 345123+stage*41
	r := 312 + stage
	if stage == 3 {
		r = 5317
	}
	return Observation{lat, lon, alt, lat + 1, lon + 3, alt - 300, r}
}
func freshChain(base, out string, stage int) error {
	if stage < 1 || stage > 3 {
		return fmt.Errorf("stage")
	}
	var inspected struct {
		Sources   map[string]string `json:"sources"`
		Artifacts map[string]string `json:"artifacts"`
	}
	b, e := os.ReadFile(filepath.Join(out, "inspected-fixtures.json"))
	if e != nil {
		return e
	}
	if e = json.Unmarshal(b, &inspected); e != nil {
		return e
	}
	root, e := os.Getwd()
	if e != nil {
		return e
	}
	for path, pin := range inspected.Sources {
		h, e := digestFile(filepath.Join(root, path))
		if e != nil {
			return e
		}
		if h != pin {
			return fmt.Errorf("source mismatch: %s", path)
		}
	}
	for path, pin := range inspected.Artifacts {
		h, e := digestFile(filepath.Join(base, path))
		if e != nil {
			return e
		}
		if h != pin {
			return fmt.Errorf("artifact mismatch: %s; preserve fixtures", path)
		}
	}
	var circuit, assignment frontend.Circuit
	if stage == 1 {
		circuit = &Leaf{member: 0}
		assignment = &Leaf{State: state(1), Observation: freshObservation(1), member: 0}
	} else {
		previous := filepath.Join(out, strconv.Itoa(stage-1))
		trustedVK := groth16.NewVerifyingKey(ecc.BN254)
		proof := groth16.NewProof(ecc.BN254)
		pub, e := witness.New(ecc.BN254.ScalarField())
		if e != nil {
			return e
		}
		for name, v := range map[string]io.ReaderFrom{"proof": proof, "public": pub} {
			if e = load(filepath.Join(previous, name+".bin"), v); e != nil {
				return e
			}
		}
		if e = load(filepath.Join(base, strconv.Itoa(stage-1), "vk.bin"), trustedVK); e != nil {
			return e
		}
		if e = groth16.Verify(proof, trustedVK, pub, recursion.GetNativeVerifierOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField())); e != nil {
			return e
		}
		vk, e := recursion.ValueOfVerifyingKeyFixed[sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl](trustedVK)
		if e != nil {
			return e
		}
		pp, e := recursion.ValueOfProof[sw_bn254.G1Affine, sw_bn254.G2Affine](proof)
		if e != nil {
			return e
		}
		pw, e := recursion.ValueOfWitness[sw_bn254.ScalarField](pub)
		if e != nil {
			return e
		}
		previousCCS := groth16.NewCS(ecc.BN254)
		if e = load(filepath.Join(base, strconv.Itoa(stage-1), "ccs.bin"), previousCCS); e != nil {
			return e
		}
		circuit = &Chain{PrevProof: recursion.PlaceholderProof[sw_bn254.G1Affine, sw_bn254.G2Affine](previousCCS), PrevPublic: recursion.PlaceholderWitness[sw_bn254.ScalarField](previousCCS), vk: vk, stage: stage}
		assignment = &Chain{State: state(stage), Observation: freshObservation(stage), PrevProof: pp, PrevPublic: pw, vk: vk, stage: stage}
	}
	t := time.Now()
	ccs, e := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, circuit)
	if e != nil {
		return e
	}
	var rebuilt bytes.Buffer
	if _, e = ccs.WriteTo(&rebuilt); e != nil {
		return e
	}
	hash := sha256.Sum256(rebuilt.Bytes())
	key := strconv.Itoa(stage) + "/ccs.bin"
	if hex.EncodeToString(hash[:]) != inspected.Artifacts[key] {
		return fmt.Errorf("rebuilt CCS differs: %s", key)
	}
	emit(map[string]any{"phase": "fresh-compile", "stage": stage, "rebuilt_ccs_identical": true, "constraints": ccs.GetNbConstraints(), "ms": time.Since(t).Milliseconds()})
	pk := groth16.NewProvingKey(ecc.BN254)
	vk := groth16.NewVerifyingKey(ecc.BN254)
	for name, v := range map[string]io.ReaderFrom{"pk": pk, "vk": vk} {
		if e = load(filepath.Join(base, strconv.Itoa(stage), name+".bin"), v); e != nil {
			return e
		}
	}
	w, e := frontend.NewWitness(assignment, ecc.BN254.ScalarField())
	if e != nil {
		return e
	}
	t = time.Now()
	proof, e := groth16.Prove(ccs, pk, w, recursion.GetNativeProverOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField()))
	if e != nil {
		return e
	}
	proveMS := time.Since(t).Milliseconds()
	pub, e := w.Public()
	if e != nil {
		return e
	}
	if e = groth16.Verify(proof, vk, pub, recursion.GetNativeVerifierOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField())); e != nil {
		return e
	}
	directory := filepath.Join(out, strconv.Itoa(stage))
	if e = os.Mkdir(directory, 0700); e != nil {
		return e
	}
	for name, v := range map[string]io.WriterTo{"proof": proof, "public": pub} {
		if e = save(filepath.Join(directory, name+".bin"), v); e != nil {
			return e
		}
	}
	// Operator-local verifier metadata only; this symlink is not a network payload.
	abs, e := filepath.Abs(filepath.Join(base, strconv.Itoa(stage), "vk.bin"))
	if e != nil {
		return e
	}
	if e = os.Symlink(abs, filepath.Join(directory, "vk.bin")); e != nil {
		return e
	}
	emit(map[string]any{"phase": "fresh-prove", "stage": stage, "pid": os.Getpid(), "verified": true, "prove_ms": proveMS, "state": state(stage), "private_assignment_cached": false, "prior_assignment_read": false, "setup": "inspected existing fixture; all hashes/source/CCS matched"})
	return nil
}
