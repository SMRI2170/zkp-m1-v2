package pcd

import (
	"math/big"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/test"

	"uav/aggregator/membership"
	"uav/aggregator/nullifier"
	"uav/aggregator/snarkimport"
)

// This slow integration test is driven by scripts/test_v2_observer_batch.sh.
// The generated VK is intentionally disposable and single-contributor; it is
// never a release key and the fixture directory is removed by the script.
func TestV2ObserverBatchProofIntegration(t *testing.T) {
	fixtureDir := os.Getenv("UAV_V2_BATCH_FIXTURE_DIR")
	if fixtureDir == "" {
		t.Skip("run scripts/test_v2_observer_batch.sh for disposable V2 Groth16 integration coverage")
	}

	vk, err := snarkimport.LoadVK(filepath.Join(fixtureDir, "verification_key.json"))
	if err != nil {
		t.Fatal(err)
	}
	load := func(label string, index int) LeafObservation {
		t.Helper()
		prefix := filepath.Join(fixtureDir, label, "dev"+big.NewInt(int64(index)).String())
		proof, err := snarkimport.LoadProof(prefix + "_proof.json")
		if err != nil {
			t.Fatal(err)
		}
		public, err := snarkimport.LoadPublicWitness(prefix + "_public.json")
		if err != nil {
			t.Fatal(err)
		}
		return LeafObservation{Proof: proof, Public: public}
	}
	base := []LeafObservation{load("base", 0), load("base", 1), load("base", 2)}
	profile2 := load("profile2", 2)
	otherRunSameBucket := load("other-run-same-bucket", 2)
	otherSession := load("other-session", 2)
	farMismatch1 := load("far-mismatch", 1)
	farMismatch2 := load("far-mismatch", 2)
	verifiedSignals := func(observation LeafObservation) []*big.Int {
		t.Helper()
		public, err := observation.Public.Public()
		if err != nil {
			t.Fatal(err)
		}
		if err := groth16.Verify(observation.Proof, vk, public); err != nil {
			t.Fatalf("integration variant is not a valid V2 proof: %v", err)
		}
		signals, err := bn254PublicSignalsWithCount(public, leafPublicSignalCountV2)
		if err != nil {
			t.Fatal(err)
		}
		return signals
	}
	baseSignals := verifiedSignals(base[0])
	profile2Signals := verifiedSignals(profile2)
	otherRunSignals := verifiedSignals(otherRunSameBucket)
	otherSessionSignals := verifiedSignals(otherSession)
	farMismatchSignals1 := verifiedSignals(farMismatch1)
	farMismatchSignals2 := verifiedSignals(farMismatch2)
	for i, signals := range [][]*big.Int{farMismatchSignals1, farMismatchSignals2} {
		if !isOne(signals[leafObservationEligibleV2]) || !isZero(signals[leafConsistencyOKV2]) {
			t.Fatalf("far-position mismatch observer %d must be valid and suspicious; signals=%v", i, signals)
		}
	}
	if profile2Signals[leafCalibrationProfileIDV2].Cmp(big.NewInt(2)) != 0 {
		t.Fatalf("alternate profile fixture exposes %s, want 2", profile2Signals[leafCalibrationProfileIDV2])
	}
	if otherRunSignals[leafTimeBucketV2].Cmp(baseSignals[leafTimeBucketV2]) != 0 || otherRunSignals[leafDroneIDV2].Cmp(baseSignals[leafDroneIDV2]) == 0 {
		t.Fatal("same-bucket proof from another run must use a different session-scoped RID commitment")
	}
	if otherSessionSignals[leafDroneIDV2].Cmp(baseSignals[leafDroneIDV2]) == 0 || otherSessionSignals[leafTimeBucketV2].Cmp(baseSignals[leafTimeBucketV2]) == 0 {
		t.Fatal("different-run proof in another bucket must use a different commitment and bucket")
	}
	_, roster, activeRoot := loadObserverFixtureBatch(t)
	allowed1 := []*big.Int{big.NewInt(1)}

	batch, err := VerifyV2ObserverBatch(vk, base, roster, activeRoot, allowed1, 2)
	if err != nil {
		t.Fatalf("verify three valid V2 leaves: %v", err)
	}
	if batch.ObserverCount != 3 || batch.ConsistentCount != 2 || batch.SuspiciousCount != 1 {
		t.Fatalf("unexpected summary counts: %+v", batch)
	}
	if batch.ProvisionalVerdict != VerdictNoInconsistencyObserved || len(batch.AllowedCalibrationProfiles) != 1 || batch.AllowedCalibrationProfiles[0].Cmp(big.NewInt(1)) != 0 {
		t.Fatalf("unexpected provisional verdict/profile set: %+v", batch)
	}
	farMismatchBatch, err := VerifyV2ObserverBatch(
		vk, []LeafObservation{base[0], farMismatch1, farMismatch2}, roster, activeRoot,
		[]*big.Int{big.NewInt(1), big.NewInt(2)}, 2,
	)
	if err != nil {
		t.Fatalf("accept and aggregate valid far-position RSSI mismatches: %v", err)
	}
	if farMismatchBatch.ObserverCount != 3 || farMismatchBatch.ConsistentCount != 1 ||
		farMismatchBatch.SuspiciousCount != 2 || farMismatchBatch.ProvisionalVerdict != VerdictSpoofSuspected {
		t.Fatalf("far-position mismatch reports did not yield the suspicious quorum: %+v", farMismatchBatch)
	}
	farMismatchPrepared, err := PrepareObserverBatchV2(
		vk, []LeafObservation{base[0], farMismatch1, farMismatch2}, roster, activeRoot,
		[]*big.Int{big.NewInt(2), big.NewInt(1)}, 2,
	)
	if err != nil {
		t.Fatalf("prepare recursive assignments for far-position mismatches: %v", err)
	}
	if farMismatchPrepared.FinalStatement[9].Cmp(big.NewInt(int64(VerdictSpoofSuspected))) != 0 {
		t.Fatalf("far-position mismatch final statement has verdict %s", farMismatchPrepared.FinalStatement[9])
	}
	for i := 1; i < len(farMismatchPrepared.Observers); i++ {
		if _, err := farMismatchPrepared.Observers[i].BridgeAssignment(); err != nil {
			t.Fatalf("suspicious observer %d was rejected by BridgeBWV2 assignment: %v", i, err)
		}
	}
	wantProfileRoot, _, err := buildCalibrationProfileSetV2(allowed1)
	if err != nil {
		t.Fatal(err)
	}
	if batch.CalibrationProfileSetRoot.Cmp(wantProfileRoot) != 0 {
		t.Fatalf("V2 profile-set root %s, want %s", batch.CalibrationProfileSetRoot, wantProfileRoot)
	}
	wantPolicy, err := FinalPolicyCommitmentV2(2, wantProfileRoot)
	if err != nil {
		t.Fatal(err)
	}
	if batch.PolicyCommitment.Cmp(wantPolicy) != 0 {
		t.Fatalf("V2 batch policy commitment %s, want %s", batch.PolicyCommitment, wantPolicy)
	}
	prepared, err := PrepareObserverBatchV2(vk, base, roster, activeRoot, allowed1, 2)
	if err != nil {
		t.Fatalf("prepare verified V2 observers for the recursive bridge: %v", err)
	}
	if len(prepared.Observers) != 3 || prepared.RootState[stateVersion].Cmp(big.NewInt(FinalPolicyV2Version)) != 0 ||
		prepared.RootState[stateConsistent].Cmp(big.NewInt(2)) != 0 || prepared.RootState[stateSuspicious].Cmp(big.NewInt(1)) != 0 {
		t.Fatalf("unexpected prepared V2 root state: %+v", prepared.RootState)
	}
	wantFinal := [publicInputCountV2]*big.Int{
		big.NewInt(FinalPolicyV2Version), batch.DroneIDCommitment, batch.TimeBucket,
		batch.PolicyCommitment, batch.CalibrationProfileSetRoot, batch.MemberRoot,
		prepared.MergedNullRoot, big.NewInt(2), big.NewInt(1), big.NewInt(int64(VerdictTrusted)),
	}
	for i := range wantFinal {
		if prepared.FinalStatement[i].Cmp(wantFinal[i]) != 0 {
			t.Fatalf("prepared V2 final public input[%d]=%s, want %s", i, prepared.FinalStatement[i], wantFinal[i])
		}
	}
	seenMembers := make(map[int]bool)
	for i, observer := range prepared.Observers {
		if seenMembers[observer.MemberIndex] {
			t.Fatalf("V2 observer %d reuses member index %d", i, observer.MemberIndex)
		}
		seenMembers[observer.MemberIndex] = true
		assignment, err := observer.BridgeAssignment()
		if err != nil {
			t.Fatalf("V2 observer %d BridgeBWV2 assignment: %v", i, err)
		}
		badEmptyPath := observer.Path
		badEmptyPath.NullifierSiblings[0] = new(big.Int).Add(badEmptyPath.NullifierSiblings[0], big.NewInt(1))
		if _, err := BridgeBWV2Assignment(observer.Proof, observer.Public, observer.State, badEmptyPath, 2); err == nil {
			t.Fatalf("V2 observer %d accepted a nullifier path sibling inconsistent with the empty-tree constant", i)
		}
		badProfilePath := observer.Path
		badProfilePath.ProfileSiblings[0] = new(big.Int).Add(badProfilePath.ProfileSiblings[0], big.NewInt(1))
		if _, err := BridgeBWV2Assignment(observer.Proof, observer.Public, observer.State, badProfilePath, 2); err == nil {
			t.Fatalf("V2 observer %d accepted a calibration profile path that does not open the policy root", i)
		}
		assignedVersion, ok := assignment.ProtocolVersion.(*big.Int)
		if !ok || assignment.MinimumQuorum != uint32(2) || assignedVersion.Cmp(prepared.RootState[stateVersion]) != 0 {
			t.Fatalf("V2 observer %d bridge assignment has the wrong version/quorum", i)
		}
		public, err := observer.Public.Public()
		if err != nil {
			t.Fatal(err)
		}
		signals, err := bn254PublicSignalsWithCount(public, leafPublicSignalCountV2)
		if err != nil {
			t.Fatal(err)
		}
		deviceLeaf := membership.MimcHash(signals[leafObserverPublicKeyXV2], signals[leafObserverPublicKeyYV2])
		memberPathRoot := applyNativeBridgePath(deviceLeaf, observer.Path.MemberSiblings, observer.Path.PathBits)
		if memberPathRoot.Cmp(prepared.MemberRoot) != 0 {
			t.Fatalf("V2 observer %d member path does not open registered root", i)
		}
		oldPathRoot := applyNativeBridgePath(new(big.Int), observer.Path.NullifierSiblings, observer.Path.PathBits)
		if oldPathRoot.Cmp(prepared.EmptyNullRoot) != 0 {
			t.Fatalf("V2 observer %d nullifier path does not open the empty root", i)
		}
		session := nullifier.SessionCommitment(
			big.NewInt(FinalPolicyV2Version), prepared.RootState[stateDrone],
			prepared.RootState[stateBucket], prepared.PolicyCommitment,
		)
		spent := nullifier.Nullifier(deviceLeaf, session)
		newPathRoot := applyNativeBridgePath(spent, observer.Path.NullifierSiblings, observer.Path.PathBits)
		if newPathRoot.Cmp(observer.State[stateNewNullifierRoot]) != 0 {
			t.Fatalf("V2 observer %d nullifier path does not open its leaf state", i)
		}
	}
	mergedV2State := prepared.Observers[0].State
	mergedV2Leaves := prepared.Observers[0].NullifierLeaves
	for i := 1; i < len(prepared.Observers); i++ {
		mergedV2State, mergedV2Leaves, err = MergeObserverStates(
			mergedV2State, prepared.Observers[i].State,
			mergedV2Leaves, prepared.Observers[i].NullifierLeaves,
		)
		if err != nil {
			t.Fatalf("merge V2 observer %d host states: %v", i, err)
		}
	}
	for i := range mergedV2State {
		if mergedV2State[i].Cmp(prepared.RootState[i]) != 0 {
			t.Fatalf("merged V2 state[%d]=%s, prepared root=%s", i, mergedV2State[i], prepared.RootState[i])
		}
	}
	mixedProtocolState := cloneState(prepared.Observers[0].State)
	mixedProtocolState[stateVersion] = big.NewInt(FinalPolicyVersion)
	if _, _, err := MergeObserverStates(
		mixedProtocolState, prepared.Observers[1].State,
		prepared.Observers[0].NullifierLeaves, prepared.Observers[1].NullifierLeaves,
	); err == nil {
		t.Fatal("host merge accepted V1 and V2 observer states in one tree")
	}
	badPolicyState := cloneState(prepared.Observers[0].State)
	badPolicyState[statePolicy].Add(badPolicyState[statePolicy], big.NewInt(1))
	if _, err := BridgeBWV2Assignment(prepared.Observers[0].Proof, prepared.Observers[0].Public, badPolicyState, prepared.Observers[0].Path, 2); err == nil {
		t.Fatal("V2 bridge assignment accepted a state policy not binding quorum/profile")
	}

	duplicate := []LeafObservation{base[0], base[0]}
	if _, err := VerifyV2ObserverBatch(vk, duplicate, roster, activeRoot, allowed1, 2); err == nil || !strings.Contains(err.Error(), "used more than once") {
		t.Fatal("duplicate registered observer was accepted")
	}

	profileMixed := []LeafObservation{base[0], base[1], profile2}
	allowed12 := []*big.Int{big.NewInt(1), big.NewInt(2)}
	mixedBatch, err := VerifyV2ObserverBatch(vk, profileMixed, roster, activeRoot, allowed12, 2)
	if err != nil {
		t.Fatalf("valid leaves with different allowlisted calibration profiles were rejected: %v", err)
	}
	if len(mixedBatch.AllowedCalibrationProfiles) != 2 || mixedBatch.AllowedCalibrationProfiles[0].Cmp(big.NewInt(1)) != 0 || mixedBatch.AllowedCalibrationProfiles[1].Cmp(big.NewInt(2)) != 0 {
		t.Fatalf("mixed-profile batch did not retain canonical allowed profile IDs: %v", mixedBatch.AllowedCalibrationProfiles)
	}
	mixedPrepared, err := PrepareObserverBatchV2(vk, profileMixed, roster, activeRoot, []*big.Int{big.NewInt(2), big.NewInt(1)}, 2)
	if err != nil {
		t.Fatalf("prepare mixed-profile bridge batch independent of allowlist ordering: %v", err)
	}
	if mixedPrepared.CalibrationProfileSetRoot.Cmp(mixedBatch.CalibrationProfileSetRoot) != 0 {
		t.Fatal("profile-set root changes when caller reorders the approved IDs")
	}
	for i, observer := range mixedPrepared.Observers {
		if _, err := observer.BridgeAssignment(); err != nil {
			t.Fatalf("mixed-profile observer %d BridgeBWV2 assignment rejected: %v", i, err)
		}
	}
	if _, err := VerifyV2ObserverBatch(vk, profileMixed, roster, activeRoot, allowed1, 2); err == nil || !strings.Contains(err.Error(), "not allowed by policy") {
		t.Fatal("unallowlisted calibration profile was accepted")
	}

	sessionMixed := []LeafObservation{base[0], base[1], otherRunSameBucket}
	if _, err := VerifyV2ObserverBatch(vk, sessionMixed, roster, activeRoot, allowed1, 2); err == nil || !strings.Contains(err.Error(), "different session-scoped RID commitment or time bucket") {
		t.Fatal("valid leaf from another run in the same time bucket was aggregated")
	}

	sessionMixed = []LeafObservation{base[0], base[1], otherSession}
	if _, err := VerifyV2ObserverBatch(vk, sessionMixed, roster, activeRoot, allowed1, 2); err == nil || !strings.Contains(err.Error(), "different session-scoped RID commitment or time bucket") {
		t.Fatal("valid leaf from another time bucket was aggregated")
	}

	tampered := base[2]
	tampered.Public = replacePublicSignal(t, tampered.Public, leafCalibrationProfileIDV2, big.NewInt(2))
	if _, err := VerifyV2ObserverBatch(vk, []LeafObservation{base[0], base[1], tampered}, roster, activeRoot, []*big.Int{big.NewInt(1), big.NewInt(2)}, 2); err == nil || !strings.Contains(err.Error(), "proof verification failed") {
		t.Fatal("tampered public calibration profile was accepted with the original proof")
	}
	tamperedFreshness := base[2]
	tamperedFreshness.Public = replacePublicSignal(t, tamperedFreshness.Public, leafFreshnessV2, new(big.Int).Add(verifiedSignals(base[2])[leafFreshnessV2], big.NewInt(1)))
	if _, err := VerifyV2ObserverBatch(vk, []LeafObservation{base[0], base[1], tamperedFreshness}, roster, activeRoot, allowed1, 2); err == nil || !strings.Contains(err.Error(), "proof verification failed") {
		t.Fatal("tampered signed freshness timestamp was accepted with the original proof")
	}

	rootV1 := filepath.Join("..", "..", "rapidsnark_app", "assets", "circuits", "uav_witness", "distance30_witness_attestation_verification_key.json")
	v1VK, err := snarkimport.LoadVK(rootV1)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := VerifyV2ObserverBatch(v1VK, base, roster, activeRoot, allowed1, 2); err == nil {
		t.Fatal("V1 verification key was accepted for V2 leaves")
	}
	if _, err := NewBridgeBWV2FromSample(v1VK, base[0].Proof, base[0].Public); err == nil {
		t.Fatal("BridgeBWV2 accepted a V1 verification key")
	}
	if _, err := NewBridgeBWFromSample(vk, base[0].Proof, base[0].Public); err == nil {
		t.Fatal("V1 BridgeBW accepted a V2 verification key/layout")
	}
	if _, err := NewBridgeBWV2FromSample(vk, base[0].Proof, base[0].Public); err != nil {
		t.Fatalf("BridgeBWV2 rejected an actual 8-signal proof shape: %v", err)
	}
	runBridgeSolve := os.Getenv("RUN_BRIDGE_BW6_SOLVE") == "1"
	runBridgeGroth16 := os.Getenv("RUN_BRIDGE_BW6_PROVE") == "1"
	if runBridgeSolve || runBridgeGroth16 {
		// Solve an actual far-position mismatch leaf proof with profile 2. This
		// confirms a suspicious result survives the recursive leaf boundary.
		observer := farMismatchPrepared.Observers[2]
		bridgeTemplate, err := NewBridgeBWV2FromSample(vk, observer.Proof, observer.Public)
		if err != nil {
			t.Fatalf("construct BridgeBWV2 from actual Circom proof: %v", err)
		}
		bridgeAssignment, err := observer.BridgeAssignment()
		if err != nil {
			t.Fatalf("construct actual BridgeBWV2 witness: %v", err)
		}
		if runBridgeSolve {
			if err := test.IsSolved(bridgeTemplate, bridgeAssignment, ecc.BW6_761.ScalarField()); err != nil {
				t.Fatalf("BridgeBWV2 did not verify an actual V2 leaf proof and its derived paths: %v", err)
			}
			badPath := *bridgeAssignment
			pathBit, ok := badPath.PathBits[0].(int)
			if !ok {
				t.Fatalf("unexpected bridge path bit type %T", badPath.PathBits[0])
			}
			badPath.PathBits[0] = 1 - pathBit
			if err := test.IsSolved(bridgeTemplate, &badPath, ecc.BW6_761.ScalarField()); err == nil {
				t.Fatal("BridgeBWV2 accepted a tampered Merkle path bit")
			}
			badProfilePath := *bridgeAssignment
			profilePathBit, ok := badProfilePath.ProfilePathBits[0].(int)
			if !ok {
				t.Fatalf("unexpected BridgeBWV2 profile path bit type %T", badProfilePath.ProfilePathBits[0])
			}
			badProfilePath.ProfilePathBits[0] = 1 - profilePathBit
			if err := test.IsSolved(bridgeTemplate, &badProfilePath, ecc.BW6_761.ScalarField()); err == nil {
				t.Fatal("BridgeBWV2 accepted a tampered calibration-profile membership path")
			}
		}
		if runBridgeGroth16 {
			ccs, err := frontend.Compile(ecc.BW6_761.ScalarField(), r1cs.NewBuilder, bridgeTemplate)
			if err != nil {
				t.Fatalf("compile actual-key BridgeBWV2 R1CS: %v", err)
			}
			pk, outerVK, err := groth16.Setup(ccs)
			if err != nil {
				t.Fatalf("disposable BW6 BridgeBWV2 setup: %v", err)
			}
			outerWitness, err := frontend.NewWitness(bridgeAssignment, ecc.BW6_761.ScalarField())
			if err != nil {
				t.Fatalf("build BW6 BridgeBWV2 witness: %v", err)
			}
			outerProof, err := groth16.Prove(ccs, pk, outerWitness)
			if err != nil {
				t.Fatalf("prove BW6 BridgeBWV2: %v", err)
			}
			outerPublic, err := outerWitness.Public()
			if err != nil {
				t.Fatalf("extract BW6 BridgeBWV2 public witness: %v", err)
			}
			if err := groth16.Verify(outerProof, outerVK, outerPublic); err != nil {
				t.Fatalf("verify BW6 BridgeBWV2 proof: %v", err)
			}
			t.Logf("verified disposable BW6 BridgeBWV2 Groth16 proof (%d constraints)", ccs.GetNbConstraints())
		}
	}
}

func replacePublicSignal(t *testing.T, source witness.Witness, index int, replacement *big.Int) witness.Witness {
	t.Helper()
	values, ok := source.Vector().(fr.Vector)
	if !ok || index < 0 || index >= len(values) {
		t.Fatalf("unexpected public witness vector or index %d", index)
	}
	copyValues := append(fr.Vector(nil), values...)
	copyValues[index].SetBigInt(replacement)
	mutated, err := witness.New(ecc.BN254.ScalarField())
	if err != nil {
		t.Fatal(err)
	}
	channel := make(chan any, len(copyValues))
	for i := range copyValues {
		channel <- copyValues[i]
	}
	close(channel)
	if err := mutated.Fill(len(copyValues), 0, channel); err != nil {
		t.Fatal(err)
	}
	return mutated
}
