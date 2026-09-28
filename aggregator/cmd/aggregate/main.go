// Spike B拡張: N=3 の witness 証明を1回路で再帰検証し、関係を回路内で強制する。
//
//	① 全 drone_id_commitment(idx10) が一致（同一ドローン）
//	② 全 time_bucket(idx13) が一致（同一時間窓）
//	③ 各 within30_and_detected(idx6) == 1
//	④ device_pubkey(idx11,12) が相異なる（Sybil対策）
//	⑤ 各 drone_auth_ok(idx15) == 1（署名付きRemote IDのみ受理）
//	⑥ consistentCount = Σ consistency_ok(idx14) を集計 → public 出力
//
// 出力: droneId / timeBucket / ConsistentCount / SuspiciousCount / Root。
// droneId と timeBucket も public output に出すことで、最終 proof を別の観測
// セッションとしてオンチェーン登録する「付け替え」を防ぐ。
package main

import (
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math/big"
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

	"uav/aggregator/membership"
	"uav/aggregator/snarkimport"
)

const N = 3

// public signal インデックス
const (
	idxWithin30  = 6
	idxDroneID   = 10
	idxPubX      = 11
	idxPubY      = 12
	idxBucket    = 13
	idxConsist   = 14
	idxDroneAuth = 15
	idxFreshness = 17
)

type AggCircuit struct {
	VK    recursion.VerifyingKey[sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl]
	Proof [N]recursion.Proof[sw_bn254.G1Affine, sw_bn254.G2Affine]
	Wit   [N]recursion.Witness[sw_bn254.ScalarField]

	// #3a: 各 device_pubkey が登録端末ルートのメンバーであることの Merkle パス
	Siblings [N][membership.Depth]frontend.Variable
	PathBits [N][membership.Depth]frontend.Variable

	// FinalAttestationRegistry / IAggregateVerifier の publicInputs 順。
	DroneID         frontend.Variable `gnark:",public"`
	TimeBucket      frontend.Variable `gnark:",public"`
	ConsistentCount frontend.Variable `gnark:",public"`
	SuspiciousCount frontend.Variable `gnark:",public"`
	Root            frontend.Variable `gnark:",public"` // 登録端末ルート（契約が deviceRoot と照合）
}

// recompose: emulated BN254 要素（4リムb×64bit）を native BN254 値へ戻す。
// 外側も BN254 なので、reduce 済みの値は native 要素に一致する。
func recompose(api frontend.API, f *emulated.Field[sw_bn254.ScalarField],
	e *emulated.Element[sw_bn254.ScalarField]) frontend.Variable {
	red := f.ReduceStrict(e)
	acc := frontend.Variable(0)
	coef := big.NewInt(1)
	for _, limb := range red.Limbs {
		acc = api.Add(acc, api.Mul(limb, new(big.Int).Set(coef)))
		coef.Lsh(coef, 64)
	}
	return acc
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
		// ⑤ drone_auth_ok == 1。leaf circuit 内で EdDSA-Poseidon 署名を
		// 検証済みのRemote IDだけを最終集計へ取り込む。
		field.AssertIsEqual(&c.Wit[i].Public[idxDroneAuth], one)
		// ⑥ consistency_ok を集計（0/1）
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

	// ⑥ 各 device_pubkey が登録端末ルート(Root)のメンバーか（#3a Sybil対策）
	for i := 0; i < N; i++ {
		axN := recompose(api, field, &c.Wit[i].Public[idxPubX])
		ayN := recompose(api, field, &c.Wit[i].Public[idxPubY])
		leaf, err := membership.Leaf(api, axN, ayN)
		if err != nil {
			return err
		}
		root, err := membership.ComputeRoot(api, leaf, c.Siblings[i], c.PathBits[i])
		if err != nil {
			return err
		}
		api.AssertIsEqual(root, c.Root)
	}

	api.AssertIsEqual(c.ConsistentCount, consCount)
	api.AssertIsEqual(api.Add(c.ConsistentCount, c.SuspiciousCount), N)
	// すでに各 leaf proof 間の一致は上で検証済み。ここでは最終 proof の公開値にも
	// 同じ観測セッションを束縛する。
	api.AssertIsEqual(c.DroneID, recompose(api, field, &c.Wit[0].Public[idxDroneID]))
	api.AssertIsEqual(c.TimeBucket, recompose(api, field, &c.Wit[0].Public[idxBucket]))
	return nil
}

// 集約に含める N 台の (ax,ay) から登録木を構築し、Root と各パスを circuit へ設定する。
func setMembership(c *AggCircuit, base string) error {
	axs := make([]*big.Int, N)
	ays := make([]*big.Int, N)
	for i := 0; i < N; i++ {
		var pub []string
		b, err := os.ReadFile(fmt.Sprintf("%s/proofs/input_dev%d_public.json", base, i))
		if err != nil {
			return err
		}
		if err := json.Unmarshal(b, &pub); err != nil {
			return err
		}
		axs[i], _ = new(big.Int).SetString(pub[idxPubX], 10)
		ays[i], _ = new(big.Int).SetString(pub[idxPubY], 10)
		if i == 0 {
			c.DroneID, _ = new(big.Int).SetString(pub[idxDroneID], 10)
			c.TimeBucket, _ = new(big.Int).SetString(pub[idxBucket], 10)
		}
	}
	leaves := make([]*big.Int, N)
	for i := range leaves {
		leaves[i] = membership.MimcHash(axs[i], ays[i])
	}
	root, siblings, bits := membership.BuildTree(leaves)
	c.Root = root
	for i := 0; i < N; i++ {
		for d := 0; d < membership.Depth; d++ {
			c.Siblings[i][d] = siblings[i][d]
			c.PathBits[i][d] = bits[i][d]
		}
	}
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
		if err := setMembership(&c, base); err != nil {
			return nil, err
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
		"proof":             "0x" + hex.EncodeToString(pm.MarshalSolidity()),
		"droneIdCommitment": asg.DroneID,
		"timeBucket":        asg.TimeBucket,
		"consistentCount":   2,
		"suspiciousCount":   1,
		"root":              asg.Root,
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
