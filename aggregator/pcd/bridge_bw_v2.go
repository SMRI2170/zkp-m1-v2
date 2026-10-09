package pcd

import (
	"fmt"
	"math/big"

	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/constraint"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	"github.com/consensys/gnark/std/math/emulated"
	stdgroth16 "github.com/consensys/gnark/std/recursion/groth16"

	"uav/aggregator/membership"
	"uav/aggregator/nullifier"
)

// BridgeBWV2 verifies a pinned 8-signal V2 BN254 leaf proof inside BW6-761,
// proves that the signed calibration profile belongs to the approved profile
// set, binds that set root and quorum into policy, and derives the V2 nullifier.
type BridgeBWV2 struct {
	LeafProof  stdgroth16.Proof[sw_bn254.G1Affine, sw_bn254.G2Affine]
	LeafPublic stdgroth16.Witness[sw_bn254.ScalarField]

	verifyingKey stdgroth16.VerifyingKey[sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl] `gnark:"-"`

	ProtocolVersion  frontend.Variable `gnark:",public"`
	DroneID          frontend.Variable `gnark:",public"`
	TimeBucket       frontend.Variable `gnark:",public"`
	PolicyCommitment frontend.Variable `gnark:",public"`
	MemberRoot       frontend.Variable `gnark:",public"`
	OldNullifierRoot frontend.Variable `gnark:",public"`
	NewNullifierRoot frontend.Variable `gnark:",public"`
	ConsistentCount  frontend.Variable `gnark:",public"`
	SuspiciousCount  frontend.Variable `gnark:",public"`

	MinimumQuorum             frontend.Variable
	CalibrationProfileSetRoot frontend.Variable
	MemberSiblings            [membership.Depth]emulated.Element[sw_bn254.ScalarField]
	ProfileSiblings           [membership.Depth]emulated.Element[sw_bn254.ScalarField]
	PathBits                  [membership.Depth]frontend.Variable
	ProfilePathBits           [membership.Depth]frontend.Variable
}

// NewBridgeBWV2 constructs a bridge template from an 8-signal BN254 leaf
// constraint system and its fixed verification key. It is useful for native
// leaf circuits and circuit-shape tests; the production Circom V2 source uses
// NewBridgeBWV2FromSample because its R1CS is not a gnark ConstraintSystem.
func NewBridgeBWV2(leafCCS constraint.ConstraintSystem, leafVK groth16.VerifyingKey) (*BridgeBWV2, error) {
	if leafCCS == nil || leafCCS.GetNbPublicVariables()-1 != leafPublicSignalCountV2 {
		got := 0
		if leafCCS != nil {
			got = leafCCS.GetNbPublicVariables() - 1
		}
		return nil, fmt.Errorf("BridgeBWV2 requires a leaf circuit with %d public signals, got %d", leafPublicSignalCountV2, got)
	}
	proof := stdgroth16.PlaceholderProof[sw_bn254.G1Affine, sw_bn254.G2Affine](leafCCS)
	public := stdgroth16.PlaceholderWitness[sw_bn254.ScalarField](leafCCS)
	return newBridgeBWV2(leafVK, proof, public)
}

// NewBridgeBWV2FromSample fixes the V2 leaf verification key and obtains the
// recursive proof/public-witness shape from one actual V2 proof. Circom V2 R1CS
// is not a gnark ConstraintSystem, so this sample-based constructor is the
// supported route until a native R1CS importer is added.
func NewBridgeBWV2FromSample(leafVK groth16.VerifyingKey, shapeProof groth16.Proof, shapePublic witness.Witness) (*BridgeBWV2, error) {
	if leafVK == nil || leafVK.NbPublicWitness() != leafPublicSignalCountV2 {
		got := 0
		if leafVK != nil {
			got = leafVK.NbPublicWitness()
		}
		return nil, fmt.Errorf("BridgeBWV2 requires a V2 leaf VK with %d public signals, got %d", leafPublicSignalCountV2, got)
	}
	proof, err := stdgroth16.ValueOfProof[sw_bn254.G1Affine, sw_bn254.G2Affine](shapeProof)
	if err != nil {
		return nil, fmt.Errorf("shape BridgeBWV2 leaf proof: %w", err)
	}
	public, err := stdgroth16.ValueOfWitness[sw_bn254.ScalarField](shapePublic)
	if err != nil {
		return nil, fmt.Errorf("shape BridgeBWV2 leaf public witness: %w", err)
	}
	if len(public.Public) != leafPublicSignalCountV2 {
		return nil, fmt.Errorf("BridgeBWV2 shape witness must have %d public signals, got %d", leafPublicSignalCountV2, len(public.Public))
	}
	return newBridgeBWV2(leafVK, proof, public)
}

