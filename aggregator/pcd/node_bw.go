package pcd

import (
	"fmt"
	"math/big"

	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/constraint"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/algebra/native/sw_bls12377"
	"github.com/consensys/gnark/std/math/emulated"
	stdgroth16 "github.com/consensys/gnark/std/recursion/groth16"
)

// OrderedState is the child statement consumed by NodeBW. The two roots model
// an authenticated append transition: the right child must start exactly where
// the left child finished. This is safer than pretending two arbitrary roots
// can be combined by hashing them.
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

// NodeBW verifies two BLS12-377 child proofs under one pinned key and emits
// their ordered merged state on BW6-761. It is the first repeating PCD node;
// a complementary NodeBLS will consume this node's proof in the other cycle
// direction once the mutually released key artifacts exist.
type NodeBW struct {
	LeftProof  stdgroth16.Proof[sw_bls12377.G1Affine, sw_bls12377.G2Affine]
	RightProof stdgroth16.Proof[sw_bls12377.G1Affine, sw_bls12377.G2Affine]
	LeftState  stdgroth16.Witness[sw_bls12377.ScalarField]
	RightState stdgroth16.Witness[sw_bls12377.ScalarField]

	verifyingKey stdgroth16.VerifyingKey[sw_bls12377.G1Affine, sw_bls12377.G2Affine, sw_bls12377.GT] `gnark:"-"`

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
	vk, err := stdgroth16.ValueOfVerifyingKeyFixed[
		sw_bls12377.G1Affine, sw_bls12377.G2Affine, sw_bls12377.GT,
	](childVK)
	if err != nil {
		return nil, fmt.Errorf("pin NodeBW child key: %w", err)
	}
	return &NodeBW{
		LeftProof:    stdgroth16.PlaceholderProof[sw_bls12377.G1Affine, sw_bls12377.G2Affine](childCCS),
		RightProof:   stdgroth16.PlaceholderProof[sw_bls12377.G1Affine, sw_bls12377.G2Affine](childCCS),
		LeftState:    stdgroth16.PlaceholderWitness[sw_bls12377.ScalarField](childCCS),
		RightState:   stdgroth16.PlaceholderWitness[sw_bls12377.ScalarField](childCCS),
		verifyingKey: vk,
	}, nil
}

func (c *NodeBW) Define(api frontend.API) error {
	v, err := stdgroth16.NewVerifier[
		sw_bls12377.ScalarField, sw_bls12377.G1Affine, sw_bls12377.G2Affine, sw_bls12377.GT,
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
		return fmt.Errorf("NodeBW children must expose %d state values", stateWidth)
	}
	f, err := emulated.NewField[sw_bls12377.ScalarField](api)
	if err != nil {
		return err
	}
	value := func(w stdgroth16.Witness[sw_bls12377.ScalarField], i int) frontend.Variable {
		x := f.ReduceStrict(&w.Public[i])
		acc := frontend.Variable(0)
		coef := big.NewInt(1)
		for _, limb := range x.Limbs {
			acc = api.Add(acc, api.Mul(limb, new(big.Int).Set(coef)))
			coef.Lsh(coef, 64)
		}
		return acc
	}
	left, right := c.LeftState, c.RightState
	// All session/policy/authentication roots must be identical.
	out := []frontend.Variable{c.ProtocolVersion, c.DroneID, c.TimeBucket, c.PolicyCommitment, c.MemberRoot}
	for i := 0; i <= stateMemberRoot; i++ {
		api.AssertIsEqual(value(left, i), value(right, i))
		api.AssertIsEqual(out[i], value(left, i))
	}
	// The ordered state hand-off is the nullifier anti-replay invariant.
	api.AssertIsEqual(value(left, stateNewNullifierRoot), value(right, stateOldNullifierRoot))
	api.AssertIsEqual(c.OldNullifierRoot, value(left, stateOldNullifierRoot))
	api.AssertIsEqual(c.NewNullifierRoot, value(right, stateNewNullifierRoot))
	api.AssertIsEqual(c.ConsistentCount, api.Add(value(left, stateConsistent), value(right, stateConsistent)))
	api.AssertIsEqual(c.SuspiciousCount, api.Add(value(left, stateSuspicious), value(right, stateSuspicious)))
	return nil
}

// NodeBWAssignment converts two native child proofs and their public states.
func NodeBWAssignment(leftProof groth16.Proof, leftPublic witness.Witness, rightProof groth16.Proof, rightPublic witness.Witness, state [stateWidth]*big.Int) (*NodeBW, error) {
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
	return &NodeBW{LeftProof: lp, RightProof: rp, LeftState: lw, RightState: rw,
		ProtocolVersion: state[stateVersion], DroneID: state[stateDrone], TimeBucket: state[stateBucket], PolicyCommitment: state[statePolicy], MemberRoot: state[stateMemberRoot], OldNullifierRoot: state[stateOldNullifierRoot], NewNullifierRoot: state[stateNewNullifierRoot], ConsistentCount: state[stateConsistent], SuspiciousCount: state[stateSuspicious]}, nil
}
