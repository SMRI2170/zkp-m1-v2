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
)

// PromoteBLS verifies one BridgeBW proof and re-encodes its state into the
// standard 36-limb BLS statement. It is the real one-observer branch used to
// balance a three-observer tree; it is not an unchecked empty/dummy proof.
type PromoteBLS struct {
	Proof stdgroth16.Proof[sw_bw6761.G1Affine, sw_bw6761.G2Affine]
	State stdgroth16.Witness[sw_bw6761.ScalarField]

	verifyingKey    stdgroth16.VerifyingKey[sw_bw6761.G1Affine, sw_bw6761.G2Affine, sw_bw6761.GTEl] `gnark:"-"`
	protocolVersion uint32                                                                          `gnark:"-"`

	Output [encodedStateWidth]frontend.Variable `gnark:",public"`
}

func NewPromoteBLS(bridgeCCS constraint.ConstraintSystem, bridgeVK groth16.VerifyingKey) (*PromoteBLS, error) {
	return NewPromoteBLSForProtocol(bridgeCCS, bridgeVK, uint32(FinalPolicyVersion))
}

// NewPromoteBLSForProtocol pins a single-child promotion circuit to the same
// versioned bridge family as its siblings.
func NewPromoteBLSForProtocol(bridgeCCS constraint.ConstraintSystem, bridgeVK groth16.VerifyingKey, protocolVersion uint32) (*PromoteBLS, error) {
	if err := validatePCDProtocolVersion(protocolVersion); err != nil {
		return nil, err
	}
	if bridgeCCS == nil || bridgeCCS.GetNbPublicVariables()-1 != stateWidth {
		got := 0
		if bridgeCCS != nil {
			got = bridgeCCS.GetNbPublicVariables() - 1
		}
		return nil, fmt.Errorf("PromoteBLS requires a BridgeBW CCS with %d state values, got %d", stateWidth, got)
	}
	vk, err := stdgroth16.ValueOfVerifyingKeyFixed[
		sw_bw6761.G1Affine, sw_bw6761.G2Affine, sw_bw6761.GTEl,
	](bridgeVK)
	if err != nil {
		return nil, fmt.Errorf("pin PromoteBLS bridge key: %w", err)
	}
	return &PromoteBLS{
		Proof:           stdgroth16.PlaceholderProof[sw_bw6761.G1Affine, sw_bw6761.G2Affine](bridgeCCS),
		State:           stdgroth16.PlaceholderWitness[sw_bw6761.ScalarField](bridgeCCS),
		verifyingKey:    vk,
		protocolVersion: protocolVersion,
	}, nil
}

func PromoteBLSAssignment(proof groth16.Proof, public witness.Witness, state [stateWidth]*big.Int) (*PromoteBLS, error) {
	return PromoteBLSAssignmentForProtocol(proof, public, state, uint32(FinalPolicyVersion))
}

// PromoteBLSAssignmentForProtocol validates and encodes one V1 or V2 leaf
// bridge state for an asymmetric tree branch.
func PromoteBLSAssignmentForProtocol(proof groth16.Proof, public witness.Witness, state [stateWidth]*big.Int, protocolVersion uint32) (*PromoteBLS, error) {
	if err := validatePCDProtocolVersion(protocolVersion); err != nil {
		return nil, err
	}
	if err := validateSingleObserverStateForProtocol(state, protocolVersion); err != nil {
		return nil, err
	}
	encoded, err := EncodeState(state)
	if err != nil {
		return nil, err
	}
	innerProof, err := stdgroth16.ValueOfProof[sw_bw6761.G1Affine, sw_bw6761.G2Affine](proof)
	if err != nil {
		return nil, fmt.Errorf("translate PromoteBLS child proof: %w", err)
	}
	innerState, err := stdgroth16.ValueOfWitness[sw_bw6761.ScalarField](public)
	if err != nil {
		return nil, fmt.Errorf("translate PromoteBLS child state: %w", err)
	}
	if len(innerState.Public) != stateWidth {
		return nil, fmt.Errorf("PromoteBLS child state must expose %d values, got %d", stateWidth, len(innerState.Public))
	}
	assignment := &PromoteBLS{Proof: innerProof, State: innerState, protocolVersion: protocolVersion}
	for i := range encoded {
		assignment.Output[i] = encoded[i]
	}
	return assignment, nil
}

