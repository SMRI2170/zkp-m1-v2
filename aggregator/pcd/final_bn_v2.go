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

const publicInputCountV2 = 10

// FinalBNV2 verifies one fixed-key BW6-761 recursive root proof in a BN254
// circuit. Its 10-field public ABI includes the approved RSSI profile-set root;
// the policy commitment binds that root and quorum. Keep V1's ABI unchanged.
type FinalBNV2 struct {
	ProtocolVersion           frontend.Variable `gnark:",public"`
	DroneID                   frontend.Variable `gnark:",public"`
	TimeBucket                frontend.Variable `gnark:",public"`
	PolicyCommitment          frontend.Variable `gnark:",public"`
	CalibrationProfileSetRoot frontend.Variable `gnark:",public"`
	MemberRoot                frontend.Variable `gnark:",public"`
	NullifierRoot             frontend.Variable `gnark:",public"`
	ConsistentCount           frontend.Variable `gnark:",public"`
	SuspiciousCount           frontend.Variable `gnark:",public"`
	Verdict                   frontend.Variable `gnark:",public"`

	MinimumQuorum frontend.Variable
	RootProof     stdgroth16.Proof[sw_bw6761.G1Affine, sw_bw6761.G2Affine]
	RootState     stdgroth16.Witness[sw_bw6761.ScalarField]

	verifyingKey stdgroth16.VerifyingKey[sw_bw6761.G1Affine, sw_bw6761.G2Affine, sw_bw6761.GTEl] `gnark:"-"`
}

// NewFinalBNV2 pins the BW6 root key into the V2 finalizer. V2 uses a separate
// final circuit and public-input order; a V1 root cannot satisfy it.
func NewFinalBNV2(rootCCS constraint.ConstraintSystem, rootVK groth16.VerifyingKey) (*FinalBNV2, error) {
	if rootCCS == nil || rootCCS.GetNbPublicVariables()-1 != stateWidth {
		got := 0
		if rootCCS != nil {
			got = rootCCS.GetNbPublicVariables() - 1
		}
		return nil, fmt.Errorf("FinalBNV2 requires a %d-value BW6 root state, got %d", stateWidth, got)
	}
	if rootVK == nil || rootVK.NbPublicWitness() != stateWidth {
		got := 0
		if rootVK != nil {
			got = rootVK.NbPublicWitness()
		}
		return nil, fmt.Errorf("FinalBNV2 requires a BW6 root key with %d public values, got %d", stateWidth, got)
	}
	vk, err := stdgroth16.ValueOfVerifyingKeyFixed[
		sw_bw6761.G1Affine, sw_bw6761.G2Affine, sw_bw6761.GTEl,
	](rootVK)
	if err != nil {
		return nil, fmt.Errorf("pin FinalBNV2 BW6 root key: %w", err)
	}
	return &FinalBNV2{
		RootProof:    stdgroth16.PlaceholderProof[sw_bw6761.G1Affine, sw_bw6761.G2Affine](rootCCS),
		RootState:    stdgroth16.PlaceholderWitness[sw_bw6761.ScalarField](rootCCS),
		verifyingKey: vk,
	}, nil
}

