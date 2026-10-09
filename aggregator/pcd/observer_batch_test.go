package pcd

import (
	"encoding/json"
	"math/big"
	"os"
	"path/filepath"
	"strconv"
	"testing"

	"uav/aggregator/membership"
	"uav/aggregator/nullifier"
	"uav/aggregator/snarkimport"
)

func loadObserverFixtureBatch(t *testing.T) (observations []LeafObservation, roster []DeviceCredential, expectedRoot *big.Int) {
	t.Helper()
	root := filepath.Join("..", "..")
	var manifest struct {
		Version    int    `json:"version"`
		Status     string `json:"status"`
		MemberRoot string `json:"memberRoot"`
		Members    []struct {
			PublicKeyX string `json:"publicKeyX"`
			PublicKeyY string `json:"publicKeyY"`
		} `json:"members"`
	}
	manifestPath := filepath.Join(root, "aggregator", "pcd", "testdata", "observer-roster-v1.json")
	manifestJSON, err := os.ReadFile(manifestPath)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(manifestJSON, &manifest); err != nil {
		t.Fatal(err)
	}
	if manifest.Version != 1 || manifest.Status == "" {
		t.Fatalf("invalid observer roster manifest metadata: version=%d status=%q", manifest.Version, manifest.Status)
	}
	expectedRoot, ok := new(big.Int).SetString(manifest.MemberRoot, 10)
	if !ok {
		t.Fatal("invalid memberRoot in observer roster manifest")
	}
	roster = make([]DeviceCredential, len(manifest.Members))
	for i, member := range manifest.Members {
		roster[i].PublicKeyX, ok = new(big.Int).SetString(member.PublicKeyX, 10)
		if !ok {
			t.Fatalf("invalid publicKeyX for roster member %d", i)
		}
		roster[i].PublicKeyY, ok = new(big.Int).SetString(member.PublicKeyY, 10)
		if !ok {
			t.Fatalf("invalid publicKeyY for roster member %d", i)
		}
	}

	observations = make([]LeafObservation, 3)
	for i := range observations {
		fixture := filepath.Join(root, "contracts", "test", "fixtures")
		proof, err := snarkimport.LoadProof(filepath.Join(fixture, "input_dev"+strconv.Itoa(i)+"_proof.json"))
		if err != nil {
			t.Fatal(err)
		}
		public, err := snarkimport.LoadPublicWitness(filepath.Join(fixture, "input_dev"+strconv.Itoa(i)+"_public.json"))
		if err != nil {
			t.Fatal(err)
		}
		observations[i] = LeafObservation{Proof: proof, Public: public}
	}
	return observations, roster, expectedRoot
}

func TestPrepareObserverBatchFromPinnedCircomProofs(t *testing.T) {
	observations, roster, expectedRoot := loadObserverFixtureBatch(t)
	root := filepath.Join("..", "..")
	vk, err := snarkimport.LoadVK(filepath.Join(root, "rapidsnark_app", "assets", "circuits", "uav_witness", "distance30_witness_attestation_verification_key.json"))
	if err != nil {
		t.Fatal(err)
	}
	batch, err := PrepareObserverBatch(vk, observations, roster, expectedRoot, 2)
	if err != nil {
		t.Fatalf("prepare valid real leaf proofs: %v", err)
	}
	if len(batch.Observers) != 3 {
		t.Fatalf("prepared %d observers, want 3", len(batch.Observers))
	}
	if batch.FinalStatement[6].Cmp(big.NewInt(2)) != 0 || batch.FinalStatement[7].Cmp(big.NewInt(1)) != 0 {
		t.Fatalf("unexpected counts: consistent=%s suspicious=%s", batch.FinalStatement[6], batch.FinalStatement[7])
	}
	if batch.FinalStatement[8].Cmp(big.NewInt(int64(VerdictTrusted))) != 0 {
		t.Fatalf("unexpected final verdict: %s", batch.FinalStatement[8])
	}
	if batch.RootState[stateOldNullifierRoot].Cmp(emptyNullifierRoot()) != 0 {
		t.Fatal("prepared PCD state does not start from the empty nullifier root")
	}
	if batch.RootState[stateNewNullifierRoot].Cmp(batch.FinalStatement[5]) != 0 {
		t.Fatal("PCD root state and final statement disagree on the merged nullifier root")
	}
	if batch.MemberRoot.Sign() == 0 {
		t.Fatal("unexpected zero member root")
	}
	if batch.MemberRoot.Cmp(expectedRoot) != 0 {
		t.Fatalf("computed member root %s does not match pinned fixture root %s", batch.MemberRoot, expectedRoot)
	}

	indices := make(map[int]bool)
	for i, observer := range batch.Observers {
		if indices[observer.MemberIndex] {
			t.Fatalf("observer %d reuses registry index %d", i, observer.MemberIndex)
		}
		indices[observer.MemberIndex] = true
		assignment, err := observer.BridgeAssignment()
		if err != nil {
			t.Fatalf("observer %d BridgeBW assignment: %v", i, err)
		}
		if assignment.DroneID.(*big.Int).Cmp(batch.FinalStatement[1]) != 0 {
			t.Fatalf("observer %d BridgeBW state uses a different drone ID", i)
		}
		occupied := 0
		for _, leaf := range observer.NullifierLeaves {
			if leaf != nil && leaf.Sign() != 0 {
				occupied++
			}
		}
		if occupied != 1 {
			t.Fatalf("observer %d has %d occupied nullifier slots, want 1", i, occupied)
		}
		signals, err := bn254PublicSignals(observer.Public)
		if err != nil {
			t.Fatal(err)
		}
		deviceLeaf := membership.MimcHash(signals[11], signals[12])
		memberPathRoot := applyNativeBridgePath(deviceLeaf, observer.Path.MemberSiblings, observer.Path.PathBits)
		if memberPathRoot.Cmp(batch.MemberRoot) != 0 {
			t.Fatalf("observer %d membership path does not open the registered root", i)
		}
		oldPathRoot := applyNativeBridgePath(new(big.Int), observer.Path.NullifierSiblings, observer.Path.PathBits)
		if oldPathRoot.Cmp(batch.EmptyNullRoot) != 0 {
			t.Fatalf("observer %d nullifier path does not open the empty root", i)
		}
		session := nullifier.SessionCommitment(big.NewInt(1), batch.FinalStatement[1], batch.FinalStatement[2], batch.FinalStatement[3])
		spent := nullifier.Nullifier(deviceLeaf, session)
		newPathRoot := applyNativeBridgePath(spent, observer.Path.NullifierSiblings, observer.Path.PathBits)
		if newPathRoot.Cmp(observer.State[stateNewNullifierRoot]) != 0 {
			t.Fatalf("observer %d nullifier path does not open its single-observer root", i)
		}
	}

	state01, leaves01, err := MergeObserverStates(
		batch.Observers[0].State, batch.Observers[1].State,
		batch.Observers[0].NullifierLeaves, batch.Observers[1].NullifierLeaves,
	)
	if err != nil {
		t.Fatalf("merge first two real observer states: %v", err)
	}
	state012, leaves012, err := MergeObserverStates(
		state01, batch.Observers[2].State, leaves01, batch.Observers[2].NullifierLeaves,
	)
	if err != nil {
		t.Fatalf("merge third real observer state: %v", err)
	}
	for i := range state012 {
		if state012[i].Cmp(batch.RootState[i]) != 0 {
			t.Fatalf("binary merge state[%d]=%s, prepared batch state=%s", i, state012[i], batch.RootState[i])
		}
	}
	if nullifierRootFromLeaves(leaves012).Cmp(batch.FinalStatement[5]) != 0 {
		t.Fatal("binary merge nullifier union does not match final statement")
	}
	if _, _, err := MergeObserverStates(
		batch.Observers[0].State, batch.Observers[0].State,
		batch.Observers[0].NullifierLeaves, batch.Observers[0].NullifierLeaves,
	); err == nil {
		t.Fatal("binary merge accepted a duplicate observer")
	}
	mixedSession := cloneState(batch.Observers[1].State)
	mixedSession[stateBucket].Add(mixedSession[stateBucket], big.NewInt(1))
	if _, _, err := MergeObserverStates(
		batch.Observers[0].State, mixedSession,
		batch.Observers[0].NullifierLeaves, batch.Observers[1].NullifierLeaves,
	); err == nil {
		t.Fatal("binary merge accepted a different time bucket")
	}
}

