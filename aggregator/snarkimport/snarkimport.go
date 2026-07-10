// Package snarkimport は snarkjs(circom) の Groth16(BN254) 成果物を
// gnark ネイティブ型（backend/groth16/bn254 の VerifyingKey/Proof と公開 witness）へ変換する。
// 点の座標順は Spike A(aggregator/main.go) で検証済み（G2 は A0=c0, A1=c1）。
package snarkimport

import (
	"encoding/json"
	"fmt"
	"os"

	bn254backend "github.com/consensys/gnark/backend/groth16/bn254"
	"github.com/consensys/gnark/backend/witness"
	curve "github.com/consensys/gnark-crypto/ecc/bn254"
	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	"github.com/consensys/gnark-crypto/ecc"
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

func readJSON(path string, v interface{}) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, v)
}

func setG1(dst *curve.G1Affine, c []string) error {
	if _, err := dst.X.SetString(c[0]); err != nil {
		return err
	}
	_, err := dst.Y.SetString(c[1])
	return err
}

// snarkjs の G2 は [c0, c1] (= c0 + c1*u)。gnark E2 は A0 + A1*u。
func setG2(dst *curve.G2Affine, c [][]string) error {
	if _, err := dst.X.A0.SetString(c[0][0]); err != nil {
		return err
	}
	if _, err := dst.X.A1.SetString(c[0][1]); err != nil {
		return err
	}
	if _, err := dst.Y.A0.SetString(c[1][0]); err != nil {
		return err
	}
	_, err := dst.Y.A1.SetString(c[1][1])
	return err
}

// LoadVK は snarkjs vkey.json を gnark ネイティブ VerifyingKey へ変換する。
func LoadVK(path string) (*bn254backend.VerifyingKey, error) {
	var j vkeyJSON
	if err := readJSON(path, &j); err != nil {
		return nil, err
	}
	vk := &bn254backend.VerifyingKey{}
	if err := setG1(&vk.G1.Alpha, j.Alpha1); err != nil {
		return nil, err
	}
	if err := setG2(&vk.G2.Beta, j.Beta2); err != nil {
		return nil, err
	}
	if err := setG2(&vk.G2.Gamma, j.Gamma2); err != nil {
		return nil, err
	}
	if err := setG2(&vk.G2.Delta, j.Delta2); err != nil {
		return nil, err
	}
	vk.G1.K = make([]curve.G1Affine, len(j.IC))
	for i := range j.IC {
		if err := setG1(&vk.G1.K[i], j.IC[i]); err != nil {
			return nil, err
		}
	}
	if err := vk.Precompute(); err != nil {
		return nil, err
	}
	return vk, nil
}

// LoadProof は snarkjs proof.json を gnark ネイティブ Proof へ変換する。
func LoadProof(path string) (*bn254backend.Proof, error) {
	var j proofJSON
	if err := readJSON(path, &j); err != nil {
		return nil, err
	}
	p := &bn254backend.Proof{}
	if err := setG1(&p.Ar, j.PiA); err != nil {
		return nil, err
	}
	if err := setG2(&p.Bs, j.PiB); err != nil {
		return nil, err
	}
	if err := setG1(&p.Krs, j.PiC); err != nil {
		return nil, err
	}
	return p, nil
}

// LoadPublicWitness は snarkjs public.json（公開信号の配列）を gnark の公開 witness へ変換する。
func LoadPublicWitness(path string) (witness.Witness, error) {
	var vals []string
	if err := readJSON(path, &vals); err != nil {
		return nil, err
	}
	w, err := witness.New(ecc.BN254.ScalarField())
	if err != nil {
		return nil, err
	}
	ch := make(chan any, len(vals))
	for _, s := range vals {
		var e fr.Element
		if _, err := e.SetString(s); err != nil {
			return nil, fmt.Errorf("bad public %q: %w", s, err)
		}
		ch <- e
	}
	close(ch)
	if err := w.Fill(len(vals), 0, ch); err != nil {
		return nil, err
	}
	return w, nil
}
