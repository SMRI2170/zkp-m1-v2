package pcd

import (
	"fmt"
	"math/big"

	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"

	"uav/aggregator/membership"
	"uav/aggregator/nullifier"
)

// PreparedObserverV2 contains a verified V2 leaf and the host-derived private
// openings expected by BridgeBWV2. The recursive circuit independently checks
// the proof, member path, nullifier path, V2 policy commitment, and counts.
type PreparedObserverV2 struct {
	Proof           groth16.Proof
	Public          witness.Witness
	State           [stateWidth]*big.Int
	Path            BridgePathWitness
	NullifierLeaves NullifierLeaves
	MemberIndex     int
	MinimumQuorum   uint32
}

// PreparedObserverBatchV2 is the deterministic V2 bridge/merge input. Its
// nine-value RootState is internal; FinalStatement is the separate 10-field
// FinalBNV2 public ABI.
type PreparedObserverBatchV2 struct {
	Observers                  []PreparedObserverV2
	MemberRoot                 *big.Int
	EmptyNullRoot              *big.Int
	MergedNullRoot             *big.Int
	CalibrationProfileSetRoot  *big.Int
	AllowedCalibrationProfiles []*big.Int
	PolicyCommitment           *big.Int
	MinimumQuorum              uint32
	RootState                  [stateWidth]*big.Int
	FinalStatement             [publicInputCountV2]*big.Int
	NullifierLeaves            NullifierLeaves
}

// BridgeAssignment constructs one private BridgeBWV2 witness.
func (o PreparedObserverV2) BridgeAssignment() (*BridgeBWV2, error) {
	return BridgeBWV2Assignment(o.Proof, o.Public, o.State, o.Path, o.MinimumQuorum)
}

