// Finite three-stage general recursion; no folding privacy claim or hardware authentication.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"math/big"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/constraint"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	"github.com/consensys/gnark/std/math/emulated"
	recursion "github.com/consensys/gnark/std/recursion/groth16"
)

// Index order is part of the fixture protocol; counts and membership are public and linkable.
type State struct {
	Version    frontend.Variable `gnark:",public"`
	Session    frontend.Variable `gnark:",public"`
	RID        frontend.Variable `gnark:",public"`
	Bucket     frontend.Variable `gnark:",public"`
	Policy     frontend.Variable `gnark:",public"`
	Members    frontend.Variable `gnark:",public"`
	Consistent frontend.Variable `gnark:",public"`
	Suspicious frontend.Variable `gnark:",public"`
	Steps      frontend.Variable `gnark:",public"`
}
type Observation struct {
	DroneLat, DroneLon, DroneAlt    frontend.Variable
	TargetLat, TargetLon, TargetAlt frontend.Variable
	Range                           frontend.Variable
}

func (o Observation) ok(api frontend.API) frontend.Variable {
	return rssiConsistencyOk(api, o.DroneLat, o.DroneLon, o.DroneAlt, o.TargetLat, o.TargetLon, o.TargetAlt, o.Range)
}
func (s State) values() []frontend.Variable {
	return []frontend.Variable{s.Version, s.Session, s.RID, s.Bucket, s.Policy, s.Members, s.Consistent, s.Suspicious, s.Steps}
}
func (s State) bind(api frontend.API) {
	// The finite fixture pins one session and policy. This is not a deployment registry.
	for i, v := range []int{1, 777, 424242, 100001, 20261011} {
		api.AssertIsEqual(s.values()[i], v)
	}
	api.ToBinary(s.Consistent, 2)
	api.ToBinary(s.Suspicious, 2)
	api.ToBinary(s.Steps, 2)
	api.ToBinary(s.Members, 3)
	api.AssertIsEqual(api.Add(s.Consistent, s.Suspicious), s.Steps)
}

type Leaf struct {
	State
	Observation
	member int `gnark:"-"`
}

func (c *Leaf) Define(api frontend.API) error {
	c.bind(api)
	ok := c.Observation.ok(api)
	api.AssertIsEqual(c.Consistent, ok)
	api.AssertIsEqual(c.Suspicious, api.Sub(1, ok))
	api.AssertIsEqual(c.Steps, 1)
	api.AssertIsEqual(c.Members, 1<<c.member)
	return nil
}

type Chain struct {
	State
	Observation
	PrevProof  recursion.Proof[sw_bn254.G1Affine, sw_bn254.G2Affine]
	PrevPublic recursion.Witness[sw_bn254.ScalarField]
	vk         recursion.VerifyingKey[sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl] `gnark:"-"`
	stage      int                                                                         `gnark:"-"`
}

