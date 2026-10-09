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

	"uav/aggregator/membership"
)

const publicInputCountV1 = 9

// FinalBN verifies one fixed-key BW6-761 recursive root proof in a BN254
// circuit, emits the exact final-attestation-v1 public-input order, checks that
// the nullifier chain starts from an empty session tree, and derives the
// quorum verdict. Its security depends on rootVK being the released NodeBW
// verification key for a complete production PCD family.
type FinalBN struct {
	// Keep these first and in protocol order: they are the only public inputs.
	ProtocolVersion  frontend.Variable `gnark:",public"`
	DroneID          frontend.Variable `gnark:",public"`
	TimeBucket       frontend.Variable `gnark:",public"`
	PolicyCommitment frontend.Variable `gnark:",public"`
	MemberRoot       frontend.Variable `gnark:",public"`
	NullifierRoot    frontend.Variable `gnark:",public"`
	ConsistentCount  frontend.Variable `gnark:",public"`
	SuspiciousCount  frontend.Variable `gnark:",public"`
	Verdict          frontend.Variable `gnark:",public"`

	MinimumQuorum frontend.Variable
	RootProof     stdgroth16.Proof[sw_bw6761.G1Affine, sw_bw6761.G2Affine]
	RootState     stdgroth16.Witness[sw_bw6761.ScalarField]

	verifyingKey stdgroth16.VerifyingKey[sw_bw6761.G1Affine, sw_bw6761.G2Affine, sw_bw6761.GTEl] `gnark:"-"`
}

// NewFinalBN pins the BW6-761 root key into the BN254 finalizer. The root
// circuit must expose the nine-field OrderedState documented in node_bw.go.
func NewFinalBN(rootCCS constraint.ConstraintSystem, rootVK groth16.VerifyingKey) (*FinalBN, error) {
	if rootCCS == nil || rootCCS.GetNbPublicVariables()-1 != stateWidth {
		got := 0
		if rootCCS != nil {
			got = rootCCS.GetNbPublicVariables() - 1
		}
		return nil, fmt.Errorf("FinalBN requires a %d-value BW6 root state, got %d", stateWidth, got)
	}
	if rootVK == nil || rootVK.NbPublicWitness() != stateWidth {
		got := 0
		if rootVK != nil {
			got = rootVK.NbPublicWitness()
		}
		return nil, fmt.Errorf("FinalBN requires a BW6 root key with %d public values, got %d", stateWidth, got)
	}
	vk, err := stdgroth16.ValueOfVerifyingKeyFixed[
		sw_bw6761.G1Affine, sw_bw6761.G2Affine, sw_bw6761.GTEl,
	](rootVK)
	if err != nil {
		return nil, fmt.Errorf("pin FinalBN BW6 root key: %w", err)
	}
	return &FinalBN{
		RootProof:    stdgroth16.PlaceholderProof[sw_bw6761.G1Affine, sw_bw6761.G2Affine](rootCCS),
		RootState:    stdgroth16.PlaceholderWitness[sw_bw6761.ScalarField](rootCCS),
		verifyingKey: vk,
	}, nil
}

func (c *FinalBN) Define(api frontend.API) error {
	verifier, err := stdgroth16.NewVerifier[
		sw_bw6761.ScalarField, sw_bw6761.G1Affine, sw_bw6761.G2Affine, sw_bw6761.GTEl,
	](api)
	if err != nil {
		return fmt.Errorf("construct FinalBN BW6 verifier: %w", err)
	}
	if err := verifier.AssertProof(c.verifyingKey, c.RootProof, c.RootState); err != nil {
		return fmt.Errorf("verify FinalBN root proof: %w", err)
	}
	if len(c.RootState.Public) != stateWidth {
		return fmt.Errorf("FinalBN root state must have %d values, got %d", stateWidth, len(c.RootState.Public))
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
		return fmt.Errorf("canonicalize FinalBN root state: %w", err)
	}
	var nodeState [stateWidth]frontend.Variable
	for i := range canonicalState {
		nodeState[i] = packBN254Element(api, bnField, canonicalState[i])
	}

	api.AssertIsEqual(c.ProtocolVersion, 1)
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
	api.AssertIsDifferent(api.Add(c.ConsistentCount, c.SuspiciousCount), 0)
	return constrainFinalPolicyAndVerdict(
		api,
		c.PolicyCommitment,
		c.ConsistentCount,
		c.SuspiciousCount,
		c.Verdict,
		c.MinimumQuorum,
	)
}