func (c *PromoteBLS) Define(api frontend.API) error {
	verifier, err := stdgroth16.NewVerifier[
		sw_bw6761.ScalarField, sw_bw6761.G1Affine, sw_bw6761.G2Affine, sw_bw6761.GTEl,
	](api)
	if err != nil {
		return fmt.Errorf("construct PromoteBLS verifier: %w", err)
	}
	if err := verifier.AssertProof(c.verifyingKey, c.Proof, c.State); err != nil {
		return fmt.Errorf("verify PromoteBLS BridgeBW proof: %w", err)
	}
	if len(c.State.Public) != stateWidth {
		return fmt.Errorf("PromoteBLS BridgeBW state must expose %d values, got %d", stateWidth, len(c.State.Public))
	}
	bwField, err := emulated.NewField[sw_bw6761.ScalarField](api)
	if err != nil {
		return err
	}
	bnField, err := emulated.NewField[sw_bn254.ScalarField](api)
	if err != nil {
		return err
	}
	var bwState [stateWidth]emulated.Element[sw_bw6761.ScalarField]
	copy(bwState[:], c.State.Public)
	state, err := BWStateToBN254(api, bwField, bnField, bwState)
	if err != nil {
		return fmt.Errorf("decode PromoteBLS BridgeBW state: %w", err)
	}
	api.AssertIsEqual(packBN254Element(api, bnField, state[stateVersion]), c.protocolVersion)
	bnField.AssertIsEqual(state[stateOldNullifierRoot], bnField.NewElement(emptyNullifierRoot()))
	assertEmulatedFieldBits(api, bnField, state[stateBucket], 64)
	assertEmulatedFieldBits(api, bnField, state[stateConsistent], 32)
	assertEmulatedFieldBits(api, bnField, state[stateSuspicious], 32)
	count := api.Add(
		packBN254Element(api, bnField, state[stateConsistent]),
		packBN254Element(api, bnField, state[stateSuspicious]),
	)
	api.AssertIsEqual(count, 1)
	encoded, err := BN254StateToBLSLimbs(bnField, state)
	if err != nil {
		return err
	}
	for i := range encoded {
		api.AssertIsEqual(c.Output[i], encoded[i])
	}
	return nil
}

func validateSingleObserverState(state [stateWidth]*big.Int) error {
	return validateSingleObserverStateForProtocol(state, uint32(FinalPolicyVersion))
}

func validateSingleObserverStateForProtocol(state [stateWidth]*big.Int, protocolVersion uint32) error {
	if err := validatePCDProtocolVersion(protocolVersion); err != nil {
		return err
	}
	for i, value := range state {
		if value == nil || value.Sign() < 0 || value.Cmp(bn254ScalarModulus) >= 0 {
			return fmt.Errorf("single observer state[%d] is not a canonical BN254 scalar", i)
		}
	}
	if state[stateVersion].Cmp(new(big.Int).SetUint64(uint64(protocolVersion))) != 0 {
		return fmt.Errorf("single observer protocolVersion must be %d", protocolVersion)
	}
	if state[stateBucket].BitLen() > 64 || state[stateConsistent].BitLen() > 32 || state[stateSuspicious].BitLen() > 32 {
		return fmt.Errorf("single observer state time/count range is invalid")
	}
	if state[stateConsistent].Uint64()+state[stateSuspicious].Uint64() != 1 {
		return fmt.Errorf("single observer state counts must total one")
	}
	return nil
}
