package pcd

import (
	"fmt"
	"math/big"

	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"

	"uav/aggregator/membership"
	"uav/aggregator/nullifier"
)

// LeafObservation is one Circom/BN254 proof and its public signals. The proof
// is verified against the caller-pinned leaf VK before it is used to construct
// any recursive state.
type LeafObservation struct {
	Proof  groth16.Proof
	Public witness.Witness
}

// DeviceCredential is an entry in the externally governed observer registry.
// The roster, not the submitted batch, is the authority for membership.
type DeviceCredential struct {
	PublicKeyX *big.Int
	PublicKeyY *big.Int
}

// PreparedObserver contains the private inputs for one BridgeBW leaf. Its
// state and Merkle paths are derived from a verified leaf and the trusted
// registry roster; they are not accepted as caller-claimed leaf outcomes.
type PreparedObserver struct {
	Proof           groth16.Proof
	Public          witness.Witness
	State           [stateWidth]*big.Int
	Path            BridgePathWitness
	NullifierLeaves NullifierLeaves
	MemberIndex     int
}

func (o PreparedObserver) BridgeAssignment() (*BridgeBW, error) {
	return BridgeBWAssignment(o.Proof, o.Public, o.State, o.Path)
}

// PreparedObserverBatch is the deterministic host-side input to the finite
// three-or-more-observer PCD tree. RootState is the nine-value internal PCD
// statement; FinalStatement has the nine public final-attestation-v1 inputs.
type PreparedObserverBatch struct {
	Observers       []PreparedObserver
	MemberRoot      *big.Int
	EmptyNullRoot   *big.Int
	MergedNullRoot  *big.Int
	MinimumQuorum   uint32
	RootState       [stateWidth]*big.Int
	FinalStatement  [publicInputCountV1]*big.Int
	NullifierLeaves NullifierLeaves
}

// UnionNullifierLeaves prepares the private leaf vector for a binary PCD
// merge. It rejects overlapping registered indices before constructing the
// witness; the merge circuit independently enforces the same invariant.
func UnionNullifierLeaves(left, right NullifierLeaves) (NullifierLeaves, error) {
	var merged NullifierLeaves
	for i := range merged {
		leftValue, rightValue := left[i], right[i]
		if leftValue == nil {
			leftValue = new(big.Int)
		}
		if rightValue == nil {
			rightValue = new(big.Int)
		}
		if !canonicalBN254(leftValue) || !canonicalBN254(rightValue) {
			return merged, fmt.Errorf("nullifier leaf %d is not a canonical BN254 scalar", i)
		}
		if leftValue.Sign() != 0 && rightValue.Sign() != 0 {
			return merged, fmt.Errorf("duplicate observer nullifier at registry index %d", i)
		}
		if leftValue.Sign() != 0 {
			merged[i] = new(big.Int).Set(leftValue)
		} else if rightValue.Sign() != 0 {
			merged[i] = new(big.Int).Set(rightValue)
		}
	}
	return merged, nil
}