func (c *FinalBNV2) Define(api frontend.API) error {
	verifier, err := stdgroth16.NewVerifier[
		sw_bw6761.ScalarField, sw_bw6761.G1Affine, sw_bw6761.G2Affine, sw_bw6761.GTEl,
	](api)
	if err != nil {
		return fmt.Errorf("construct FinalBNV2 BW6 verifier: %w", err)
	}
	if err := verifier.AssertProof(c.verifyingKey, c.RootProof, c.RootState); err != nil {
		return fmt.Errorf("verify FinalBNV2 root proof: %w", err)
	}
	if len(c.RootState.Public) != stateWidth {
		return fmt.Errorf("FinalBNV2 root state must have %d values, got %d", stateWidth, len(c.RootState.Public))
	}

	var bwState [stateWidth]emulated.Element[sw_bw6761.ScalarField]
	copy(bwState[:], c.RootState.Public)
	bwField, err := emulated.NewField[sw_bw6761.ScalarField](api)
	if err != nil {
		return err
	}
	bnField, err := emulated.NewField[sw_bn254.ScalarField](api)
	if err != nil {
		return err
	}
	canonicalState, err := BWStateToBN254(api, bwField, bnField, bwState)
	if err != nil {
		return fmt.Errorf("canonicalize FinalBNV2 root state: %w", err)
	}
	var nodeState [stateWidth]frontend.Variable
	for i := range canonicalState {
		nodeState[i] = packBN254Element(api, bnField, canonicalState[i])
	}

	api.AssertIsEqual(c.ProtocolVersion, FinalPolicyV2Version)
	api.AssertIsEqual(c.ProtocolVersion, nodeState[stateVersion])
	api.AssertIsEqual(c.DroneID, nodeState[stateDrone])
	api.AssertIsEqual(c.TimeBucket, nodeState[stateBucket])
	api.AssertIsEqual(c.PolicyCommitment, nodeState[statePolicy])
	api.AssertIsEqual(c.MemberRoot, nodeState[stateMemberRoot])
	api.AssertIsEqual(nodeState[stateOldNullifierRoot], emptyNullifierRoot())
	api.AssertIsEqual(c.NullifierRoot, nodeState[stateNewNullifierRoot])
	api.AssertIsEqual(c.ConsistentCount, nodeState[stateConsistent])
	api.AssertIsEqual(c.SuspiciousCount, nodeState[stateSuspicious])

	api.ToBinary(c.TimeBucket, 64)
	api.ToBinary(c.ConsistentCount, 32)
	api.ToBinary(c.SuspiciousCount, 32)
	api.AssertIsDifferent(api.Add(c.ConsistentCount, c.SuspiciousCount), 0)
	if err := constrainFinalPolicyV2(api, c.PolicyCommitment, c.MinimumQuorum, c.CalibrationProfileSetRoot); err != nil {
		return err
	}
	return constrainFinalQuorumVerdict(api, c.ConsistentCount, c.SuspiciousCount, c.Verdict, c.MinimumQuorum)
}

// FinalBNV2Assignment validates the public V2 ABI before constructing the
// private recursive witness. The circuit independently repeats every check.
func FinalBNV2Assignment(
	rootProof groth16.Proof,
	rootPublic witness.Witness,
	state [publicInputCountV2]*big.Int,
	minimumQuorum uint32,
) (*FinalBNV2, error) {
	for i, value := range state {
		if value == nil || value.Sign() < 0 || value.Cmp(bn254ScalarModulus) >= 0 {
			return nil, fmt.Errorf("final V2 public input[%d] is not a canonical BN254 scalar", i)
		}
	}
	if state[0].Cmp(big.NewInt(FinalPolicyV2Version)) != 0 {
		return nil, fmt.Errorf("final V2 protocolVersion must be %d", FinalPolicyV2Version)
	}
	if state[2].BitLen() > 64 {
		return nil, fmt.Errorf("final V2 time bucket is out of range")
	}
	if !state[7].IsUint64() || state[7].BitLen() > 32 || !state[8].IsUint64() || state[8].BitLen() > 32 {
		return nil, fmt.Errorf("final V2 counts are outside uint32 range")
	}
	policy, err := FinalPolicyCommitmentV2(minimumQuorum, state[4])
	if err != nil {
		return nil, err
	}
	if state[3].Cmp(policy) != 0 {
		return nil, fmt.Errorf("V2 policyCommitment does not bind quorum %d and profile set root %s", minimumQuorum, state[4])
	}
	verdict, err := DeriveFinalVerdict(uint32(state[7].Uint64()), uint32(state[8].Uint64()), minimumQuorum)
	if err != nil {
		return nil, err
	}
	if state[9].Cmp(new(big.Int).SetUint64(uint64(verdict))) != 0 {
		return nil, fmt.Errorf("final V2 verdict does not match counts and minimum quorum")
	}
	if new(big.Int).Add(state[7], state[8]).Sign() == 0 {
		return nil, fmt.Errorf("empty final V2 aggregate")
	}
	proof, err := stdgroth16.ValueOfProof[sw_bw6761.G1Affine, sw_bw6761.G2Affine](rootProof)
	if err != nil {
		return nil, fmt.Errorf("translate BW6 V2 root proof: %w", err)
	}
	public, err := stdgroth16.ValueOfWitness[sw_bw6761.ScalarField](rootPublic)
	if err != nil {
		return nil, fmt.Errorf("translate BW6 V2 root public state: %w", err)
	}
	return &FinalBNV2{
		ProtocolVersion: state[0], DroneID: state[1], TimeBucket: state[2],
		PolicyCommitment: state[3], CalibrationProfileSetRoot: state[4],
		MemberRoot: state[5], NullifierRoot: state[6],
		ConsistentCount: state[7], SuspiciousCount: state[8], Verdict: state[9],
		MinimumQuorum: minimumQuorum, RootProof: proof, RootState: public,
	}, nil
}