// FinalBNAssignment converts a native BW6-761 root proof and its public state
// into the private witness of FinalBN. state is the public v1 ABI vector in
// protocol order; invalid or noncanonical values are rejected early, then are
// independently constrained by the circuit.
func FinalBNAssignment(
	rootProof groth16.Proof,
	rootPublic witness.Witness,
	state [publicInputCountV1]*big.Int,
	minimumQuorum uint32,
) (*FinalBN, error) {
	for i, value := range state {
		if value == nil || value.Sign() < 0 || value.Cmp(bn254ScalarModulus) >= 0 {
			return nil, fmt.Errorf("final public input[%d] is not a canonical BN254 scalar", i)
		}
	}
	if state[0].Cmp(big.NewInt(FinalPolicyVersion)) != 0 {
		return nil, fmt.Errorf("final protocolVersion must be %d", FinalPolicyVersion)
	}
	if state[2].BitLen() > 64 {
		return nil, fmt.Errorf("timeBucket is outside uint64 range")
	}
	if !state[6].IsUint64() || state[6].BitLen() > 32 || !state[7].IsUint64() || state[7].BitLen() > 32 {
		return nil, fmt.Errorf("final counts are outside uint32 range")
	}
	policy, err := FinalPolicyCommitment(minimumQuorum)
	if err != nil {
		return nil, err
	}
	if state[3].Cmp(policy) != 0 {
		return nil, fmt.Errorf("policyCommitment does not commit to minimum quorum %d", minimumQuorum)
	}
	verdict, err := DeriveFinalVerdict(uint32(state[6].Uint64()), uint32(state[7].Uint64()), minimumQuorum)
	if err != nil {
		return nil, err
	}
	if state[8].Cmp(new(big.Int).SetUint64(uint64(verdict))) != 0 {
		return nil, fmt.Errorf("verdict does not match counts and minimum quorum")
	}
	if new(big.Int).Add(state[6], state[7]).Sign() == 0 {
		return nil, fmt.Errorf("empty final aggregate")
	}

	proof, err := stdgroth16.ValueOfProof[sw_bw6761.G1Affine, sw_bw6761.G2Affine](rootProof)
	if err != nil {
		return nil, fmt.Errorf("translate BW6 root proof: %w", err)
	}
	public, err := stdgroth16.ValueOfWitness[sw_bw6761.ScalarField](rootPublic)
	if err != nil {
		return nil, fmt.Errorf("translate BW6 root public state: %w", err)
	}
	assignment := &FinalBN{
		ProtocolVersion:  state[0],
		DroneID:          state[1],
		TimeBucket:       state[2],
		PolicyCommitment: state[3],
		MemberRoot:       state[4],
		NullifierRoot:    state[5],
		ConsistentCount:  state[6],
		SuspiciousCount:  state[7],
		Verdict:          state[8],
		MinimumQuorum:    minimumQuorum,
		RootProof:        proof,
		RootState:        public,
	}
	return assignment, nil
}

func packBN254Element(api frontend.API, field *emulated.Field[sw_bn254.ScalarField], value *emulated.Element[sw_bn254.ScalarField]) frontend.Variable {
	canonical := field.ReduceStrict(value)
	acc := frontend.Variable(0)
	coefficient := big.NewInt(1)
	for _, limb := range canonical.Limbs {
		acc = api.Add(acc, api.Mul(limb, new(big.Int).Set(coefficient)))
		coefficient.Lsh(coefficient, 64)
	}
	return acc
}

func emptyNullifierRoot() *big.Int {
	root := big.NewInt(0)
	for range membership.Depth {
		root = membership.MimcHash(root, root)
	}
	return root
}
