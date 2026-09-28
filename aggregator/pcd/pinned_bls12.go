package pcd

import (
	"fmt"

	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/constraint"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/algebra/native/sw_bls12377"
	stdgroth16 "github.com/consensys/gnark/std/recursion/groth16"
)

// PinnedBLS12ProofCircuit verifies a BLS12-377 proof in BW6-761 while keeping
// the child verification key as circuit constants.  The key is deliberately
// unexported and marked gnark:"-": it is selected when the parent circuit is
// compiled, not supplied by the prover as a witness.
//
// This is the fixed-key primitive used by BridgeBW and by the NodeBW side of
// the planned BLS12-377/BW6-761 PCD cycle.  A proof made under any other key
// cannot satisfy this circuit, even if it has the same public-input layout.
type PinnedBLS12ProofCircuit struct {
	Proof        stdgroth16.Proof[sw_bls12377.G1Affine, sw_bls12377.G2Affine]
	InnerWitness stdgroth16.Witness[sw_bls12377.ScalarField]

	verifyingKey stdgroth16.VerifyingKey[sw_bls12377.G1Affine, sw_bls12377.G2Affine, sw_bls12377.GT] `gnark:"-"`
}

// NewPinnedBLS12ProofCircuit creates the circuit template for a known child
// circuit and release-pinned verification key.  The caller must persist the
// key's release digest alongside the resulting parent proving/verifying keys.
func NewPinnedBLS12ProofCircuit(childCCS constraint.ConstraintSystem, childVK groth16.VerifyingKey) (*PinnedBLS12ProofCircuit, error) {
	vk, err := stdgroth16.ValueOfVerifyingKeyFixed[
		sw_bls12377.G1Affine, sw_bls12377.G2Affine, sw_bls12377.GT,
	](childVK)
	if err != nil {
		return nil, fmt.Errorf("pin BLS12-377 verification key: %w", err)
	}
	return &PinnedBLS12ProofCircuit{
		Proof:        stdgroth16.PlaceholderProof[sw_bls12377.G1Affine, sw_bls12377.G2Affine](childCCS),
		InnerWitness: stdgroth16.PlaceholderWitness[sw_bls12377.ScalarField](childCCS),
		verifyingKey: vk,
	}, nil
}

// PinnedBLS12ProofAssignment translates a native child proof and its public
// witness into the private witness accepted by PinnedBLS12ProofCircuit.
func PinnedBLS12ProofAssignment(childProof groth16.Proof, childPublic witness.Witness) (*PinnedBLS12ProofCircuit, error) {
	proof, err := stdgroth16.ValueOfProof[sw_bls12377.G1Affine, sw_bls12377.G2Affine](childProof)
	if err != nil {
		return nil, fmt.Errorf("translate BLS12-377 proof: %w", err)
	}
	public, err := stdgroth16.ValueOfWitness[sw_bls12377.ScalarField](childPublic)
	if err != nil {
		return nil, fmt.Errorf("translate BLS12-377 public witness: %w", err)
	}
	return &PinnedBLS12ProofCircuit{Proof: proof, InnerWitness: public}, nil
}

func (c *PinnedBLS12ProofCircuit) Define(api frontend.API) error {
	verifier, err := stdgroth16.NewVerifier[
		sw_bls12377.ScalarField, sw_bls12377.G1Affine, sw_bls12377.G2Affine, sw_bls12377.GT,
	](api)
	if err != nil {
		return fmt.Errorf("new pinned BLS12-377 verifier: %w", err)
	}
	return verifier.AssertProof(c.verifyingKey, c.Proof, c.InnerWitness)
}
