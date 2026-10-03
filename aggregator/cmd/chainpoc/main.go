// Step A/B PoC（NEXT_STEPS.md §1, §3）:
//   Step A: 各ノードが前の証明 π_{i-1} を自分の回路内で再帰検証（内包）し、
//           自分の観測を足した新しい証明 π_i を作る「逐次チェーン」を
//           gnark(BN254, std/recursion/groth16) で 3 ステップ連結して動かす。
//   Step B: 各ステップの Ok(consistency_ok) を外部入力として受け取るのではなく、
//           circuits/remoteid_consistency_rel.circom と同じ「相対許容帯」判定を
//           回路内で計算する（RSSI実測レンジと申告位置からの幾何距離の相対整合）。
//
// 構成（自己再帰のブートストラップ、詳細 week20/06 §1.2）:
//   GenesisCircuit … チェーンの起点(参加者1)。前の証明は無い。z_1 を出す。
//   ChainCircuit   … 参加者2以降。前の証明(Genesis or Chain)を回路内で再帰検証して
//                     内包し、観測を足した z_i を出す。
//
// 公開状態 z = (DroneID, TimeBucket, ConsistentCount, SuspiciousCount, StepCount)。
// 座標・生RSSIは回路の外に出さない（各ステップの private 入力のまま、公開されるのは
// 集計 z のみ）。
package main

import (
	"fmt"
	"math/big"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/constraint"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	"github.com/consensys/gnark/std/math/cmp"
	"github.com/consensys/gnark/std/math/emulated"
	recursion "github.com/consensys/gnark/std/recursion/groth16"
)

// z の中の公開信号インデックス（PrevWit.Public の並び = 各circuitのstructフィールド宣言順）
const (
	zIdxDroneID         = 0
	zIdxTimeBucket      = 1
	zIdxConsistentCount = 2
	zIdxSuspiciousCount = 3
	zIdxStepCount       = 4
)

// circuits/remoteid_consistency_rel.circom と同じ係数（相対許容 ±90%）。
const (
	latCmNum = 11132000
	lonCmNum = 9128800
	geoDen   = 10000000
	tolNum   = 90
	tolDen   = 100
)

// absDiff: |a-b|（circuits/lib_uav_safety.circom の AbsDiff と同じ発想。
// gnark は体が大きい(BN254)ので a-b の符号を cmp.IsLess で判定して Select する）。
func absDiff(api frontend.API, a, b frontend.Variable) frontend.Variable {
	aLtB := cmp.IsLess(api, a, b)
	return api.Select(aLtB, api.Sub(b, a), api.Sub(a, b))
}

// rssiConsistencyOk: circuits/remoteid_consistency_rel.circom の RemoteIdConsistencyRel と
// 同じ計算。申告位置(drone)と自分の位置(target)から求めた幾何距離の二乗と、RSSIから求めた
// 実測レンジ(measuredRangeCm)の相対許容帯 [measured*(1-r), measured*(1+r)] を整数のまま
// （平方根/除算を避けて）比較する。r = tolNum/tolDen。
func rssiConsistencyOk(api frontend.API,
	droneLat, droneLon, droneAlt,
	targetLat, targetLon, targetAlt,
	measuredRangeCm frontend.Variable) frontend.Variable {

	dLat := absDiff(api, droneLat, targetLat)
	dLon := absDiff(api, droneLon, targetLon)
	dAlt := absDiff(api, droneAlt, targetAlt)

	latScaled := api.Mul(dLat, latCmNum)
	lonScaled := api.Mul(dLon, lonCmNum)
	altScaled := api.Mul(dAlt, geoDen)

	claimedDistSq := api.Add(
		api.Mul(latScaled, latScaled),
		api.Mul(lonScaled, lonScaled),
		api.Mul(altScaled, altScaled),
	)

	const lower = tolDen - tolNum
	const upper = tolDen + tolNum

	base := api.Mul(measuredRangeCm, geoDen)
	lowerSq := api.Mul(api.Mul(base, lower), api.Mul(base, lower))
	upperSq := api.Mul(api.Mul(base, upper), api.Mul(base, upper))

	claimedScaled := api.Mul(claimedDistSq, tolDen*tolDen)

	geLower := cmp.IsLessOrEqual(api, lowerSq, claimedScaled)
	leUpper := cmp.IsLessOrEqual(api, claimedScaled, upperSq)
	return api.Mul(geLower, leUpper)
}

