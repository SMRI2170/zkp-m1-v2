package pcd

import (
	"fmt"
	"math/big"

	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/constraint"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	"github.com/consensys/gnark/std/algebra/native/sw_bls12377"
	"github.com/consensys/gnark/std/math/emulated"
	stdgroth16 "github.com/consensys/gnark/std/recursion/groth16"

	"uav/aggregator/nullifier"
)

// State is the internal child statement shared by BridgeBW, NodeBLS, and
// NodeBW. oldNullifierRoot is the common empty session root; newNullifierRoot
// commits to the node's populated observer set.
const (
	stateVersion = iota
	stateDrone
	stateBucket
	statePolicy
	stateMemberRoot
	stateOldNullifierRoot
	stateNewNullifierRoot
	stateConsistent
	stateSuspicious
	stateWidth
)

// NodeBW verifies two BLS12-377 child proofs under one pinned key, decodes their
// canonical 36-limb BN254 states, and emits a disjoint-set union on BW6-761.
type NodeBW struct {
	LeftProof  stdgroth16.Proof[sw_bls12377.G1Affine, sw_bls12377.G2Affine]
	RightProof stdgroth16.Proof[sw_bls12377.G1Affine, sw_bls12377.G2Affine]
	LeftState  stdgroth16.Witness[sw_bls12377.ScalarField]
	RightState stdgroth16.Witness[sw_bls12377.ScalarField]

	LeftNullifierLeaves  [nullifier.TreeSize]emulated.Element[sw_bn254.ScalarField]
	RightNullifierLeaves [nullifier.TreeSize]emulated.Element[sw_bn254.ScalarField]

	leftVerifyingKey  stdgroth16.VerifyingKey[sw_bls12377.G1Affine, sw_bls12377.G2Affine, sw_bls12377.GT] `gnark:"-"`
	rightVerifyingKey stdgroth16.VerifyingKey[sw_bls12377.G1Affine, sw_bls12377.G2Affine, sw_bls12377.GT] `gnark:"-"`
	// protocolVersion is fixed at circuit construction and is deliberately
	// excluded from the witness/public statement.
	protocolVersion uint32 `gnark:"-"`

	ProtocolVersion  frontend.Variable `gnark:",public"`
	DroneID          frontend.Variable `gnark:",public"`
	TimeBucket       frontend.Variable `gnark:",public"`
	PolicyCommitment frontend.Variable `gnark:",public"`
	MemberRoot       frontend.Variable `gnark:",public"`
	OldNullifierRoot frontend.Variable `gnark:",public"`
	NewNullifierRoot frontend.Variable `gnark:",public"`
	ConsistentCount  frontend.Variable `gnark:",public"`
	SuspiciousCount  frontend.Variable `gnark:",public"`
}

func NewNodeBW(childCCS constraint.ConstraintSystem, childVK groth16.VerifyingKey) (*NodeBW, error) {
	return NewNodeBWForProtocol(childCCS, childVK, uint32(FinalPolicyVersion))
}

// NewNodeBWForProtocol constructs a merge circuit whose child and output
// states must all belong to the selected protocol version.
func NewNodeBWForProtocol(childCCS constraint.ConstraintSystem, childVK groth16.VerifyingKey, protocolVersion uint32) (*NodeBW, error) {
	return NewNodeBWWithChildKeysForProtocol(childCCS, childVK, childCCS, childVK, protocolVersion)
}

// NewNodeBWWithChildKeys supports a finite-depth asymmetric tree: both child
// verification keys remain compile-time constants, but the left and right
// child circuits may differ (for example, a two-leaf merge and a one-leaf
// promotion). This avoids introducing an unchecked dummy proof for odd batches.
func NewNodeBWWithChildKeys(
	leftCCS constraint.ConstraintSystem,
	leftVK groth16.VerifyingKey,
	rightCCS constraint.ConstraintSystem,
	rightVK groth16.VerifyingKey,
) (*NodeBW, error) {
	return NewNodeBWWithChildKeysForProtocol(leftCCS, leftVK, rightCCS, rightVK, uint32(FinalPolicyVersion))
}

