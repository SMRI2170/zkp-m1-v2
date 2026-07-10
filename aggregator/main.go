// Spike A: snarkjs(circom) の Groth16(BN254) 証明を gnark-crypto の bn254 ペアリングで
// 直接検証する。点の形式変換（特に G2 の座標順）が正しいかを確かめる interop 検証。
//
// 使い方:
//   go run . <vkey.json> <proof.json> <public.json>
//   （引数省略時は zk-distance/build の witness 成果物を既定使用）
package main

import (
	"encoding/json"
	"fmt"
	"math/big"
	"os"

	"github.com/consensys/gnark-crypto/ecc/bn254"
)

type vkeyJSON struct {
	Alpha1 []string   `json:"vk_alpha_1"`
	Beta2  [][]string `json:"vk_beta_2"`
	Gamma2 [][]string `json:"vk_gamma_2"`
	Delta2 [][]string `json:"vk_delta_2"`
	IC     [][]string `json:"IC"`
}

type proofJSON struct {
	PiA []string   `json:"pi_a"`
	PiB [][]string `json:"pi_b"`
	PiC []string   `json:"pi_c"`
}

func mustRead(path string, v interface{}) {
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	if err := json.Unmarshal(b, v); err != nil {
		panic(err)
	}
}

func setG1(dst *bn254.G1Affine, c []string) {
	if _, err := dst.X.SetString(c[0]); err != nil {
		panic(err)
	}
	if _, err := dst.Y.SetString(c[1]); err != nil {
		panic(err)
	}
}

// snarkjs の G2 は [c0, c1]（= c0 + c1*u）。gnark E2 は A0 + A1*u。
func setG2(dst *bn254.G2Affine, c [][]string) {
	if _, err := dst.X.A0.SetString(c[0][0]); err != nil {
		panic(err)
	}
	if _, err := dst.X.A1.SetString(c[0][1]); err != nil {
		panic(err)
	}
	if _, err := dst.Y.A0.SetString(c[1][0]); err != nil {
		panic(err)
	}
	if _, err := dst.Y.A1.SetString(c[1][1]); err != nil {
		panic(err)
	}
}

func main() {
	base := "../zk-distance/build/uav_witness_attestation"
	vkPath := base + "/distance30_witness_attestation_vkey.json"
	prPath := base + "/proofs/input_dev0_proof.json"
	pubPath := base + "/proofs/input_dev0_public.json"
	if len(os.Args) == 4 {
		vkPath, prPath, pubPath = os.Args[1], os.Args[2], os.Args[3]
	}

	var vk vkeyJSON
	var pr proofJSON
	var pub []string
	mustRead(vkPath, &vk)
	mustRead(prPath, &pr)
	mustRead(pubPath, &pub)

	var alpha, a, c bn254.G1Affine
	var beta, gamma, delta, b bn254.G2Affine
	setG1(&alpha, vk.Alpha1)
	setG2(&beta, vk.Beta2)
	setG2(&gamma, vk.Gamma2)
	setG2(&delta, vk.Delta2)
	setG1(&a, pr.PiA)
	setG2(&b, pr.PiB)
	setG1(&c, pr.PiC)

	ic := make([]bn254.G1Affine, len(vk.IC))
	for i := range vk.IC {
		setG1(&ic[i], vk.IC[i])
	}
	if len(ic) != len(pub)+1 {
		panic(fmt.Sprintf("IC(%d) != public(%d)+1", len(ic), len(pub)))
	}

	// vk_x = IC[0] + Σ public_i · IC[i+1]
	var vkx bn254.G1Affine
	vkx = ic[0]
	for i, s := range pub {
		scalar, ok := new(big.Int).SetString(s, 10)
		if !ok {
			panic("bad public scalar: " + s)
		}
		var term bn254.G1Affine
		term.ScalarMultiplication(&ic[i+1], scalar)
		vkx.Add(&vkx, &term)
	}

	// e(A,B) == e(alpha,beta)·e(vk_x,gamma)·e(C,delta)
	// ⇔ e(-A,B)·e(alpha,beta)·e(vk_x,gamma)·e(C,delta) == 1
	var negA bn254.G1Affine
	negA.Neg(&a)

	ok, err := bn254.PairingCheck(
		[]bn254.G1Affine{negA, alpha, vkx, c},
		[]bn254.G2Affine{b, beta, gamma, delta},
	)
	if err != nil {
		panic(err)
	}
	fmt.Printf("public signals: %d\n", len(pub))
	fmt.Printf("within30_and_detected(idx6)=%s  consistency_ok(idx14)=%s\n", pub[6], pub[14])
	if ok {
		fmt.Println("Groth16 verify (gnark-crypto bn254): OK  ← snarkjs 証明の interop 成立")
	} else {
		fmt.Println("Groth16 verify: FAIL（点の変換/座標順を要確認）")
		os.Exit(1)
	}
}