type GenesisCircuit struct {
	DroneID         frontend.Variable `gnark:",public"`
	TimeBucket      frontend.Variable `gnark:",public"`
	ConsistentCount frontend.Variable `gnark:",public"`
	SuspiciousCount frontend.Variable `gnark:",public"`
	StepCount       frontend.Variable `gnark:",public"`

	// RSSI整合の入力（回路の外に出ない）。circuits/remoteid_consistency_rel.circom と同じ形。
	DroneLat, DroneLon, DroneAlt    frontend.Variable // 放送位置（申告値）
	TargetLat, TargetLon, TargetAlt frontend.Variable // 自分(witness)の位置
	MeasuredRangeCm                 frontend.Variable // RSSIから算出した実測レンジ(cm)
}

func (c *GenesisCircuit) Define(api frontend.API) error {
	ok := rssiConsistencyOk(api, c.DroneLat, c.DroneLon, c.DroneAlt, c.TargetLat, c.TargetLon, c.TargetAlt, c.MeasuredRangeCm)
	api.AssertIsEqual(c.ConsistentCount, ok)
	api.AssertIsEqual(c.SuspiciousCount, api.Sub(1, ok))
	api.AssertIsEqual(c.StepCount, 1)
	return nil
}

type ChainCircuit struct {
	DroneID         frontend.Variable `gnark:",public"`
	TimeBucket      frontend.Variable `gnark:",public"`
	ConsistentCount frontend.Variable `gnark:",public"`
	SuspiciousCount frontend.Variable `gnark:",public"`
	StepCount       frontend.Variable `gnark:",public"`

	DroneLat, DroneLon, DroneAlt    frontend.Variable
	TargetLat, TargetLon, TargetAlt frontend.Variable
	MeasuredRangeCm                 frontend.Variable

	PrevVK    recursion.VerifyingKey[sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl]
	PrevProof recursion.Proof[sw_bn254.G1Affine, sw_bn254.G2Affine]
	PrevWit   recursion.Witness[sw_bn254.ScalarField]
}

// recompose: emulated BN254 要素（native と同じ体）を native frontend.Variable へ戻す。
// aggregator/cmd/aggregate/main.go と同じ手法。
func recompose(api frontend.API, f *emulated.Field[sw_bn254.ScalarField], e *emulated.Element[sw_bn254.ScalarField]) frontend.Variable {
	red := f.ReduceStrict(e)
	acc := frontend.Variable(0)
	coef := big.NewInt(1)
	for _, limb := range red.Limbs {
		acc = api.Add(acc, api.Mul(limb, new(big.Int).Set(coef)))
		coef.Lsh(coef, 64)
	}
	return acc
}

func (c *ChainCircuit) Define(api frontend.API) error {
	ok := rssiConsistencyOk(api, c.DroneLat, c.DroneLon, c.DroneAlt, c.TargetLat, c.TargetLon, c.TargetAlt, c.MeasuredRangeCm)

	// (1) 前の証明 π_{i-1} を回路内で再帰検証 ＝ 内包
	verifier, err := recursion.NewVerifier[sw_bn254.ScalarField, sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl](api)
	if err != nil {
		return err
	}
	if err := verifier.AssertProof(c.PrevVK, c.PrevProof, c.PrevWit); err != nil {
		return err
	}

	field, err := emulated.NewField[sw_bn254.ScalarField](api)
	if err != nil {
		return err
	}
	prevDroneID := recompose(api, field, &c.PrevWit.Public[zIdxDroneID])
	prevTimeBucket := recompose(api, field, &c.PrevWit.Public[zIdxTimeBucket])
	prevConsistentCount := recompose(api, field, &c.PrevWit.Public[zIdxConsistentCount])
	prevSuspiciousCount := recompose(api, field, &c.PrevWit.Public[zIdxSuspiciousCount])
	prevStepCount := recompose(api, field, &c.PrevWit.Public[zIdxStepCount])

	// (2) 同一ドローン・同一時間窓 が前の累積 z_{i-1} と一致
	api.AssertIsEqual(c.DroneID, prevDroneID)
	api.AssertIsEqual(c.TimeBucket, prevTimeBucket)
	// (3)(4) 状態更新: consistent/suspicious += ok/(1-ok), step += 1 → z_i を public 出力
	api.AssertIsEqual(c.ConsistentCount, api.Add(prevConsistentCount, ok))
	api.AssertIsEqual(c.SuspiciousCount, api.Add(prevSuspiciousCount, api.Sub(1, ok)))
	api.AssertIsEqual(c.StepCount, api.Add(prevStepCount, 1))
	return nil
}