// NewNodeBWWithChildKeysForProtocol supports asymmetric child circuits while
// pinning both verification keys and the protocol version into this circuit.
func NewNodeBWWithChildKeysForProtocol(
	leftCCS constraint.ConstraintSystem,
	leftVK groth16.VerifyingKey,
	rightCCS constraint.ConstraintSystem,
	rightVK groth16.VerifyingKey,
	protocolVersion uint32,
) (*NodeBW, error) {
	if err := validatePCDProtocolVersion(protocolVersion); err != nil {
		return nil, err
	}
	if leftCCS == nil || leftCCS.GetNbPublicVariables()-1 != encodedStateWidth {
		got := 0
		if leftCCS != nil {
			got = leftCCS.GetNbPublicVariables() - 1
		}
		return nil, fmt.Errorf("NodeBW left child must expose %d state limbs, got %d", encodedStateWidth, got)
	}
	if rightCCS == nil || rightCCS.GetNbPublicVariables()-1 != encodedStateWidth {
		got := 0
		if rightCCS != nil {
			got = rightCCS.GetNbPublicVariables() - 1
		}
		return nil, fmt.Errorf("NodeBW right child must expose %d state limbs, got %d", encodedStateWidth, got)
	}
	leftKey, err := stdgroth16.ValueOfVerifyingKeyFixed[
		sw_bls12377.G1Affine, sw_bls12377.G2Affine, sw_bls12377.GT,
	](leftVK)
	if err != nil {
		return nil, fmt.Errorf("pin NodeBW left child key: %w", err)
	}
	rightKey, err := stdgroth16.ValueOfVerifyingKeyFixed[
		sw_bls12377.G1Affine, sw_bls12377.G2Affine, sw_bls12377.GT,
	](rightVK)
	if err != nil {
		return nil, fmt.Errorf("pin NodeBW right child key: %w", err)
	}
	return &NodeBW{
		LeftProof:         stdgroth16.PlaceholderProof[sw_bls12377.G1Affine, sw_bls12377.G2Affine](leftCCS),
		RightProof:        stdgroth16.PlaceholderProof[sw_bls12377.G1Affine, sw_bls12377.G2Affine](rightCCS),
		LeftState:         stdgroth16.PlaceholderWitness[sw_bls12377.ScalarField](leftCCS),
		RightState:        stdgroth16.PlaceholderWitness[sw_bls12377.ScalarField](rightCCS),
		leftVerifyingKey:  leftKey,
		rightVerifyingKey: rightKey,
		protocolVersion:   protocolVersion,
	}, nil
}