// MergeObserverStates computes the off-circuit statement for one binary PCD
// node. It mirrors the circuit's session equality, child-root openings,
// disjoint nullifier union, and count-to-occupied-slot checks. The circuit
// remains authoritative; this function only builds and rejects malformed
// witnesses before an expensive recursive prove. It supports matching V1 or
// V2 protocol versions; callers must compile version-pinned NodeBW/NodeBLS
// circuits for the same protocol version before proving a recursive merge.
func MergeObserverStates(
	leftState, rightState [stateWidth]*big.Int,
	leftLeaves, rightLeaves NullifierLeaves,
) ([stateWidth]*big.Int, NullifierLeaves, error) {
	var out [stateWidth]*big.Int
	for _, child := range []struct {
		label string
		state [stateWidth]*big.Int
	}{{label: "left", state: leftState}, {label: "right", state: rightState}} {
		for i, value := range child.state {
			if !canonicalBN254(value) {
				return out, NullifierLeaves{}, fmt.Errorf("%s state[%d] is not a canonical BN254 scalar", child.label, i)
			}
		}
		version := child.state[stateVersion]
		if (version.Cmp(big.NewInt(1)) != 0 && version.Cmp(big.NewInt(FinalPolicyV2Version)) != 0) || child.state[stateBucket].BitLen() > 64 ||
			child.state[stateConsistent].BitLen() > 32 || child.state[stateSuspicious].BitLen() > 32 {
			return out, NullifierLeaves{}, fmt.Errorf("%s state has an unsupported version, bucket, or count range", child.label)
		}
	}
	for i := 0; i <= stateMemberRoot; i++ {
		if leftState[i].Cmp(rightState[i]) != 0 {
			return out, NullifierLeaves{}, fmt.Errorf("child states disagree at session field %d", i)
		}
	}
	if leftState[stateOldNullifierRoot].Cmp(rightState[stateOldNullifierRoot]) != 0 {
		return out, NullifierLeaves{}, fmt.Errorf("child states have different initial nullifier roots")
	}
	leftCount, err := nullifierLeafCount(leftLeaves)
	if err != nil {
		return out, NullifierLeaves{}, fmt.Errorf("left nullifier set: %w", err)
	}
	rightCount, err := nullifierLeafCount(rightLeaves)
	if err != nil {
		return out, NullifierLeaves{}, fmt.Errorf("right nullifier set: %w", err)
	}
	if nullifierRootFromLeaves(leftLeaves).Cmp(leftState[stateNewNullifierRoot]) != 0 {
		return out, NullifierLeaves{}, fmt.Errorf("left nullifier leaves do not open the child state root")
	}
	if nullifierRootFromLeaves(rightLeaves).Cmp(rightState[stateNewNullifierRoot]) != 0 {
		return out, NullifierLeaves{}, fmt.Errorf("right nullifier leaves do not open the child state root")
	}
	if new(big.Int).Add(leftState[stateConsistent], leftState[stateSuspicious]).Cmp(new(big.Int).SetUint64(uint64(leftCount))) != 0 {
		return out, NullifierLeaves{}, fmt.Errorf("left state counts do not match occupied nullifier slots")
	}
	if new(big.Int).Add(rightState[stateConsistent], rightState[stateSuspicious]).Cmp(new(big.Int).SetUint64(uint64(rightCount))) != 0 {
		return out, NullifierLeaves{}, fmt.Errorf("right state counts do not match occupied nullifier slots")
	}
	merged, err := UnionNullifierLeaves(leftLeaves, rightLeaves)
	if err != nil {
		return out, NullifierLeaves{}, err
	}
	mergedCount, err := nullifierLeafCount(merged)
	if err != nil {
		return out, NullifierLeaves{}, err
	}
	consistent := new(big.Int).Add(leftState[stateConsistent], rightState[stateConsistent])
	suspicious := new(big.Int).Add(leftState[stateSuspicious], rightState[stateSuspicious])
	if new(big.Int).Add(consistent, suspicious).Cmp(new(big.Int).SetUint64(uint64(mergedCount))) != 0 {
		return out, NullifierLeaves{}, fmt.Errorf("merged state counts do not match occupied nullifier slots")
	}
	for i := 0; i <= stateMemberRoot; i++ {
		out[i] = new(big.Int).Set(leftState[i])
	}
	out[stateOldNullifierRoot] = new(big.Int).Set(leftState[stateOldNullifierRoot])
	out[stateNewNullifierRoot] = nullifierRootFromLeaves(merged)
	out[stateConsistent] = consistent
	out[stateSuspicious] = suspicious
	return out, merged, nil
}

func nullifierRootFromLeaves(leaves NullifierLeaves) *big.Int {
	values := make([]*big.Int, nullifier.TreeSize)
	for i, leaf := range leaves {
		if leaf == nil {
			values[i] = new(big.Int)
		} else {
			values[i] = new(big.Int).Set(leaf)
		}
	}
	root, _, _ := membership.BuildTree(values)
	return root
}