const (
	droneID    = 424242
	timeBucket = 100001
)

// observation: RSSI整合判定への入力7つ。実測値は
// zk-distance/samples/sample_remoteid_{consistent,spoof}.json をそのまま流用
// （申告位置・自位置は共通、measuredRangeCmだけ変えて「整合」「なりすまし(乖離)」を作る）。
type observation struct {
	droneLat, droneLon, droneAlt    int
	targetLat, targetLon, targetAlt int
	measuredRangeCm                 int
}

var (
	// 申告位置と自位置から幾何距離 ≈341cm。measured=341cm は許容帯内 → consistent(ok=1)。
	obsConsistent = observation{1256891390, 3196917000, 1200, 1256891590, 3196917180, 1000, 341}
	// 同じ位置関係だが measured=5000cm（50m）を主張 → 幾何距離(≈341cm)と大きく乖離 → ok=0。
	obsSpoofed = observation{1256891390, 3196917000, 1200, 1256891590, 3196917180, 1000, 5000}
)

func must(err error) {
	if err != nil {
		panic(err)
	}
}

func proveGenesis(ccs constraint.ConstraintSystem, pk groth16.ProvingKey, obs observation, okExpected int) (groth16.Proof, witness.Witness, error) {
	assignment := &GenesisCircuit{
		DroneID: droneID, TimeBucket: timeBucket,
		ConsistentCount: okExpected, SuspiciousCount: 1 - okExpected, StepCount: 1,
		DroneLat: obs.droneLat, DroneLon: obs.droneLon, DroneAlt: obs.droneAlt,
		TargetLat: obs.targetLat, TargetLon: obs.targetLon, TargetAlt: obs.targetAlt,
		MeasuredRangeCm: obs.measuredRangeCm,
	}
	w, err := frontend.NewWitness(assignment, ecc.BN254.ScalarField())
	if err != nil {
		return nil, nil, err
	}
	proof, err := groth16.Prove(ccs, pk, w)
	if err != nil {
		return nil, nil, err
	}
	pub, err := w.Public()
	if err != nil {
		return nil, nil, err
	}
	return proof, pub, nil
}

func chainProverOpts() []backend.ProverOption {
	return []backend.ProverOption{recursion.GetNativeProverOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField())}
}
func chainVerifierOpts() []backend.VerifierOption {
	return []backend.VerifierOption{recursion.GetNativeVerifierOptions(ecc.BN254.ScalarField(), ecc.BN254.ScalarField())}
}

func chainAssignment(prevVK groth16.VerifyingKey, prevProof groth16.Proof, prevWit witness.Witness,
	newDroneID, newTimeBucket, newConsistentCount, newSuspiciousCount, newStepCount int,
	obs observation) (*ChainCircuit, error) {
	vk, err := recursion.ValueOfVerifyingKey[sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl](prevVK)
	if err != nil {
		return nil, err
	}
	pr, err := recursion.ValueOfProof[sw_bn254.G1Affine, sw_bn254.G2Affine](prevProof)
	if err != nil {
		return nil, err
	}
	wit, err := recursion.ValueOfWitness[sw_bn254.ScalarField](prevWit)
	if err != nil {
		return nil, err
	}
	return &ChainCircuit{
		DroneID: newDroneID, TimeBucket: newTimeBucket,
		ConsistentCount: newConsistentCount, SuspiciousCount: newSuspiciousCount, StepCount: newStepCount,
		DroneLat: obs.droneLat, DroneLon: obs.droneLon, DroneAlt: obs.droneAlt,
		TargetLat: obs.targetLat, TargetLon: obs.targetLon, TargetAlt: obs.targetAlt,
		MeasuredRangeCm: obs.measuredRangeCm,
		PrevVK:          vk, PrevProof: pr, PrevWit: wit,
	}, nil
}