// PrepareObserverBatchV2 verifies the actual leaf proofs, checks the V2 policy
// and active roster, then derives member/nullifier Merkle paths and one-time
// observer nullifiers for the recursive bridge. It does not generate a
// recursive proof; the returned statements are inputs to that next step.
func PrepareObserverBatchV2(
	leafVK groth16.VerifyingKey,
	observations []LeafObservation,
	registered []DeviceCredential,
	activeMemberRoot *big.Int,
	allowedCalibrationProfileIDs []*big.Int,
	minimumQuorum uint32,
) (*PreparedObserverBatchV2, error) {
	verified, err := VerifyV2ObserverBatch(
		leafVK, observations, registered, activeMemberRoot,
		allowedCalibrationProfileIDs, minimumQuorum,
	)
	if err != nil {
		return nil, err
	}
	registeredIndex := make(map[string]int, len(registered))
	memberLeaves := make([]*big.Int, len(registered))
	for i, credential := range registered {
		registeredIndex[deviceKey(credential.PublicKeyX, credential.PublicKeyY)] = i
		memberLeaves[i] = membership.MimcHash(credential.PublicKeyX, credential.PublicKeyY)
	}
	memberRoot, memberSiblings, memberBits := membership.BuildTree(memberLeaves)
	if memberRoot.Cmp(verified.MemberRoot) != 0 || memberRoot.Cmp(activeMemberRoot) != 0 {
		return nil, fmt.Errorf("V2 prepared roster root changed after proof verification")
	}
	zeroLeaves := make([]*big.Int, nullifier.TreeSize)
	for i := range zeroLeaves {
		zeroLeaves[i] = new(big.Int)
	}
	emptyNullRoot, emptyNullSiblings, emptyNullBits := membership.BuildTree(zeroLeaves)

	prepared := &PreparedObserverBatchV2{
		Observers:                  make([]PreparedObserverV2, len(verified.verifiedLeaves)),
		MemberRoot:                 new(big.Int).Set(memberRoot),
		EmptyNullRoot:              new(big.Int).Set(emptyNullRoot),
		CalibrationProfileSetRoot:  new(big.Int).Set(verified.CalibrationProfileSetRoot),
		AllowedCalibrationProfiles: make([]*big.Int, len(verified.AllowedCalibrationProfiles)),
		PolicyCommitment:           new(big.Int).Set(verified.PolicyCommitment),
		MinimumQuorum:              minimumQuorum,
	}
	for i, profileID := range verified.AllowedCalibrationProfiles {
		prepared.AllowedCalibrationProfiles[i] = new(big.Int).Set(profileID)
	}
	allNullifierLeaves := make([]*big.Int, nullifier.TreeSize)
	for i := range allNullifierLeaves {
		allNullifierLeaves[i] = new(big.Int)
	}
	for i, leaf := range verified.verifiedLeaves {
		memberIndex := leaf.MemberIndex
		if memberIndex < 0 || memberIndex >= len(memberLeaves) || memberIndex >= nullifier.TreeSize {
			return nil, fmt.Errorf("V2 observation %d has an invalid roster index %d", i, memberIndex)
		}
		deviceLeaf := memberLeaves[memberIndex]
		session := nullifier.SessionCommitment(
			big.NewInt(FinalPolicyV2Version), verified.DroneIDCommitment,
			verified.TimeBucket, verified.PolicyCommitment,
		)
		spent := nullifier.Nullifier(deviceLeaf, session)
		if spent.Sign() == 0 {
			return nil, fmt.Errorf("V2 observer %d produced a zero session nullifier", i)
		}
		if allNullifierLeaves[memberIndex].Sign() != 0 {
			return nil, fmt.Errorf("duplicate V2 observer slot %d in prepared nullifier union", memberIndex)
		}
		allNullifierLeaves[memberIndex] = new(big.Int).Set(spent)
		nullifierLeaves := make([]*big.Int, nullifier.TreeSize)
		for j := range nullifierLeaves {
			nullifierLeaves[j] = new(big.Int)
		}
		nullifierLeaves[memberIndex] = new(big.Int).Set(spent)
		newNullRoot, _, _ := membership.BuildTree(nullifierLeaves)

		consistent, suspicious := new(big.Int), new(big.Int)
		if isOne(leaf.Signals[leafConsistencyOKV2]) {
			consistent.SetInt64(1)
		} else {
			suspicious.SetInt64(1)
		}
		state := [stateWidth]*big.Int{
			big.NewInt(FinalPolicyV2Version), new(big.Int).Set(verified.DroneIDCommitment),
			new(big.Int).Set(verified.TimeBucket), new(big.Int).Set(verified.PolicyCommitment),
			new(big.Int).Set(memberRoot), new(big.Int).Set(emptyNullRoot),
			new(big.Int).Set(newNullRoot), consistent, suspicious,
		}
		path := BridgePathWitness{}
		for depth := 0; depth < membership.Depth; depth++ {
			path.MemberSiblings[depth] = new(big.Int).Set(memberSiblings[memberIndex][depth])
			path.NullifierSiblings[depth] = new(big.Int).Set(emptyNullSiblings[memberIndex][depth])
			if memberBits[memberIndex][depth] != emptyNullBits[memberIndex][depth] {
				return nil, fmt.Errorf("V2 membership/nullifier path index mismatch at depth %d", depth)
			}
			path.PathBits[depth] = memberBits[memberIndex][depth]
			path.ProfileSetRoot = new(big.Int).Set(verified.CalibrationProfileSetRoot)
			path.ProfileSiblings[depth] = new(big.Int).Set(leaf.ProfilePath.Siblings[depth])
			path.ProfilePathBits[depth] = leaf.ProfilePath.Bits[depth]
		}
		var privateLeaves NullifierLeaves
		privateLeaves[memberIndex] = new(big.Int).Set(spent)
		prepared.Observers[i] = PreparedObserverV2{
			Proof: leaf.Proof, Public: leaf.Public, State: state, Path: path,
			NullifierLeaves: privateLeaves, MemberIndex: memberIndex,
			MinimumQuorum: minimumQuorum,
		}
	}
	mergedNullRoot, _, _ := membership.BuildTree(allNullifierLeaves)
	prepared.MergedNullRoot = new(big.Int).Set(mergedNullRoot)
	prepared.NullifierLeaves, err = nullifierLeavesFromSlice(allNullifierLeaves)
	if err != nil {
		return nil, err
	}
	prepared.RootState = [stateWidth]*big.Int{
		big.NewInt(FinalPolicyV2Version), new(big.Int).Set(verified.DroneIDCommitment),
		new(big.Int).Set(verified.TimeBucket), new(big.Int).Set(verified.PolicyCommitment),
		new(big.Int).Set(memberRoot), new(big.Int).Set(emptyNullRoot),
		new(big.Int).Set(mergedNullRoot), new(big.Int).SetUint64(uint64(verified.ConsistentCount)),
		new(big.Int).SetUint64(uint64(verified.SuspiciousCount)),
	}
	prepared.FinalStatement = [publicInputCountV2]*big.Int{
		big.NewInt(FinalPolicyV2Version),
		new(big.Int).Set(verified.DroneIDCommitment),
		new(big.Int).Set(verified.TimeBucket),
		new(big.Int).Set(verified.PolicyCommitment),
		new(big.Int).Set(verified.CalibrationProfileSetRoot),
		new(big.Int).Set(verified.MemberRoot),
		new(big.Int).Set(mergedNullRoot),
		new(big.Int).SetUint64(uint64(verified.ConsistentCount)),
		new(big.Int).SetUint64(uint64(verified.SuspiciousCount)),
		new(big.Int).SetUint64(uint64(verified.ProvisionalVerdict)),
	}
	return prepared, nil
}

func nullifierLeavesFromSlice(values []*big.Int) (NullifierLeaves, error) {
	var leaves NullifierLeaves
	if len(values) != len(leaves) {
		return leaves, fmt.Errorf("V2 nullifier slice has %d values, expected %d", len(values), len(leaves))
	}
	for i, value := range values {
		if !canonicalBN254(value) {
			return leaves, fmt.Errorf("V2 nullifier leaf %d is not canonical", i)
		}
		leaves[i] = new(big.Int).Set(value)
	}
	return leaves, nil
}