func nullifierLeafCount(leaves NullifierLeaves) (uint32, error) {
	var count uint32
	for i, leaf := range leaves {
		if leaf == nil {
			continue
		}
		if !canonicalBN254(leaf) {
			return 0, fmt.Errorf("leaf %d is not a canonical BN254 scalar", i)
		}
		if leaf.Sign() != 0 {
			count++
		}
	}
	return count, nil
}

// PrepareObserverBatch verifies each checked-in/native Circom leaf proof,
// resolves each key against a separately supplied registration roster, and
// derives all BridgeBW paths and aggregate public state. The separately
// supplied activeMemberRoot must come from the registry contract; the function
// rejects a roster whose computed root differs from that trust anchor.
func PrepareObserverBatch(
	leafVK groth16.VerifyingKey,
	observations []LeafObservation,
	registered []DeviceCredential,
	activeMemberRoot *big.Int,
	minimumQuorum uint32,
) (*PreparedObserverBatch, error) {
	if !canonicalBN254(activeMemberRoot) {
		return nil, fmt.Errorf("active member root must be a canonical BN254 scalar")
	}
	if leafVK == nil || leafVK.NbPublicWitness() != leafPublicSignalCount {
		got := 0
		if leafVK != nil {
			got = leafVK.NbPublicWitness()
		}
		return nil, fmt.Errorf("observer batch requires a pinned leaf VK with %d public signals, got %d", leafPublicSignalCount, got)
	}
	if len(observations) < 2 {
		return nil, fmt.Errorf("observer batch requires at least two independent observations")
	}
	if len(observations) > nullifier.TreeSize {
		return nil, fmt.Errorf("observer batch has %d observations; registry capacity is %d", len(observations), nullifier.TreeSize)
	}
	if len(registered) == 0 || len(registered) > nullifier.TreeSize {
		return nil, fmt.Errorf("registered roster size must be between 1 and %d", nullifier.TreeSize)
	}
	if minimumQuorum == 0 {
		return nil, fmt.Errorf("minimum quorum must be greater than zero")
	}
	policyCommitment, err := FinalPolicyCommitment(minimumQuorum)
	if err != nil {
		return nil, err
	}

	registeredIndex := make(map[string]int, len(registered))
	memberLeaves := make([]*big.Int, len(registered))
	for i, credential := range registered {
		if !canonicalBN254(credential.PublicKeyX) || !canonicalBN254(credential.PublicKeyY) {
			return nil, fmt.Errorf("registered observer %d has a noncanonical BN254 public key", i)
		}
		key := deviceKey(credential.PublicKeyX, credential.PublicKeyY)
		if _, exists := registeredIndex[key]; exists {
			return nil, fmt.Errorf("registered observer public key is duplicated")
		}
		registeredIndex[key] = i
		memberLeaves[i] = membership.MimcHash(credential.PublicKeyX, credential.PublicKeyY)
	}
	memberRoot, memberSiblings, memberBits := membership.BuildTree(memberLeaves)
	if memberRoot.Cmp(activeMemberRoot) != 0 {
		return nil, fmt.Errorf("registered roster root does not match the active member root")
	}
	zeroLeaves := make([]*big.Int, nullifier.TreeSize)
	for i := range zeroLeaves {
		zeroLeaves[i] = new(big.Int)
	}
	emptyNullRoot, emptyNullSiblings, emptyNullBits := membership.BuildTree(zeroLeaves)

	prepared := &PreparedObserverBatch{
		Observers:     make([]PreparedObserver, len(observations)),
		MemberRoot:    new(big.Int).Set(memberRoot),
		EmptyNullRoot: new(big.Int).Set(emptyNullRoot),
		MinimumQuorum: minimumQuorum,
	}
	seenIndices := make(map[int]struct{}, len(observations))
	var droneID, timeBucket *big.Int
	consistentCount, suspiciousCount := uint32(0), uint32(0)
	for i, observation := range observations {
		if observation.Proof == nil || observation.Public == nil {
			return nil, fmt.Errorf("observation %d is missing its proof or public witness", i)
		}
		public, err := observation.Public.Public()
		if err != nil {
			return nil, fmt.Errorf("observation %d public witness: %w", i, err)
		}
		signals, err := bn254PublicSignals(public)
		if err != nil {
			return nil, fmt.Errorf("observation %d: %w", i, err)
		}
		if err := groth16.Verify(observation.Proof, leafVK, public); err != nil {
			return nil, fmt.Errorf("observation %d leaf proof verification failed: %w", i, err)
		}
		if !isOne(signals[leafWithin30AndDetected]) {
			return nil, fmt.Errorf("observation %d does not satisfy within30_and_detected", i)
		}
		if !isOne(signals[leafDroneAuthOK]) {
			return nil, fmt.Errorf("observation %d does not satisfy drone_auth_ok", i)
		}
		if !isZero(signals[leafConsistencyOK]) && !isOne(signals[leafConsistencyOK]) {
			return nil, fmt.Errorf("observation %d consistency_ok is not boolean", i)
		}
		if i == 0 {
			droneID = new(big.Int).Set(signals[leafDroneID])
			timeBucket = new(big.Int).Set(signals[leafTimeBucket])
		} else if signals[leafDroneID].Cmp(droneID) != 0 || signals[leafTimeBucket].Cmp(timeBucket) != 0 {
			return nil, fmt.Errorf("observation %d belongs to a different drone or time bucket", i)
		}
		if signals[leafTimeBucket].BitLen() > 64 {
			return nil, fmt.Errorf("observation %d time bucket exceeds uint64", i)
		}

		pubX, pubY := signals[11], signals[12]
		memberIndex, ok := registeredIndex[deviceKey(pubX, pubY)]
		if !ok {
			return nil, fmt.Errorf("observation %d device is not in the registered roster", i)
		}
		if _, duplicate := seenIndices[memberIndex]; duplicate {
			return nil, fmt.Errorf("observer registry index %d is used more than once", memberIndex)
		}
		seenIndices[memberIndex] = struct{}{}

		deviceLeaf := memberLeaves[memberIndex]
		session := nullifier.SessionCommitment(
			big.NewInt(1), droneID, timeBucket, policyCommitment,
		)
		spent := nullifier.Nullifier(deviceLeaf, session)
		if spent.Sign() == 0 {
			return nil, fmt.Errorf("observer %d produced a zero session nullifier", i)
		}
		nullifierLeaves := make([]*big.Int, nullifier.TreeSize)
		for j := range nullifierLeaves {
			nullifierLeaves[j] = new(big.Int)
		}
		nullifierLeaves[memberIndex] = new(big.Int).Set(spent)
		newNullRoot, _, _ := membership.BuildTree(nullifierLeaves)

		var state [stateWidth]*big.Int
		state[stateVersion] = big.NewInt(1)
		state[stateDrone] = new(big.Int).Set(droneID)
		state[stateBucket] = new(big.Int).Set(timeBucket)
		state[statePolicy] = new(big.Int).Set(policyCommitment)
		state[stateMemberRoot] = new(big.Int).Set(memberRoot)
		state[stateOldNullifierRoot] = new(big.Int).Set(emptyNullRoot)
		state[stateNewNullifierRoot] = new(big.Int).Set(newNullRoot)
		if isOne(signals[leafConsistencyOK]) {
			state[stateConsistent] = big.NewInt(1)
			state[stateSuspicious] = new(big.Int)
			consistentCount++
		} else {
			state[stateConsistent] = new(big.Int)
			state[stateSuspicious] = big.NewInt(1)
			suspiciousCount++
		}

		path := BridgePathWitness{}
		for d := 0; d < membership.Depth; d++ {
			path.MemberSiblings[d] = new(big.Int).Set(memberSiblings[memberIndex][d])
			path.NullifierSiblings[d] = new(big.Int).Set(emptyNullSiblings[memberIndex][d])
			if memberBits[memberIndex][d] != emptyNullBits[memberIndex][d] {
				return nil, fmt.Errorf("membership/nullifier path index mismatch at depth %d", d)
			}
			path.PathBits[d] = memberBits[memberIndex][d]
		}
		var privateLeaves NullifierLeaves
		privateLeaves[memberIndex] = new(big.Int).Set(spent)
		prepared.Observers[i] = PreparedObserver{
			Proof: observation.Proof, Public: public, State: state,
			Path: path, NullifierLeaves: privateLeaves, MemberIndex: memberIndex,
		}
	}

	allLeaves := make([]*big.Int, nullifier.TreeSize)
	for i := range allLeaves {
		allLeaves[i] = new(big.Int)
	}
	for _, observer := range prepared.Observers {
		for i, leaf := range observer.NullifierLeaves {
			if leaf == nil || leaf.Sign() == 0 {
				continue
			}
			if allLeaves[i].Sign() != 0 {
				return nil, fmt.Errorf("duplicate observer slot %d in prepared nullifier union", i)
			}
			allLeaves[i] = new(big.Int).Set(leaf)
			prepared.NullifierLeaves[i] = new(big.Int).Set(leaf)
		}
	}
	mergedNullRoot, _, _ := membership.BuildTree(allLeaves)
	prepared.MergedNullRoot = new(big.Int).Set(mergedNullRoot)
	verdict, err := DeriveFinalVerdict(consistentCount, suspiciousCount, minimumQuorum)
	if err != nil {
		return nil, err
	}
	prepared.RootState = [stateWidth]*big.Int{
		big.NewInt(1), new(big.Int).Set(droneID), new(big.Int).Set(timeBucket),
		new(big.Int).Set(policyCommitment), new(big.Int).Set(memberRoot),
		new(big.Int).Set(emptyNullRoot), new(big.Int).Set(mergedNullRoot),
		new(big.Int).SetUint64(uint64(consistentCount)), new(big.Int).SetUint64(uint64(suspiciousCount)),
	}
	prepared.FinalStatement = [publicInputCountV1]*big.Int{
		big.NewInt(1), new(big.Int).Set(droneID), new(big.Int).Set(timeBucket),
		new(big.Int).Set(policyCommitment), new(big.Int).Set(memberRoot),
		new(big.Int).Set(mergedNullRoot), new(big.Int).SetUint64(uint64(consistentCount)),
		new(big.Int).SetUint64(uint64(suspiciousCount)), new(big.Int).SetUint64(uint64(verdict)),
	}
	return prepared, nil
}

func bn254PublicSignals(public witness.Witness) ([]*big.Int, error) {
	if public == nil {
		return nil, fmt.Errorf("public witness is nil")
	}
	values, ok := public.Vector().(fr.Vector)
	if !ok {
		return nil, fmt.Errorf("public witness is not a BN254 scalar vector")
	}
	if len(values) != leafPublicSignalCount {
		return nil, fmt.Errorf("leaf public witness has %d signals, expected %d", len(values), leafPublicSignalCount)
	}
	signals := make([]*big.Int, len(values))
	for i := range values {
		signals[i] = new(big.Int)
		values[i].BigInt(signals[i])
	}
	return signals, nil
}

func canonicalBN254(value *big.Int) bool {
	return value != nil && value.Sign() >= 0 && value.Cmp(bn254ScalarModulus) < 0
}

func deviceKey(x, y *big.Int) string {
	return x.String() + ":" + y.String()
}

func isZero(value *big.Int) bool { return value.Sign() == 0 }

func isOne(value *big.Int) bool { return value.Cmp(big.NewInt(1)) == 0 }
