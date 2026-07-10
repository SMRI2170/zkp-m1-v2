// Spike B: gnark 回路内で snarkjs の Groth16(BN254) 証明を1個検証する（emulated BN254）。
// まずコンパイルして制約数を出し、次に Groth16 setup/prove/verify を時間計測する。
// 目的は「回路内検証が現実的な重さか」の feasibility 判定。
package main

import (
	"fmt"
	"os"
	"time"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	recursion "github.com/consensys/gnark/std/recursion/groth16"

	"uav/aggregator/snarkimport"
)

// 内側(circom/BN254)の証明を、外側 BN254 回路内で emulated 検証する。
type VerifyCircuit struct {
	Proof   recursion.Proof[sw_bn254.G1Affine, sw_bn254.G2Affine]
	VK      recursion.VerifyingKey[sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl]
	Witness recursion.Witness[sw_bn254.ScalarField] `gnark:",public"`
}

func (c *VerifyCircuit) Define(api frontend.API) error {
	v, err := recursion.NewVerifier[sw_bn254.ScalarField, sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl](api)
	if err != nil {
		return err
	}
	return v.AssertProof(c.VK, c.Proof, c.Witness)
}

func main() {
	base := "../zk-distance/build/uav_witness_attestation"
	if len(os.Args) == 2 {
		base = os.Args[1]
	}
	vkPath := base + "/distance30_witness_attestation_vkey.json"
	prPath := base + "/proofs/input_dev0_proof.json"
	pubPath := base + "/proofs/input_dev0_public.json"

	nativeVK, err := snarkimport.LoadVK(vkPath)
	must(err)
	nativeProof, err := snarkimport.LoadProof(prPath)
	must(err)
	pubWit, err := snarkimport.LoadPublicWitness(pubPath)
	must(err)

	// compile 用テンプレート値（compile は回路変数へ破壊的置換するので assignment とは別に作る）
	tvk, err := recursion.ValueOfVerifyingKey[sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl](nativeVK)
	must(err)
	tproof, err := recursion.ValueOfProof[sw_bn254.G1Affine, sw_bn254.G2Affine](nativeProof)
	must(err)
	twit, err := recursion.ValueOfWitness[sw_bn254.ScalarField](pubWit)
	must(err)

	fmt.Println("[1/3] Compiling in-circuit verifier (emulated BN254)...")
	t0 := time.Now()
	ccs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &VerifyCircuit{Proof: tproof, VK: tvk, Witness: twit})
	must(err)
	fmt.Printf("   constraints=%d  (compile %s)\n", ccs.GetNbConstraints(), time.Since(t0).Round(time.Millisecond))

	// assignment 用に値を作り直す（compile で汚染された値を使わない）
	avk, err := recursion.ValueOfVerifyingKey[sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl](nativeVK)
	must(err)
	aproof, err := recursion.ValueOfProof[sw_bn254.G1Affine, sw_bn254.G2Affine](nativeProof)
	must(err)
	awit, err := recursion.ValueOfWitness[sw_bn254.ScalarField](pubWit)
	must(err)
	fullWit, err := frontend.NewWitness(&VerifyCircuit{Proof: aproof, VK: avk, Witness: awit}, ecc.BN254.ScalarField())
	must(err)

	// 再帰検証回路は commitment を含むため、prove/verify に recursion 用オプションが要る
	proverOpt := recursion.GetNativeProverOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField())
	verifierOpt := recursion.GetNativeVerifierOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField())

	fmt.Println("[2/3] Groth16 setup...")
	t0 = time.Now()
	pk, vk, err := groth16.Setup(ccs)
	must(err)
	fmt.Printf("   setup %s\n", time.Since(t0).Round(time.Millisecond))

	fmt.Println("[3/3] Prove + Verify...")
	t0 = time.Now()
	proof, err := groth16.Prove(ccs, pk, fullWit, proverOpt)
	must(err)
	fmt.Printf("   prove %s\n", time.Since(t0).Round(time.Millisecond))
	pubOnly, err := fullWit.Public()
	must(err)
	t0 = time.Now()
	must(groth16.Verify(proof, vk, pubOnly, verifierOpt))
	fmt.Printf("   verify %s  → OK: 回路内で snarkjs 証明を検証できた\n", time.Since(t0).Round(time.Millisecond))
}

func must(err error) {
	if err != nil {
		panic(err)
	}
}
