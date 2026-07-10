// Spike B拡張: N=3 の witness 証明を1回路で再帰検証し、関係を回路内で強制する。
//   ① 全 drone_id_commitment(idx10) が一致（同一ドローン）
//   ② 全 time_bucket(idx13) が一致（同一時間窓）
//   ③ 各 within30_and_detected(idx6) == 1
//   ④ device_pubkey(idx11,12) が相異なる（Sybil対策）
//   ⑤ consistentCount = Σ consistency_ok(idx14) を集計 → public 出力
// 出力: ConsistentCount / SuspiciousCount（=N-ConsistentCount）。
package main

import (
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/solidity"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	"github.com/consensys/gnark/std/math/emulated"
	recursion "github.com/consensys/gnark/std/recursion/groth16"

	"uav/aggregator/snarkimport"
)

const N = 3

// public signal インデックス
const (
	idxWithin30 = 6
	idxDroneID  = 10
	idxPubX     = 11
	idxPubY     = 12
	idxBucket   = 13
	idxConsist  = 14
)

type AggCircuit struct {
	VK    recursion.VerifyingKey[sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl]
	Proof [N]recursion.Proof[sw_bn254.G1Affine, sw_bn254.G2Affine]
	Wit   [N]recursion.Witness[sw_bn254.ScalarField]

	ConsistentCount frontend.Variable `gnark:",public"`
	SuspiciousCount frontend.Variable `gnark:",public"`
}

func (c *AggCircuit) Define(api frontend.API) error {
	verifier, err := recursion.NewVerifier[sw_bn254.ScalarField, sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl](api)
	if err != nil {
		return err
	}
	field, err := emulated.NewField[sw_bn254.ScalarField](api)
	if err != nil {
		return err
	}
	one := field.NewElement(1)

	consCount := frontend.Variable(0)
	for i := 0; i < N; i++ {
		// 各証明を回路内検証
		if err := verifier.AssertProof(c.VK, c.Proof[i], c.Wit[i]); err != nil {
			return err
		}
		// ① 同一ドローン ② 同一時間窓
		field.AssertIsEqual(&c.Wit[i].Public[idxDroneID], &c.Wit[0].Public[idxDroneID])
		field.AssertIsEqual(&c.Wit[i].Public[idxBucket], &c.Wit[0].Public[idxBucket])
		// ③ within30_and_detected == 1
		field.AssertIsEqual(&c.Wit[i].Public[idxWithin30], one)
		// ⑤ consistency_ok を集計（0/1）
		isZero := field.IsZero(&c.Wit[i].Public[idxConsist]) // 1 なら consistency==0
		consCount = api.Add(consCount, api.Sub(1, isZero))
	}

	// ④ device_pubkey が相異なる（i<j で (x,y) が両方一致しないこと）
	for i := 0; i < N; i++ {
		for j := i + 1; j < N; j++ {
			eqX := field.IsZero(field.Sub(&c.Wit[i].Public[idxPubX], &c.Wit[j].Public[idxPubX]))
			eqY := field.IsZero(field.Sub(&c.Wit[i].Public[idxPubY], &c.Wit[j].Public[idxPubY]))
			api.AssertIsEqual(api.Mul(eqX, eqY), 0)
		}
	}

	api.AssertIsEqual(c.ConsistentCount, consCount)
	api.AssertIsEqual(api.Add(c.ConsistentCount, c.SuspiciousCount), N)
	return nil
}

func main() {
	base := "../zk-distance/build/uav_witness_attestation"
	vkPath := base + "/distance30_witness_attestation_vkey.json"
	nativeVK, err := snarkimport.LoadVK(vkPath)
	must(err)

	// N 端末の証明/公開witnessを読み込む（dev0,dev1 整合 / dev2 詐称）
	load := func() (*AggCircuit, error) {
		var c AggCircuit
		vk, err := recursion.ValueOfVerifyingKey[sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl](nativeVK)
		if err != nil {
			return nil, err
		}
		c.VK = vk
		for i := 0; i < N; i++ {
			pr, err := snarkimport.LoadProof(fmt.Sprintf("%s/proofs/input_dev%d_proof.json", base, i))
			if err != nil {
				return nil, err
			}
			pub, err := snarkimport.LoadPublicWitness(fmt.Sprintf("%s/proofs/input_dev%d_public.json", base, i))
			if err != nil {
				return nil, err
			}
			cp, err := recursion.ValueOfProof[sw_bn254.G1Affine, sw_bn254.G2Affine](pr)
			if err != nil {
				return nil, err
			}
			cw, err := recursion.ValueOfWitness[sw_bn254.ScalarField](pub)
			if err != nil {
				return nil, err
			}
			c.Proof[i] = cp
			c.Wit[i] = cw
		}
		return &c, nil
	}

	tmpl, err := load()
	must(err)
	fmt.Printf("[1/3] Compiling aggregate circuit (N=%d)...\n", N)
	t0 := time.Now()
	ccs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, tmpl)
	must(err)
	fmt.Printf("   constraints=%d  (compile %s)\n", ccs.GetNbConstraints(), time.Since(t0).Round(time.Millisecond))

	asg, err := load() // compile で汚染されるので作り直す
	must(err)
	asg.ConsistentCount = 2 // dev0,dev1 整合 / dev2 詐称
	asg.SuspiciousCount = 1
	fullWit, err := frontend.NewWitness(asg, ecc.BN254.ScalarField())
	must(err)

	// 集約回路は commitment を含むため recursion 用オプション、
	// かつオンチェーン検証のため Solidity ターゲットで prove/verify する。
	proverOpts := []backend.ProverOption{
		recursion.GetNativeProverOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField()),
		solidity.WithProverTargetSolidityVerifier(backend.GROTH16),
	}
	verifierOpts := []backend.VerifierOption{
		recursion.GetNativeVerifierOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField()),
		solidity.WithVerifierTargetSolidityVerifier(backend.GROTH16),
	}

	fmt.Println("[2/4] Groth16 setup...")
	t0 = time.Now()
	pk, vk, err := groth16.Setup(ccs)
	must(err)
	fmt.Printf("   setup %s\n", time.Since(t0).Round(time.Millisecond))

	fmt.Println("[3/4] Prove + Verify...")
	t0 = time.Now()
	proof, err := groth16.Prove(ccs, pk, fullWit, proverOpts...)
	must(err)
	fmt.Printf("   prove %s\n", time.Since(t0).Round(time.Millisecond))
	pubOnly, err := fullWit.Public()
	must(err)
	t0 = time.Now()
	must(groth16.Verify(proof, vk, pubOnly, verifierOpts...))
	fmt.Printf("   verify %s (go)\n", time.Since(t0).Round(time.Millisecond))

	fmt.Println("[4/4] Export Solidity verifier + proof calldata...")
	sol, err := os.Create("../contracts/contracts/AggregateVerifier.sol")
	must(err)
	must(vk.ExportSolidity(sol))
	must(sol.Close())

	pm, ok := proof.(interface{ MarshalSolidity() []byte })
	if !ok {
		panic("proof has no MarshalSolidity")
	}
	out := map[string]any{
		"proof":           "0x" + hex.EncodeToString(pm.MarshalSolidity()),
		"consistentCount": 2,
		"suspiciousCount": 1,
	}
	buf, _ := json.MarshalIndent(out, "", "  ")
	must(os.WriteFile("../contracts/test/fixtures/aggregate.json", buf, 0644))

	fmt.Printf("OK: N=%d 集約・consistentCount=2 を検証。AggregateVerifier.sol と aggregate.json を出力\n", N)
}

func must(err error) {
	if err != nil {
		panic(err)
	}
}
