package pcd

import (
	"fmt"
	"math/big"

	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/constraint"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bw6761"
	"github.com/consensys/gnark/std/math/emulated"
	stdgroth16 "github.com/consensys/gnark/std/recursion/groth16"

	"uav/aggregator/nullifier"
)

// NodeBLS is the BLS12-377 half of the recursive pair. It verifies two
// BW6-761 child proofs under a verification key fixed when this circuit is compiled.
// Keeping the key out of the witness is essential: otherwise a relayer could
// substitute a valid proof for a different recursive statement.
//
// BN254 state values cross the BLS public-input boundary as four 64-bit limbs;
// the circuit reconstructs and checks canonical field elements before comparing
// session fields or merging nullifier sets.
type NodeBLS struct {
	LeftProof  stdgroth16.Proof[sw_bw6761.G1Affine, sw_bw6761.G2Affine]
	RightProof stdgroth16.Proof[sw_bw6761.G1Affine, sw_bw6761.G2Affine]
	LeftState  stdgroth16.Witness[sw_bw6761.ScalarField]
	RightState stdgroth16.Witness[sw_bw6761.ScalarField]

	LeftNullifierLeaves  [nullifier.TreeSize]emulated.Element[sw_bn254.ScalarField]
	RightNullifierLeaves [nullifier.TreeSize]emulated.Element[sw_bn254.ScalarField]

	verifyingKey stdgroth16.VerifyingKey[sw_bw6761.G1Affine, sw_bw6761.G2Affine, sw_bw6761.GTEl] `gnark:"-"`
	// protocolVersion is fixed when the circuit is compiled. It is not a
	// witness value: a V1 verifier key can never be reused to accept V2 states
	// (or vice versa).
	protocolVersion uint32 `gnark:"-"`

	State [encodedStateWidth]frontend.Variable `gnark:",public"`
}

func NewNodeBLS(childCCS constraint.ConstraintSystem, childVK groth16.VerifyingKey) (*NodeBLS, error) {
	return NewNodeBLSForProtocol(childCCS, childVK, uint32(FinalPolicyVersion))
}

// NewNodeBLSForProtocol constructs a version-pinned recursive merge circuit.
// V1 and V2 intentionally share the state layout but not the verifying keys.
func NewNodeBLSForProtocol(childCCS constraint.ConstraintSystem, childVK groth16.VerifyingKey, protocolVersion uint32) (*NodeBLS, error) {
	if err := validatePCDProtocolVersion(protocolVersion); err != nil {
		return nil, err
	}
	if childCCS == nil || childCCS.GetNbPublicVariables()-1 != stateWidth {
		got := 0
		if childCCS != nil {
			got = childCCS.GetNbPublicVariables() - 1
		}
		return nil, fmt.Errorf("NodeBLS requires a %d-value BW6 child state, got %d", stateWidth, got)
	}
	return newNodeBLS(
		childVK,
		stdgroth16.PlaceholderProof[sw_bw6761.G1Affine, sw_bw6761.G2Affine](childCCS),
		stdgroth16.PlaceholderWitness[sw_bw6761.ScalarField](childCCS),
		protocolVersion,
	)
}

// NewNodeBLSFromSample sizes the recursive variables from an actual BW6 proof
// and public witness. It permits a finite-depth setup chain without requiring
// the child circuit source to be recompiled in this process.
func NewNodeBLSFromSample(childVK groth16.VerifyingKey, shapeProof groth16.Proof, shapePublic witness.Witness) (*NodeBLS, error) {
	return NewNodeBLSFromSampleForProtocol(childVK, shapeProof, shapePublic, uint32(FinalPolicyVersion))
}

