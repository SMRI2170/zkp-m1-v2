package pcd

import (
	"fmt"
	"math/big"

	bn254mimc "github.com/consensys/gnark-crypto/ecc/bn254/fr/mimc"
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

const (
	leafWithin30AndDetected = 6
	leafDroneID             = 10
	leafTimeBucket          = 13
	leafConsistencyOK       = 14
	leafDroneAuthOK         = 15
	leafPublicSignalCount   = 18
)

// BridgeBW verifies a release-pinned V1 BN254 leaf proof in BW6-761 and converts
// its relevant public signals into the ordered recursive-node state. V2 uses a
// separate BridgeBWV2 type and its versioned 8-signal leaf verification key.
type BridgeBW struct {
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

	// The member and nullifier paths use BN254 field elements, even though this
	// bridge itself is a BW6-761 circuit. They are verified with the exact
	// MiMC_BN254 construction used by the leaf-side registration tree.
	MemberSiblings    [membership.Depth]emulated.Element[sw_bn254.ScalarField]
	NullifierSiblings [membership.Depth]emulated.Element[sw_bn254.ScalarField]
	PathBits          [membership.Depth]frontend.Variable
}

// NewBridgeBW constructs a bridge for a known BN254 leaf circuit and its
// release-pinned verification key. The leaf is required to expose the 18
// signals documented in docs/protocol/leaf-attestation-v1.md.
func NewBridgeBW(leafCCS constraint.ConstraintSystem, leafVK groth16.VerifyingKey) (*BridgeBW, error) {
	if leafCCS == nil || leafCCS.GetNbPublicVariables()-1 != leafPublicSignalCount {
		got := 0
		if leafCCS != nil {
			got = leafCCS.GetNbPublicVariables() - 1
		}
		return nil, fmt.Errorf("BridgeBW requires %d leaf public signals, got %d", leafPublicSignalCount, got)
	}
	return newBridgeBW(
		leafVK,
		stdgroth16.PlaceholderProof[sw_bn254.G1Affine, sw_bn254.G2Affine](leafCCS),
		stdgroth16.PlaceholderWitness[sw_bn254.ScalarField](leafCCS),
	)
}

// NewBridgeBWFromSample builds the same fixed-key bridge shape from a real
// Circom proof and public witness. This is useful when the native Circom R1CS
// is not available as a gnark ConstraintSystem but its VK/proof artifacts are.
func NewBridgeBWFromSample(leafVK groth16.VerifyingKey, shapeProof groth16.Proof, shapePublic witness.Witness) (*BridgeBW, error) {
	proof, err := stdgroth16.ValueOfProof[sw_bn254.G1Affine, sw_bn254.G2Affine](shapeProof)
	if err != nil {
		return nil, fmt.Errorf("shape BridgeBW leaf proof: %w", err)
	}
	public, err := stdgroth16.ValueOfWitness[sw_bn254.ScalarField](shapePublic)
	if err != nil {
		return nil, fmt.Errorf("shape BridgeBW leaf public witness: %w", err)
	}
	if len(public.Public) != leafPublicSignalCount {
		return nil, fmt.Errorf("BridgeBW shape witness must have %d public signals, got %d", leafPublicSignalCount, len(public.Public))
	}
	return newBridgeBW(leafVK, proof, public)
}

func newBridgeBW(
	leafVK groth16.VerifyingKey,
	proof stdgroth16.Proof[sw_bn254.G1Affine, sw_bn254.G2Affine],
	public stdgroth16.Witness[sw_bn254.ScalarField],
) (*BridgeBW, error) {
	if leafVK == nil || leafVK.NbPublicWitness() != leafPublicSignalCount {
		got := 0
		if leafVK != nil {
			got = leafVK.NbPublicWitness()
		}
		return nil, fmt.Errorf("BridgeBW requires a leaf VK with %d public signals, got %d", leafPublicSignalCount, got)
	}
	vk, err := stdgroth16.ValueOfVerifyingKeyFixed[
		sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl,
	](leafVK)
	if err != nil {
		return nil, fmt.Errorf("pin BridgeBW leaf key: %w", err)
	}
	return &BridgeBW{
		LeafProof:    proof,
		LeafPublic:   public,
		verifyingKey: vk,
	}, nil
}

func (c *BridgeBW) Define(api frontend.API) error {
	v, err := stdgroth16.NewVerifier[
		sw_bn254.ScalarField, sw_bn254.G1Affine, sw_bn254.G2Affine, sw_bn254.GTEl,
	](api)
	if err != nil {
		return err
	}
	if err = v.AssertProof(c.verifyingKey, c.LeafProof, c.LeafPublic); err != nil {
		return err
	}
	if len(c.LeafPublic.Public) != leafPublicSignalCount {
		return fmt.Errorf("BridgeBW leaf must expose %d public signals", leafPublicSignalCount)
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
		coef := big.NewInt(1)
		for _, limb := range x.Limbs {
			acc = api.Add(acc, api.Mul(limb, new(big.Int).Set(coef)))
			coef.Lsh(coef, 64)
		}
		return acc
	}

	api.AssertIsEqual(c.ProtocolVersion, 1)
	within := value(leafWithin30AndDetected)
	droneAuth := value(leafDroneAuthOK)
	f.AssertIsEqual(within, f.One())
	f.AssertIsEqual(droneAuth, f.One())
	droneID := nativeBWScalarToBN254(api, f, c.DroneID)
	timeBucket := nativeBWScalarToBN254(api, f, c.TimeBucket)
	protocolVersion := nativeBWScalarToBN254(api, f, c.ProtocolVersion)
	policyCommitment := nativeBWScalarToBN254(api, f, c.PolicyCommitment)
	memberRootValue := nativeBWScalarToBN254(api, f, c.MemberRoot)
	oldNullifierRoot := nativeBWScalarToBN254(api, f, c.OldNullifierRoot)
	newNullifierRoot := nativeBWScalarToBN254(api, f, c.NewNullifierRoot)
	f.AssertIsEqual(droneID, value(leafDroneID))
	f.AssertIsEqual(timeBucket, value(leafTimeBucket))
	ok := value(leafConsistencyOK)
	okNative := publicValue(ok)
	api.AssertIsBoolean(okNative)
	api.AssertIsEqual(c.ConsistentCount, okNative)
	api.AssertIsEqual(c.SuspiciousCount, api.Sub(1, okNative))

	// Bind the device public key from the verified leaf to the authorised
	// memberRoot, then consume its session-specific nullifier slot. This is the
	// one-time-participation invariant: the old path must contain zero, while
	// the new path contains the derived nonzero nullifier at that same index.
	deviceLeaf := mimcBN254(f, value(11), value(12))
	memberRoot := bridgeMerkleRoot(api, f, deviceLeaf, c.MemberSiblings, c.PathBits)
	f.AssertIsEqual(memberRoot, memberRootValue)

	session := mimcBN254(f,
		f.NewElement(nullifier.SessionDomain),
		protocolVersion,
		droneID,
		timeBucket,
		policyCommitment,
	)
	oldRoot := bridgeMerkleRoot(api, f, f.Zero(), c.NullifierSiblings, c.PathBits)
	f.AssertIsEqual(oldRoot, oldNullifierRoot)
	nullifierValue := mimcBN254(f, f.NewElement(nullifier.NullifierDomain), deviceLeaf, session)
	f.AssertIsDifferent(nullifierValue, f.Zero())
	newRoot := bridgeMerkleRoot(api, f, nullifierValue, c.NullifierSiblings, c.PathBits)
	f.AssertIsEqual(newRoot, newNullifierRoot)
	return nil
}

// mimcBN254 is the MiMC_BN254 Miyaguchi-Preneel construction evaluated in an
// emulated BN254 scalar field. BridgeBW cannot use the host BW6 MiMC gadget:
// that would produce a different registration/nullifier root. The round
// constants are obtained from gnark-crypto, the same source used by the native
// BN254 membership and nullifier circuits.
func mimcBN254(f *emulated.Field[sw_bn254.ScalarField], elems ...*emulated.Element[sw_bn254.ScalarField]) *emulated.Element[sw_bn254.ScalarField] {
	constants := bn254mimc.GetConstants()
	h := f.Zero()
	for _, stream := range elems {
		x := stream
		for i := range constants {
			x = f.Add(f.Add(x, h), f.NewElement(&constants[i]))
			x2 := f.Mul(x, x)
			x4 := f.Mul(x2, x2)
			x = f.Mul(x4, x)
		}
		x = f.Add(x, h)
		h = f.Add(f.Add(h, x), stream)
	}
	return h
}

func bridgeMerkleRoot(api frontend.API, f *emulated.Field[sw_bn254.ScalarField], leaf *emulated.Element[sw_bn254.ScalarField], siblings [membership.Depth]emulated.Element[sw_bn254.ScalarField], bits [membership.Depth]frontend.Variable) *emulated.Element[sw_bn254.ScalarField] {
	cur := leaf
	for i := 0; i < membership.Depth; i++ {
		api.AssertIsBoolean(bits[i])
		left := f.Select(bits[i], &siblings[i], cur)
		right := f.Select(bits[i], cur, &siblings[i])
		cur = mimcBN254(f, left, right)
	}
	return cur
}

// BridgeBWAssignment converts a native BN254 Groth16 leaf proof and its public
// witness into the private recursive witness accepted by BridgeBW. State must
// contain the public values enforced by Define; inconsistent values fail in the
// bridge circuit rather than being trusted from a relayer.
type BridgePathWitness struct {
	MemberSiblings    [membership.Depth]*big.Int
	NullifierSiblings [membership.Depth]*big.Int
	PathBits          [membership.Depth]int
	ProfileSetRoot    *big.Int
	ProfileSiblings   [membership.Depth]*big.Int
	ProfilePathBits   [membership.Depth]int
}

func BridgeBWAssignment(leafProof groth16.Proof, leafPublic witness.Witness, state [stateWidth]*big.Int, path BridgePathWitness) (*BridgeBW, error) {
	if err := validateSingleObserverState(state); err != nil {
		return nil, err
	}
	proof, err := stdgroth16.ValueOfProof[sw_bn254.G1Affine, sw_bn254.G2Affine](leafProof)
	if err != nil {
		return nil, err
	}
	pub, err := stdgroth16.ValueOfWitness[sw_bn254.ScalarField](leafPublic)
	if err != nil {
		return nil, err
	}
	assignment := &BridgeBW{LeafProof: proof, LeafPublic: pub,
		ProtocolVersion: state[stateVersion], DroneID: state[stateDrone], TimeBucket: state[stateBucket], PolicyCommitment: state[statePolicy], MemberRoot: state[stateMemberRoot], OldNullifierRoot: state[stateOldNullifierRoot], NewNullifierRoot: state[stateNewNullifierRoot], ConsistentCount: state[stateConsistent], SuspiciousCount: state[stateSuspicious]}
	for i := 0; i < membership.Depth; i++ {
		if path.MemberSiblings[i] == nil || path.MemberSiblings[i].Sign() < 0 || path.MemberSiblings[i].Cmp(bn254ScalarModulus) >= 0 {
			return nil, fmt.Errorf("BridgeBW member sibling %d is not a canonical BN254 scalar", i)
		}
		if path.NullifierSiblings[i] == nil || path.NullifierSiblings[i].Sign() < 0 || path.NullifierSiblings[i].Cmp(bn254ScalarModulus) >= 0 {
			return nil, fmt.Errorf("BridgeBW nullifier sibling %d is not a canonical BN254 scalar", i)
		}
		if path.PathBits[i] != 0 && path.PathBits[i] != 1 {
			return nil, fmt.Errorf("BridgeBW path bit %d is not boolean", i)
		}
		assignment.MemberSiblings[i] = emulated.ValueOf[sw_bn254.ScalarField](path.MemberSiblings[i])
		assignment.NullifierSiblings[i] = emulated.ValueOf[sw_bn254.ScalarField](path.NullifierSiblings[i])
		assignment.PathBits[i] = path.PathBits[i]
	}
	return assignment, nil
}