func newBridgeBWV2(
	leafVK groth16.VerifyingKey,
	proof stdgroth16.Proof[sw_bn254.G1Affine, sw_bn254.G2Affine],
	public stdgroth16.Witness[sw_bn254.ScalarField],
) (*BridgeBWV2, error) {
	if leafVK == nil || leafVK.NbPublicWitness() != leafPublicSignalCountV2 {
		got := 0
		if leafVK != nil {
			got = leafVK.NbPublicWitness()
		}
		return nil, fmt.Errorf("BridgeBWV2 requires a V2 leaf VK with %d public signals, got %d", leafPublicSignalCountV2, got)
	}
	vk, err := stdgroth16.ValueOfVerifyingKeyFixed[
		sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl,
	](leafVK)
	if err != nil {
		return nil, fmt.Errorf("pin BridgeBWV2 V2 leaf key: %w", err)
	}
	return &BridgeBWV2{
		LeafProof: proof, LeafPublic: public, verifyingKey: vk,
	}, nil
}

func (c *BridgeBWV2) Define(api frontend.API) error {
	verifier, err := stdgroth16.NewVerifier[
		sw_bn254.ScalarField, sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl,
	](api)
	if err != nil {
		return err
	}
	if err := verifier.AssertProof(c.verifyingKey, c.LeafProof, c.LeafPublic); err != nil {
		return err
	}
	if len(c.LeafPublic.Public) != leafPublicSignalCountV2 {
		return fmt.Errorf("BridgeBWV2 leaf must expose %d public signals", leafPublicSignalCountV2)
	}

	f, err := emulated.NewField[sw_bn254.ScalarField](api)
	if err != nil {
		return err
	}
	value := func(i int) *emulated.Element[sw_bn254.ScalarField] {
		return f.ReduceStrict(&c.LeafPublic.Public[i])
	}
	publicValue := func(v *emulated.Element[sw_bn254.ScalarField]) frontend.Variable {
		x := f.ReduceStrict(v)
		acc := frontend.Variable(0)
		coefficient := big.NewInt(1)
		for _, limb := range x.Limbs {
			acc = api.Add(acc, api.Mul(limb, new(big.Int).Set(coefficient)))
			coefficient.Lsh(coefficient, 64)
		}
		return acc
	}

	api.AssertIsEqual(c.ProtocolVersion, FinalPolicyV2Version)
	observationEligible := value(leafObservationEligibleV2)
	f.AssertIsEqual(observationEligible, f.One())
	profile := value(leafCalibrationProfileIDV2)
	profileSetRoot := nativeBWScalarToBN254(api, f, c.CalibrationProfileSetRoot)
	policyFromLeaf := finalPolicyCommitmentV2Emulated(api, f, c.MinimumQuorum, profileSetRoot)
	profileLeaf := mimcBN254(f, f.NewElement(finalPolicyV2ProfileDomain), profile)
	profileRootFromPath := bridgeMerkleRoot(api, f, profileLeaf, c.ProfileSiblings, c.ProfilePathBits)
	f.AssertIsEqual(profileRootFromPath, profileSetRoot)

	droneID := nativeBWScalarToBN254(api, f, c.DroneID)
	timeBucket := nativeBWScalarToBN254(api, f, c.TimeBucket)
	protocolVersion := nativeBWScalarToBN254(api, f, c.ProtocolVersion)
	policyCommitment := nativeBWScalarToBN254(api, f, c.PolicyCommitment)
	memberRootValue := nativeBWScalarToBN254(api, f, c.MemberRoot)
	oldNullifierRoot := nativeBWScalarToBN254(api, f, c.OldNullifierRoot)
	newNullifierRoot := nativeBWScalarToBN254(api, f, c.NewNullifierRoot)
	f.AssertIsEqual(droneID, value(leafDroneIDV2))
	f.AssertIsEqual(timeBucket, value(leafTimeBucketV2))
	f.AssertIsEqual(policyCommitment, policyFromLeaf)
	f.AssertIsEqual(oldNullifierRoot, f.NewElement(emptyNullifierRoot()))

	ok := value(leafConsistencyOKV2)
	okNative := publicValue(ok)
	api.AssertIsBoolean(okNative)
	api.AssertIsEqual(c.ConsistentCount, okNative)
	api.AssertIsEqual(c.SuspiciousCount, api.Sub(1, okNative))

	deviceLeaf := mimcBN254(f, value(leafObserverPublicKeyXV2), value(leafObserverPublicKeyYV2))
	memberRoot := bridgeMerkleRoot(api, f, deviceLeaf, c.MemberSiblings, c.PathBits)
	f.AssertIsEqual(memberRoot, memberRootValue)

	session := mimcBN254(f,
		f.NewElement(nullifier.SessionDomain),
		protocolVersion,
		droneID,
		timeBucket,
		policyCommitment,
	)
	nullifierValue := mimcBN254(f, f.NewElement(nullifier.NullifierDomain), deviceLeaf, session)
	f.AssertIsDifferent(nullifierValue, f.Zero())
	newRoot := bridgeMerkleRoot(api, f, nullifierValue, emptyNullifierSiblingsV2(), c.PathBits)
	f.AssertIsEqual(newRoot, newNullifierRoot)
	return nil
}