// NewNodeBLSFromSampleForProtocol is the sample-shaped constructor for V2
// Circom leaf bridges and other child systems unavailable as gnark CCS values.
func NewNodeBLSFromSampleForProtocol(childVK groth16.VerifyingKey, shapeProof groth16.Proof, shapePublic witness.Witness, protocolVersion uint32) (*NodeBLS, error) {
	if err := validatePCDProtocolVersion(protocolVersion); err != nil {
		return nil, err
	}
	proof, err := stdgroth16.ValueOfProof[sw_bw6761.G1Affine, sw_bw6761.G2Affine](shapeProof)
	if err != nil {
		return nil, fmt.Errorf("shape NodeBLS child proof: %w", err)
	}
	public, err := stdgroth16.ValueOfWitness[sw_bw6761.ScalarField](shapePublic)
	if err != nil {
		return nil, fmt.Errorf("shape NodeBLS child state: %w", err)
	}
	if len(public.Public) != stateWidth {
		return nil, fmt.Errorf("NodeBLS child state must have %d fields, got %d", stateWidth, len(public.Public))
	}
	return newNodeBLS(childVK, proof, public, protocolVersion)
}

func newNodeBLS(
	childVK groth16.VerifyingKey,
	proof stdgroth16.Proof[sw_bw6761.G1Affine, sw_bw6761.G2Affine],
	public stdgroth16.Witness[sw_bw6761.ScalarField],
	protocolVersion uint32,
) (*NodeBLS, error) {
	vk, err := stdgroth16.ValueOfVerifyingKeyFixed[
		sw_bw6761.G1Affine, sw_bw6761.G2Affine, sw_bw6761.GTEl,
	](childVK)
	if err != nil {
		return nil, fmt.Errorf("pin NodeBLS child key: %w", err)
	}
	return &NodeBLS{
		LeftProof:       proof,
		RightProof:      proof,
		LeftState:       public,
		RightState:      public,
		verifyingKey:    vk,
		protocolVersion: protocolVersion,
	}, nil
}

func (c *NodeBLS) Define(api frontend.API) error {
	v, err := stdgroth16.NewVerifier[
		sw_bw6761.ScalarField, sw_bw6761.G1Affine, sw_bw6761.G2Affine, sw_bw6761.GTEl,
	](api)
	if err != nil {
		return err
	}
	if err = v.AssertProof(c.verifyingKey, c.LeftProof, c.LeftState); err != nil {
		return err
	}
	if err = v.AssertProof(c.verifyingKey, c.RightProof, c.RightState); err != nil {
		return err
	}
	if len(c.LeftState.Public) != stateWidth || len(c.RightState.Public) != stateWidth {
		return fmt.Errorf("NodeBLS children must expose %d state values", stateWidth)
	}
	bwField, err := emulated.NewField[sw_bw6761.ScalarField](api)
	if err != nil {
		return err
	}
	bnField, err := emulated.NewField[sw_bn254.ScalarField](api)
	if err != nil {
		return err
	}
	var leftBW, rightBW [stateWidth]emulated.Element[sw_bw6761.ScalarField]
	copy(leftBW[:], c.LeftState.Public)
	copy(rightBW[:], c.RightState.Public)
	left, err := BWStateToBN254(api, bwField, bnField, leftBW)
	if err != nil {
		return err
	}
	right, err := BWStateToBN254(api, bwField, bnField, rightBW)
	if err != nil {
		return err
	}
	out, err := DecodeStateLimbs(bnField, c.State)
	if err != nil {
		return err
	}
	for i := 0; i <= stateMemberRoot; i++ {
		bnField.AssertIsEqual(left[i], right[i])
		bnField.AssertIsEqual(out[i], left[i])
	}
	bnField.AssertIsEqual(out[stateVersion], bnField.NewElement(c.protocolVersion))
	for _, child := range [2][stateWidth]*emulated.Element[sw_bn254.ScalarField]{left, right} {
		assertEmulatedFieldBits(api, bnField, child[stateBucket], 64)
		assertEmulatedFieldBits(api, bnField, child[stateConsistent], 32)
		assertEmulatedFieldBits(api, bnField, child[stateSuspicious], 32)
	}
	bnField.AssertIsEqual(left[stateOldNullifierRoot], right[stateOldNullifierRoot])
	bnField.AssertIsEqual(out[stateOldNullifierRoot], left[stateOldNullifierRoot])
	unionCounts, err := assertNullifierSetUnion(api, bnField, c.LeftNullifierLeaves, c.RightNullifierLeaves,
		left[stateNewNullifierRoot], right[stateNewNullifierRoot], out[stateNewNullifierRoot])
	if err != nil {
		return err
	}
	assertLeafCountMatchesUnion(api, bnField, left, unionCounts.Left)
	assertLeafCountMatchesUnion(api, bnField, right, unionCounts.Right)
	bnField.AssertIsEqual(out[stateConsistent], bnField.Add(left[stateConsistent], right[stateConsistent]))
	bnField.AssertIsEqual(out[stateSuspicious], bnField.Add(left[stateSuspicious], right[stateSuspicious]))
	assertEmulatedFieldBits(api, bnField, out[stateBucket], 64)
	assertEmulatedFieldBits(api, bnField, out[stateConsistent], 32)
	assertEmulatedFieldBits(api, bnField, out[stateSuspicious], 32)
	return nil
}