func (c *NodeBW) Define(api frontend.API) error {
	v, err := stdgroth16.NewVerifier[
		sw_bls12377.ScalarField, sw_bls12377.G1Affine, sw_bls12377.G2Affine, sw_bls12377.GT,
	](api)
	if err != nil {
		return err
	}
	if err = v.AssertProof(c.leftVerifyingKey, c.LeftProof, c.LeftState); err != nil {
		return err
	}
	if err = v.AssertProof(c.rightVerifyingKey, c.RightProof, c.RightState); err != nil {
		return err
	}
	if len(c.LeftState.Public) != encodedStateWidth || len(c.RightState.Public) != encodedStateWidth {
		return fmt.Errorf("NodeBW children must expose %d state limbs", encodedStateWidth)
	}
	blsField, err := emulated.NewField[sw_bls12377.ScalarField](api)
	if err != nil {
		return err
	}
	bnField, err := emulated.NewField[sw_bn254.ScalarField](api)
	if err != nil {
		return err
	}
	leftLimbs, err := recursiveBLSStateLimbs(api, blsField, c.LeftState)
	if err != nil {
		return err
	}
	rightLimbs, err := recursiveBLSStateLimbs(api, blsField, c.RightState)
	if err != nil {
		return err
	}
	left, err := DecodeStateLimbs(bnField, leftLimbs)
	if err != nil {
		return err
	}
	right, err := DecodeStateLimbs(bnField, rightLimbs)
	if err != nil {
		return err
	}
	out, err := nativeBWStateToBN254(api, bnField, [stateWidth]frontend.Variable{
		c.ProtocolVersion, c.DroneID, c.TimeBucket, c.PolicyCommitment,
		c.MemberRoot, c.OldNullifierRoot, c.NewNullifierRoot,
		c.ConsistentCount, c.SuspiciousCount,
	})
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

// recursiveBLSStateLimbs converts one child public input at a time to its
// canonical low 64-bit value. The high BLS limbs must be zero before these
// values are interpreted as BN254 state limbs.
func recursiveBLSStateLimbs(
	api frontend.API,
	field *emulated.Field[sw_bls12377.ScalarField],
	w stdgroth16.Witness[sw_bls12377.ScalarField],
) ([encodedStateWidth]frontend.Variable, error) {
	var limbs [encodedStateWidth]frontend.Variable
	if len(w.Public) != encodedStateWidth {
		return limbs, fmt.Errorf("BLS child state has %d limbs, expected %d", len(w.Public), encodedStateWidth)
	}
	for i := range w.Public {
		canonical := field.ReduceStrict(&w.Public[i])
		if len(canonical.Limbs) < 1 {
			return limbs, fmt.Errorf("BLS child limb %d has no canonical limb", i)
		}
		for j := 1; j < len(canonical.Limbs); j++ {
			api.AssertIsEqual(canonical.Limbs[j], 0)
		}
		limbs[i] = canonical.Limbs[0]
	}
	return limbs, nil
}

func nativeBWStateToBN254(
	api frontend.API,
	field *emulated.Field[sw_bn254.ScalarField],
	state [stateWidth]frontend.Variable,
) ([stateWidth]*emulated.Element[sw_bn254.ScalarField], error) {
	var result [stateWidth]*emulated.Element[sw_bn254.ScalarField]
	for i := range state {
		result[i] = nativeBWScalarToBN254(api, field, state[i])
	}
	return result, nil
}

// nativeBWScalarToBN254 constrains a BW6-761 scalar to the canonical BN254
// scalar range, then splits it into explicit 64-bit limbs. A native BW6 field
// variable cannot be passed directly to emulated.NewElement: its 377-bit
// representation is wider than the emulated 254-bit field.
func nativeBWScalarToBN254(
	api frontend.API,
	field *emulated.Field[sw_bn254.ScalarField],
	value frontend.Variable,
) *emulated.Element[sw_bn254.ScalarField] {
	bits := api.ToBinary(value, bn254LimbCount*bn254LimbBits)
	limbs := make([]frontend.Variable, bn254LimbCount)
	for i := range limbs {
		start := i * bn254LimbBits
		end := start + bn254LimbBits
		if end > len(bits) {
			end = len(bits)
		}
		limbs[i] = api.FromBinary(bits[start:end]...)
	}
	candidate := field.NewElement(limbs)
	field.AssertIsInRange(candidate)
	return field.ReduceStrict(candidate)
}

// NodeBWAssignment converts two native child proofs and their public states.
func NodeBWAssignment(leftProof groth16.Proof, leftPublic witness.Witness, rightProof groth16.Proof, rightPublic witness.Witness, state [stateWidth]*big.Int, nullifiers NullifierSetWitness) (*NodeBW, error) {
	lp, err := stdgroth16.ValueOfProof[sw_bls12377.G1Affine, sw_bls12377.G2Affine](leftProof)
	if err != nil {
		return nil, err
	}
	rp, err := stdgroth16.ValueOfProof[sw_bls12377.G1Affine, sw_bls12377.G2Affine](rightProof)
	if err != nil {
		return nil, err
	}
	lw, err := stdgroth16.ValueOfWitness[sw_bls12377.ScalarField](leftPublic)
	if err != nil {
		return nil, err
	}
	rw, err := stdgroth16.ValueOfWitness[sw_bls12377.ScalarField](rightPublic)
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
	return &NodeBW{LeftProof: lp, RightProof: rp, LeftState: lw, RightState: rw,
		LeftNullifierLeaves: leftLeaves, RightNullifierLeaves: rightLeaves,
		ProtocolVersion: state[stateVersion], DroneID: state[stateDrone], TimeBucket: state[stateBucket], PolicyCommitment: state[statePolicy], MemberRoot: state[stateMemberRoot], OldNullifierRoot: state[stateOldNullifierRoot], NewNullifierRoot: state[stateNewNullifierRoot], ConsistentCount: state[stateConsistent], SuspiciousCount: state[stateSuspicious]}, nil
}