// BridgeBWV2Assignment converts one leaf proof, its V2 policy, and its member/
// nullifier openings into the recursive private witness. The circuit remains
// authoritative and verifies the proof plus both Merkle paths.
func BridgeBWV2Assignment(
	leafProof groth16.Proof,
	leafPublic witness.Witness,
	state [stateWidth]*big.Int,
	path BridgePathWitness,
	minimumQuorum uint32,
) (*BridgeBWV2, error) {
	if minimumQuorum == 0 {
		return nil, fmt.Errorf("BridgeBWV2 minimum quorum must be greater than zero")
	}
	for i, value := range state {
		if !canonicalBN254(value) {
			return nil, fmt.Errorf("BridgeBWV2 state[%d] is not a canonical BN254 scalar", i)
		}
	}
	if state[stateVersion].Cmp(big.NewInt(FinalPolicyV2Version)) != 0 {
		return nil, fmt.Errorf("BridgeBWV2 state protocolVersion must be %d", FinalPolicyV2Version)
	}
	if state[stateBucket].BitLen() > 64 || state[stateConsistent].BitLen() > 32 || state[stateSuspicious].BitLen() > 32 {
		return nil, fmt.Errorf("BridgeBWV2 state bucket/count is out of range")
	}
	if state[stateConsistent].Cmp(big.NewInt(1)) > 0 || state[stateSuspicious].Cmp(big.NewInt(1)) > 0 ||
		new(big.Int).Add(state[stateConsistent], state[stateSuspicious]).Cmp(big.NewInt(1)) != 0 {
		return nil, fmt.Errorf("BridgeBWV2 single-observer counts must sum to one")
	}
	if state[stateOldNullifierRoot].Cmp(emptyNullifierRoot()) != 0 {
		return nil, fmt.Errorf("BridgeBWV2 single-observer state must start from the empty nullifier root")
	}
	if leafPublic == nil {
		return nil, fmt.Errorf("BridgeBWV2 leaf public witness is nil")
	}
	publicWitness, err := leafPublic.Public()
	if err != nil {
		return nil, fmt.Errorf("BridgeBWV2 leaf public witness: %w", err)
	}
	signals, err := bn254PublicSignalsWithCount(publicWitness, leafPublicSignalCountV2)
	if err != nil {
		return nil, fmt.Errorf("BridgeBWV2 leaf signals: %w", err)
	}
	if !isOne(signals[leafObservationEligibleV2]) || (!isZero(signals[leafConsistencyOKV2]) && !isOne(signals[leafConsistencyOKV2])) {
		return nil, fmt.Errorf("BridgeBWV2 leaf observation-valid/outcome signals are invalid")
	}
	if signals[leafCalibrationProfileIDV2].BitLen() > 32 {
		return nil, fmt.Errorf("BridgeBWV2 leaf calibration profile ID is outside uint32")
	}
	if signals[leafDroneIDV2].Cmp(state[stateDrone]) != 0 || signals[leafTimeBucketV2].Cmp(state[stateBucket]) != 0 {
		return nil, fmt.Errorf("BridgeBWV2 state does not match V2 leaf session")
	}
	wantConsistent, wantSuspicious := new(big.Int), new(big.Int)
	if isOne(signals[leafConsistencyOKV2]) {
		wantConsistent.SetInt64(1)
	} else {
		wantSuspicious.SetInt64(1)
	}
	if state[stateConsistent].Cmp(wantConsistent) != 0 || state[stateSuspicious].Cmp(wantSuspicious) != 0 {
		return nil, fmt.Errorf("BridgeBWV2 counts do not match the V2 leaf outcome")
	}
	profileRoot, err := calibrationProfilePathRootV2(signals[leafCalibrationProfileIDV2], calibrationProfilePathV2{
		Siblings: path.ProfileSiblings,
		Bits:     path.ProfilePathBits,
	})
	if err != nil {
		return nil, fmt.Errorf("BridgeBWV2 calibration profile membership: %w", err)
	}
	if !canonicalBN254(path.ProfileSetRoot) || profileRoot.Cmp(path.ProfileSetRoot) != 0 {
		return nil, fmt.Errorf("BridgeBWV2 calibration profile path does not open the approved set root")
	}
	policy, err := FinalPolicyCommitmentV2(minimumQuorum, profileRoot)
	if err != nil {
		return nil, fmt.Errorf("BridgeBWV2 V2 policy: %w", err)
	}
	if state[statePolicy].Cmp(policy) != 0 {
		return nil, fmt.Errorf("BridgeBWV2 state policy commitment does not bind quorum/profile set")
	}
	proof, err := stdgroth16.ValueOfProof[sw_bn254.G1Affine, sw_bn254.G2Affine](leafProof)
	if err != nil {
		return nil, fmt.Errorf("translate BridgeBWV2 leaf proof: %w", err)
	}
	public, err := stdgroth16.ValueOfWitness[sw_bn254.ScalarField](leafPublic)
	if err != nil {
		return nil, fmt.Errorf("translate BridgeBWV2 leaf public witness: %w", err)
	}
	assignment := &BridgeBWV2{
		LeafProof: proof, LeafPublic: public,
		ProtocolVersion: state[stateVersion], DroneID: state[stateDrone], TimeBucket: state[stateBucket],
		PolicyCommitment: state[statePolicy], MemberRoot: state[stateMemberRoot],
		OldNullifierRoot: state[stateOldNullifierRoot], NewNullifierRoot: state[stateNewNullifierRoot],
		ConsistentCount: state[stateConsistent], SuspiciousCount: state[stateSuspicious],
		MinimumQuorum: minimumQuorum, CalibrationProfileSetRoot: path.ProfileSetRoot,
	}
	emptyNullifierSiblings := emptyNullifierSiblingValuesV2()
	for i := 0; i < membership.Depth; i++ {
		if !canonicalBN254(path.MemberSiblings[i]) {
			return nil, fmt.Errorf("BridgeBWV2 member sibling %d is not a canonical BN254 scalar", i)
		}
		if !canonicalBN254(path.NullifierSiblings[i]) {
			return nil, fmt.Errorf("BridgeBWV2 nullifier sibling %d is not a canonical BN254 scalar", i)
		}
		if path.NullifierSiblings[i].Cmp(emptyNullifierSiblings[i]) != 0 {
			return nil, fmt.Errorf("BridgeBWV2 nullifier sibling %d does not match the empty-tree constant", i)
		}
		if path.PathBits[i] != 0 && path.PathBits[i] != 1 {
			return nil, fmt.Errorf("BridgeBWV2 path bit %d is not boolean", i)
		}
		if !canonicalBN254(path.ProfileSiblings[i]) {
			return nil, fmt.Errorf("BridgeBWV2 profile sibling %d is not a canonical BN254 scalar", i)
		}
		if path.ProfilePathBits[i] != 0 && path.ProfilePathBits[i] != 1 {
			return nil, fmt.Errorf("BridgeBWV2 profile path bit %d is not boolean", i)
		}
		assignment.MemberSiblings[i] = emulated.ValueOf[sw_bn254.ScalarField](path.MemberSiblings[i])
		assignment.ProfileSiblings[i] = emulated.ValueOf[sw_bn254.ScalarField](path.ProfileSiblings[i])
		assignment.PathBits[i] = path.PathBits[i]
		assignment.ProfilePathBits[i] = path.ProfilePathBits[i]
	}
	return assignment, nil
}

// emptyNullifierSiblingValuesV2 returns the deterministic sibling at each
// level of the all-zero session nullifier tree. Because a V2 bridge only
// consumes one observer from the fixed empty root, these values are constants
// rather than witness inputs.
func emptyNullifierSiblingValuesV2() [membership.Depth]*big.Int {
	var siblings [membership.Depth]*big.Int
	root := new(big.Int)
	for depth := 0; depth < membership.Depth; depth++ {
		siblings[depth] = new(big.Int).Set(root)
		root = membership.MimcHash(root, root)
	}
	return siblings
}

func emptyNullifierSiblingsV2() [membership.Depth]emulated.Element[sw_bn254.ScalarField] {
	values := emptyNullifierSiblingValuesV2()
	var siblings [membership.Depth]emulated.Element[sw_bn254.ScalarField]
	for depth := 0; depth < membership.Depth; depth++ {
		siblings[depth] = emulated.ValueOf[sw_bn254.ScalarField](values[depth])
	}
	return siblings
}