func assertLeafCountMatchesUnion(
	api frontend.API,
	field *emulated.Field[sw_bn254.ScalarField],
	state [stateWidth]*emulated.Element[sw_bn254.ScalarField],
	occupied frontend.Variable,
) {
	count := field.Add(state[stateConsistent], state[stateSuspicious])
	api.AssertIsEqual(packBN254Element(api, field, count), occupied)
}

func assertEmulatedFieldBits(
	api frontend.API,
	field *emulated.Field[sw_bn254.ScalarField],
	value *emulated.Element[sw_bn254.ScalarField],
	width int,
) {
	bits := field.ToBitsCanonical(value)
	for i := width; i < len(bits); i++ {
		api.AssertIsEqual(bits[i], 0)
	}
}

// NodeBLSAssignment converts native BW6-761 proofs and public witnesses into
// the private recursive witnesses accepted by NodeBLS.
func NodeBLSAssignment(leftProof groth16.Proof, leftPublic witness.Witness, rightProof groth16.Proof, rightPublic witness.Witness, state [stateWidth]*big.Int, nullifiers NullifierSetWitness) (*NodeBLS, error) {
	lp, err := stdgroth16.ValueOfProof[sw_bw6761.G1Affine, sw_bw6761.G2Affine](leftProof)
	if err != nil {
		return nil, err
	}
	rp, err := stdgroth16.ValueOfProof[sw_bw6761.G1Affine, sw_bw6761.G2Affine](rightProof)
	if err != nil {
		return nil, err
	}
	lw, err := stdgroth16.ValueOfWitness[sw_bw6761.ScalarField](leftPublic)
	if err != nil {
		return nil, err
	}
	rw, err := stdgroth16.ValueOfWitness[sw_bw6761.ScalarField](rightPublic)
	if err != nil {
		return nil, err
	}
	encoded, err := EncodeState(state)
	if err != nil {
		return nil, err
	}
	leftLeaves, err := assignNullifierLeaves(nullifiers.Left)
	if err != nil {
		return nil, fmt.Errorf("encode left nullifier leaves: %w", err)
	}
	rightLeaves, err := assignNullifierLeaves(nullifiers.Right)
	if err != nil {
		return nil, fmt.Errorf("encode right nullifier leaves: %w", err)
	}
	assignment := &NodeBLS{LeftProof: lp, RightProof: rp, LeftState: lw, RightState: rw,
		LeftNullifierLeaves: leftLeaves, RightNullifierLeaves: rightLeaves}
	for i := range encoded {
		assignment.State[i] = encoded[i]
	}
	return assignment, nil
}