func (c *Chain) Define(api frontend.API) error {
	c.bind(api)
	verifier, err := recursion.NewVerifier[sw_bn254.ScalarField, sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl](api)
	if err != nil {
		return err
	}
	if err = verifier.AssertProof(c.vk, c.PrevProof, c.PrevPublic); err != nil {
		return err
	}
	f, err := emulated.NewField[sw_bn254.ScalarField](api)
	if err != nil {
		return err
	}
	prev := make([]frontend.Variable, 9)
	for i := range prev {
		e := f.ReduceStrict(&c.PrevPublic.Public[i])
		acc := frontend.Variable(0)
		coef := big.NewInt(1)
		for _, limb := range e.Limbs {
			acc = api.Add(acc, api.Mul(limb, new(big.Int).Set(coef)))
			coef.Lsh(coef, 64)
		}
		prev[i] = acc
	}
	for i := 0; i < 5; i++ {
		api.AssertIsEqual(c.values()[i], prev[i])
	}
	// Fixed member ordinals A=0, B=1, C=2; excludes duplicates in this finite chain.
	api.AssertIsEqual(prev[8], c.stage-1)
	api.AssertIsEqual(prev[5], (1<<(c.stage-1))-1)
	api.AssertIsEqual(c.Members, api.Add(prev[5], 1<<(c.stage-1)))
	ok := c.Observation.ok(api)
	api.AssertIsEqual(c.Consistent, api.Add(prev[6], ok))
	api.AssertIsEqual(c.Suspicious, api.Add(prev[7], api.Sub(1, ok)))
	api.AssertIsEqual(c.Steps, api.Add(prev[8], 1))
	return nil
}
func save(path string, v io.WriterTo) error {
	f, e := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if e != nil {
		return e
	}
	defer f.Close()
	_, e = v.WriteTo(f)
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
func emit(v any) { b, _ := json.Marshal(v); fmt.Println(string(b)) }
func observation(stage int) Observation { // synthetic only; 3m altitude difference, then range outlier
	base := 100000 + stage*100
	r := 300
	if stage == 3 {
		r = 5000
	}
	return Observation{base + 1, base + 3, 1200, base + 1, base + 3, 900, r}
}
func state(stage int) State {
	c := stage
	s := 0
	if stage == 3 {
		c = 2
		s = 1
	}
	return State{1, 777, 424242, 100001, 20261011, (1 << stage) - 1, c, s, stage}
}
func run(mode, dir string, stage int) error {
	if stage < 1 || stage > 3 {
		return fmt.Errorf("stage must be 1..3")
	}
	if mode == "verify" || mode == "verify-host" {
		vk := groth16.NewVerifyingKey(ecc.BN254)
		proof := groth16.NewProof(ecc.BN254)
		pub, e := witness.New(ecc.BN254.ScalarField())
		if e != nil {
			return e
		}
		for name, v := range map[string]io.ReaderFrom{"vk": vk, "proof": proof, "public": pub} {
			if e = load(filepath.Join(dir, strconv.Itoa(stage), name+".bin"), v); e != nil {
				return e
			}
		}
		if e = groth16.Verify(proof, vk, pub, recursion.GetNativeVerifierOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField())); e != nil {
			return e
		}
		if mode == "verify-host" {
			return checkEligibility(pub, stage)
		}
		return nil
	}
	var circuit, assignment frontend.Circuit
	if stage == 1 || mode == "baseline" {
		member := 0
		st := state(1)
		if mode == "baseline" {
			member = stage - 1
			st.Members = 1 << member
			if stage == 3 {
				st.Consistent = 0
				st.Suspicious = 1
			}
		}
		circuit = &Leaf{member: member}
		assignment = &Leaf{State: st, Observation: observation(stage), member: member}
	} else {
		prevDir := filepath.Join(dir, strconv.Itoa(stage-1))
		vk := groth16.NewVerifyingKey(ecc.BN254)
		proof := groth16.NewProof(ecc.BN254)
		pub, e := witness.New(ecc.BN254.ScalarField())
		if e != nil {
			return e
		}
		for name, v := range map[string]io.ReaderFrom{"vk": vk, "proof": proof, "public": pub} {
			if e = load(filepath.Join(prevDir, name+".bin"), v); e != nil {
				return e
			}
		}
		if e = groth16.Verify(proof, vk, pub, recursion.GetNativeVerifierOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField())); e != nil {
			return fmt.Errorf("received proof: %w", e)
		}
		pvk, e := recursion.ValueOfVerifyingKeyFixed[sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl](vk)
		if e != nil {
			return e
		}
		pproof, e := recursion.ValueOfProof[sw_bn254.G1Affine, sw_bn254.G2Affine](proof)
		if e != nil {
			return e
		}
		ppublic, e := recursion.ValueOfWitness[sw_bn254.ScalarField](pub)
		if e != nil {
			return e
		}
		prevCCS := groth16.NewCS(ecc.BN254)
		if e = load(filepath.Join(prevDir, "ccs.bin"), prevCCS); e != nil {
			return e
		}
		circuit = &Chain{PrevProof: recursion.PlaceholderProof[sw_bn254.G1Affine, sw_bn254.G2Affine](prevCCS), PrevPublic: recursion.PlaceholderWitness[sw_bn254.ScalarField](prevCCS), vk: pvk, stage: stage}
		assignment = &Chain{State: state(stage), Observation: observation(stage), PrevProof: pproof, PrevPublic: ppublic, vk: pvk, stage: stage}
	}
	t := time.Now()
	ccs, e := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, circuit)
	if e != nil {
		return e
	}
	emit(map[string]any{"stage": stage, "phase": "compile", "constraints": ccs.GetNbConstraints(), "ms": time.Since(t).Milliseconds()})

	if mode != "prove" && mode != "baseline" && mode != "plan" {
		return fmt.Errorf("mode must be plan|prove|verify")
	}
	w, e := frontend.NewWitness(assignment, ecc.BN254.ScalarField())
	if e != nil {
		return e
	}
	if stage == 1 || mode == "baseline" {
		if e = ccs.IsSolved(w); e != nil {
			return fmt.Errorf("pre-setup solver: %w", e)
		}
	}
	emit(map[string]any{"stage": stage, "phase": "pre-setup-witness", "created": true, "solver_checked": stage == 1 || mode == "baseline"})
	if mode == "plan" {
		return nil
	}
	t = time.Now()
	pk, vk, e := groth16.Setup(ccs)
	if e != nil {
		return e
	}
	setupMS := time.Since(t).Milliseconds()
	out := filepath.Join(dir, strconv.Itoa(stage))
	if e = os.Mkdir(out, 0700); e != nil {
		return e
	}
	for name, v := range map[string]io.WriterTo{"vk": vk, "pk": pk, "ccs": ccs} {
		if e = save(filepath.Join(out, name+".bin"), v); e != nil {
			return e
		}
	}
	emit(map[string]any{"stage": stage, "phase": "setup", "ms": setupMS})
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
	t = time.Now()
	if e = groth16.Verify(proof, vk, pub, recursion.GetNativeVerifierOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField())); e != nil {
		return e
	}
	verifyMS := time.Since(t).Microseconds()

	// Keep setup material local; only proof+public are consumed by the next process.
	for name, v := range map[string]io.WriterTo{"proof": proof, "public": pub} {
		if e = save(filepath.Join(out, name+".bin"), v); e != nil {
			return e
		}
	}
	var publicState State
	switch a := assignment.(type) {
	case *Leaf:
		publicState = a.State
	case *Chain:
		publicState = a.State
	}
	emit(map[string]any{"stage": stage, "phase": "prove", "pid": os.Getpid(), "setup_ms": setupMS, "prove_ms": proveMS, "verify_us": verifyMS, "state": publicState, "verified": true})
	return negative(ccs, pk, assignment, stage)
}
func negative(ccs constraint.ConstraintSystem, pk groth16.ProvingKey, assignment frontend.Circuit, stage int) error {
	// Solver tests supplement proof verification; never present these as forged-proof verification.
	for _, kind := range []string{"session", "rid", "policy", "duplicate", "count"} {
		var a frontend.Circuit
		if leaf, ok := assignment.(*Leaf); ok {
			x := *leaf
			a = &x
			switch kind {
			case "session":
				x.Session = 778
			case "rid":
				x.RID = 424243
			case "policy":
				x.Policy = 0
			case "duplicate":
				x.Members = 0
			case "count":
				x.Consistent = 3
			}
		}
		if chain, ok := assignment.(*Chain); ok {
			x := *chain
			a = &x
			switch kind {
			case "session":
				x.Session = 778
			case "rid":
				x.RID = 424243
			case "policy":
				x.Policy = 0
			case "duplicate":
				x.Members = 0
			case "count":
				x.Consistent = 3
			}
		}
		w, e := frontend.NewWitness(a, ecc.BN254.ScalarField())
		if e != nil {
			return e
		}
		_, e = groth16.Prove(ccs, pk, w, recursion.GetNativeProverOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField()))
		emit(map[string]any{"stage": stage, "phase": "negative-prover", "case": kind, "rejected": e != nil})
		if e == nil {
			return fmt.Errorf("negative %s accepted", kind)
		}
	}
	return nil
}
func main() {
	if len(os.Args) == 4 && os.Args[1] == "bench-singleton" {
		stage, err := strconv.Atoi(os.Args[3])
		if err == nil {
			err = benchSingleton(os.Args[2], stage)
		}
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		return
	}

	if len(os.Args) == 3 && os.Args[1] == "joint" {
		if err := joint(os.Args[2]); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		return
	}

	if len(os.Args) != 4 {
		fmt.Fprintln(os.Stderr, "usage: private-pcd plan|prove|verify PRIVATE_DIR STAGE")
		os.Exit(2)
	}
	stage, e := strconv.Atoi(os.Args[3])
	if e == nil {
		e = run(os.Args[1], os.Args[2], stage)
	}
	if e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
}