func TestPrepareObserverBatchRejectsDuplicateAndUnregisteredObservers(t *testing.T) {
	observations, roster, expectedRoot := loadObserverFixtureBatch(t)
	root := filepath.Join("..", "..")
	vk, err := snarkimport.LoadVK(filepath.Join(root, "rapidsnark_app", "assets", "circuits", "uav_witness", "distance30_witness_attestation_verification_key.json"))
	if err != nil {
		t.Fatal(err)
	}

	duplicate := []LeafObservation{observations[0], observations[0]}
	if _, err := PrepareObserverBatch(vk, duplicate, roster, expectedRoot, 2); err == nil {
		t.Fatal("duplicate registered observer unexpectedly accepted")
	}
	unregisteredRoster := []DeviceCredential{
		roster[0], roster[1],
		{PublicKeyX: new(big.Int).Add(roster[0].PublicKeyX, big.NewInt(1)), PublicKeyY: new(big.Int).Set(roster[0].PublicKeyY)},
	}
	registeredLeaves := make([]*big.Int, len(unregisteredRoster))
	for i, credential := range unregisteredRoster {
		registeredLeaves[i] = membership.MimcHash(credential.PublicKeyX, credential.PublicKeyY)
	}
	unregisteredRoot, _, _ := membership.BuildTree(registeredLeaves)
	if _, err := PrepareObserverBatch(vk, observations, unregisteredRoster, unregisteredRoot, 2); err == nil {
		t.Fatal("valid proof from a key absent from the active roster unexpectedly accepted")
	}
	if _, err := PrepareObserverBatch(vk, observations, roster, new(big.Int).Add(expectedRoot, big.NewInt(1)), 2); err == nil {
		t.Fatal("roster with a root different from the active registry root unexpectedly accepted")
	}
}

func TestUnionNullifierLeavesRejectsOverlap(t *testing.T) {
	var left, right NullifierLeaves
	left[5] = big.NewInt(17)
	merged, err := UnionNullifierLeaves(left, right)
	if err != nil || merged[5].Cmp(big.NewInt(17)) != 0 {
		t.Fatalf("disjoint nullifier union failed: merged=%v err=%v", merged[5], err)
	}
	right[5] = big.NewInt(19)
	if _, err := UnionNullifierLeaves(left, right); err == nil {
		t.Fatal("overlapping observer nullifier sets unexpectedly merged")
	}
}

func applyNativeBridgePath(leaf *big.Int, siblings [membership.Depth]*big.Int, bits [membership.Depth]int) *big.Int {
	current := new(big.Int).Set(leaf)
	for d := 0; d < membership.Depth; d++ {
		if bits[d] == 0 {
			current = membership.MimcHash(current, siblings[d])
		} else {
			current = membership.MimcHash(siblings[d], current)
		}
	}
	return current
}

func cloneState(state [stateWidth]*big.Int) [stateWidth]*big.Int {
	var clone [stateWidth]*big.Int
	for i, value := range state {
		clone[i] = new(big.Int).Set(value)
	}
	return clone
}