func proveChain(ccs constraint.ConstraintSystem, pk groth16.ProvingKey, assignment *ChainCircuit) (groth16.Proof, witness.Witness, error) {
	w, err := frontend.NewWitness(assignment, ecc.BN254.ScalarField())
	if err != nil {
		return nil, nil, err
	}
	proof, err := groth16.Prove(ccs, pk, w, chainProverOpts()...)
	if err != nil {
		return nil, nil, err
	}
	pub, err := w.Public()
	if err != nil {
		return nil, nil, err
	}
	return proof, pub, nil
}

func main() {
	fmt.Println("[setup] Genesis circuit")
	genesisCcs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &GenesisCircuit{})
	must(err)
	pkG, vkG, err := groth16.Setup(genesisCcs)
	must(err)
	fmt.Printf("  genesis constraints=%d\n", genesisCcs.GetNbConstraints())

	fmt.Println("[setup] Chain circuit A（Genesisを再帰検証する回路）")
	// 自己再帰のブートストラップ注記（詳細 week20/06 §1.2）: GenesisCircuit と ChainCircuit は
	// 内部構造（再帰検証器を含むかどうか）が異なるため、「前の証明を受け取る箱」のサイズは
	// 前段の ccs 形状に依存する。段ごとに立て直す。
	//   chainCcsA: Genesis を検証する形（step2 用）
	//   chainCcsB: chainCcsA を検証する形（step3 用）
	chainTemplateA := &ChainCircuit{
		PrevVK:    recursion.PlaceholderVerifyingKey[sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl](genesisCcs),
		PrevProof: recursion.PlaceholderProof[sw_bn254.G1Affine, sw_bn254.G2Affine](genesisCcs),
		PrevWit:   recursion.PlaceholderWitness[sw_bn254.ScalarField](genesisCcs),
	}
	chainCcsA, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, chainTemplateA)
	must(err)
	pkA, vkA, err := groth16.Setup(chainCcsA)
	must(err)
	fmt.Printf("  chainA(verifies genesis) constraints=%d\n", chainCcsA.GetNbConstraints())

	fmt.Println("[setup] Chain circuit B（chainA の証明を再帰検証する回路）")
	chainTemplateB := &ChainCircuit{
		PrevVK:    recursion.PlaceholderVerifyingKey[sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl](chainCcsA),
		PrevProof: recursion.PlaceholderProof[sw_bn254.G1Affine, sw_bn254.G2Affine](chainCcsA),
		PrevWit:   recursion.PlaceholderWitness[sw_bn254.ScalarField](chainCcsA),
	}
	chainCcsB, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, chainTemplateB)
	must(err)
	pkB, vkB, err := groth16.Setup(chainCcsB)
	must(err)
	fmt.Printf("  chainB(verifies chainA) constraints=%d\n", chainCcsB.GetNbConstraints())

	// ── 正常系: 3 ステップ連結（RSSI整合を回路内で計算） ──────────────
	fmt.Println("\n[step1] genesis: 整合な観測(申告位置と自位置の幾何距離≈341cm, measured=341cm) → ok=1, z_1=(consistent=1, suspicious=0, step=1)")
	proof1, pub1, err := proveGenesis(genesisCcs, pkG, obsConsistent, 1)
	must(err)
	must(groth16.Verify(proof1, vkG, pub1))
	fmt.Println("  π_1 単体検証: OK（RSSI整合は回路内で計算・確認済）")

	fmt.Println("[step2] π_1 を再帰検証(内包) + 整合な観測 → ok=1, z_2=(consistent=2, suspicious=0, step=2)")
	asg2, err := chainAssignment(vkG, proof1, pub1, droneID, timeBucket, 2, 0, 2, obsConsistent)
	must(err)
	proof2, pub2, err := proveChain(chainCcsA, pkA, asg2)
	must(err)
	must(groth16.Verify(proof2, vkA, pub2, chainVerifierOpts()...))
	fmt.Println("  π_2 単体検証: OK")

	fmt.Println("[step3] π_2 を再帰検証(内包) + なりすまし観測(measured=5000cmだが幾何距離は≈341cm) → ok=0, z_3=(consistent=2, suspicious=1, step=3)")
	asg3, err := chainAssignment(vkA, proof2, pub2, droneID, timeBucket, 2, 1, 3, obsSpoofed)
	must(err)
	proof3, pub3, err := proveChain(chainCcsB, pkB, asg3)
	must(err)
	must(groth16.Verify(proof3, vkB, pub3, chainVerifierOpts()...))
	fmt.Println("  π_3 単体検証: OK（矛盾した観測でも証明は成立し、suspicious_countとして正しく計上される）")

	fmt.Println("\n[OK] 3ステップ連結成功。consistent_count = 1 → 2 → 2、suspicious_count = 0 → 0 → 1 と正しく育った。")
	fmt.Println("     各 π_k は単体で検証できる（チェーンから取ってきて verify、方式Aの肝）。")
	fmt.Println("     RSSI整合はStep入力ではなく回路内で計算される（方式Bの核）。")

	// ── 否定系1: time_bucket を食い違わせる ────────────────────
	fmt.Println("\n[negative 1] time_bucket を食い違わせて π_2' を作ろうとする")
	badTimeBucket, err := chainAssignment(vkG, proof1, pub1, droneID, timeBucket+1, 2, 0, 2, obsConsistent)
	must(err)
	if _, _, err := proveChain(chainCcsA, pkA, badTimeBucket); err != nil {
		fmt.Println("  → 期待通り Prove が失敗（拒否）:", err)
	} else {
		panic("negative test 1 failed: 食い違う time_bucket で証明が成立してしまった")
	}

	// ── 否定系2: 偽の π_{i-1}（proof は本物だが主張する公開値z_{i-1}を改ざん）─
	fmt.Println("[negative 2] 偽の z_1 主張（π_1は本物のまま consistent_count だけ改ざん）で π_2' を作ろうとする")
	forgedGenesisClaim := &GenesisCircuit{
		DroneID: droneID, TimeBucket: timeBucket, ConsistentCount: 99, SuspiciousCount: 0, StepCount: 1,
		// Public()の抽出にしか使わないが、frontend.Variableはinterfaceなので未設定だとnilのまま
		// NewWitnessがpanicする。値そのものは使われないので0で埋める。
		DroneLat: 0, DroneLon: 0, DroneAlt: 0, TargetLat: 0, TargetLon: 0, TargetAlt: 0, MeasuredRangeCm: 0,
	}
	forgedW, err := frontend.NewWitness(forgedGenesisClaim, ecc.BN254.ScalarField())
	must(err)
	forgedPub, err := forgedW.Public()
	must(err)
	badWit, err := chainAssignment(vkG, proof1 /* 本物のπ1 */, forgedPub /* 改ざんした主張 */, droneID, timeBucket, 100, 0, 2, obsConsistent)
	must(err)
	if _, _, err := proveChain(chainCcsA, pkA, badWit); err != nil {
		fmt.Println("  → 期待通り Prove が失敗（拒否）:", err)
	} else {
		panic("negative test 2 failed: 偽の公開値主張で証明が成立してしまった")
	}

	// ── 否定系3(Step B新規): 実際は矛盾したRSSI観測なのに consistent と偽って計上しようとする ─
	fmt.Println("[negative 3] なりすまし観測(obsSpoofed, 本当はok=0)なのに ok=1 として consistent_count に計上しようとする")
	fakeConsistent, err := chainAssignment(vkA, proof2, pub2, droneID, timeBucket, 3 /* 本当は+0のはずが+1を主張 */, 0, 3, obsSpoofed)
	must(err)
	if _, _, err := proveChain(chainCcsB, pkB, fakeConsistent); err != nil {
		fmt.Println("  → 期待通り Prove が失敗（拒否）: 回路が自分でRSSI整合を計算するため、参加者は結果を偽れない")
	} else {
		panic("negative test 3 failed: 矛盾した観測を consistent と偽って計上できてしまった")
	}

	fmt.Println("\n[DONE] Step A/B PoC 成功: 前の証明を内包する逐次チェーンが3ステップ連結でき、")
	fmt.Println("       RSSI整合は回路内で計算され、食い違い/偽の前証明/偽の整合主張は正しく拒否される。")
}
