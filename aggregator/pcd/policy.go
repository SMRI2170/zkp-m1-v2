package pcd

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"math/big"

	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/algebra/emulated/sw_bn254"
	"github.com/consensys/gnark/std/math/emulated"
)

const (
	// FinalPolicyDomainTag is the field encoding of the ASCII string
	// "UAV_FINAL_POLICY_V1". It domain-separates this hash from other Circomlib
	// Poseidon commitments used by the project.
	FinalPolicyDomainTag = "1901255031385829779341467108224662776848537137"
	FinalPolicyVersion   = 1
	FinalPolicyV2Version = 2
	// The inner commitment binds quorum to an immutable RSSI profile-set root;
	// the outer commitment domain-separates the resulting V2 policy statement.
	FinalPolicyV2ProfileDomainTag = "124600649742315774619507494999129216379624694039385"
	FinalPolicyV2DomainTag        = "1901255031385829779341467108224662776848537138"
)

// FinalVerdict follows the final-attestation-v1 public statement.
type FinalVerdict uint8

const (
	VerdictUndetermined FinalVerdict = iota
	VerdictNoInconsistencyObserved
	VerdictSpoofSuspected
)

// VerdictTrusted preserves the v1 source-level name and numeric ABI value.
// V2 uses VerdictNoInconsistencyObserved because consistency does not prove
// Remote ID authenticity, aircraft safety, or physical truth.
const VerdictTrusted = VerdictNoInconsistencyObserved

// FinalVerdictV2Label gives the V2 numeric verdict its deliberately narrow
// meaning. The numeric public-input ABI remains 0/1/2.
func FinalVerdictV2Label(verdict FinalVerdict) string {
	switch verdict {
	case VerdictUndetermined:
		return "INSUFFICIENT_EVIDENCE"
	case VerdictNoInconsistencyObserved:
		return "NO_INCONSISTENCY_OBSERVED"
	case VerdictSpoofSuspected:
		return "POSITION_INCONSISTENCY_SUSPECTED"
	default:
		return "INVALID_VERDICT"
	}
}

// Circomlib Poseidon parameters for BN254, input arity 3 (width t=4).
// These are frozen from circomlibjs' poseidon_constants.json and are generated
// by scripts/generate_circomlib_poseidon_t4_constants.js.
//
//go:embed circomlib_poseidon_t4_constants.json
var circomPoseidonT4JSON []byte

type circomPoseidonT4Parameters struct {
	Source         string     `json:"source"`
	RoundConstants []string   `json:"roundConstants"`
	MDS            [][]string `json:"mds"`
}

var circomPoseidonT4 = mustLoadCircomPoseidonT4()
var finalPolicyDomain = mustBigInt(FinalPolicyDomainTag)
var finalPolicyV2ProfileDomain = mustBigInt(FinalPolicyV2ProfileDomainTag)
var finalPolicyV2Domain = mustBigInt(FinalPolicyV2DomainTag)

var bn254Modulus = new(big.Int).Set(bn254ScalarModulus)

func validatePCDProtocolVersion(version uint32) error {
	if version != uint32(FinalPolicyVersion) && version != uint32(FinalPolicyV2Version) {
		return fmt.Errorf("unsupported PCD protocol version %d", version)
	}
	return nil
}

func mustLoadCircomPoseidonT4() circomPoseidonT4Parameters {
	var params circomPoseidonT4Parameters
	if err := json.Unmarshal(circomPoseidonT4JSON, &params); err != nil {
		panic(fmt.Errorf("decode Circomlib Poseidon parameters: %w", err))
	}
	if len(params.RoundConstants) != (8+56)*4 || len(params.MDS) != 4 {
		panic("unexpected Circomlib Poseidon t=4 parameter dimensions")
	}
	for i := range params.MDS {
		if len(params.MDS[i]) != 4 {
			panic("unexpected Circomlib Poseidon MDS width")
		}
	}
	return params
}

func mustBigInt(decimal string) *big.Int {
	v, ok := new(big.Int).SetString(decimal, 10)
	if !ok {
		panic("invalid decimal big integer in protocol parameters")
	}
	return v
}

// FinalPolicyCommitment computes the canonical v1 Poseidon commitment to the
// minimum quorum. RSSI, freshness and geometry rules are fixed by the pinned
// v1 leaf-circuit verification key; this commitment binds the configurable
// final quorum as Poseidon(domainTag, protocolVersion, minimumQuorum).
func FinalPolicyCommitment(minimumQuorum uint32) (*big.Int, error) {
	if minimumQuorum == 0 {
		return nil, fmt.Errorf("minimum quorum must be greater than zero")
	}
	return circomlibPoseidon3(
		finalPolicyDomain,
		big.NewInt(FinalPolicyVersion),
		new(big.Int).SetUint64(uint64(minimumQuorum)),
	), nil
}

// FinalPolicyCommitmentV2 commits to quorum and the root of the approved
// immutable RSSI profile set. Every leaf profile must prove membership in this
// root inside BridgeBWV2; the root then remains common across recursive merges.
func FinalPolicyCommitmentV2(minimumQuorum uint32, calibrationProfileSetRoot *big.Int) (*big.Int, error) {
	if minimumQuorum == 0 {
		return nil, fmt.Errorf("minimum quorum must be greater than zero")
	}
	if !canonicalBN254(calibrationProfileSetRoot) {
		return nil, fmt.Errorf("calibration profile set root must be a canonical BN254 scalar")
	}
	parameters := circomlibPoseidon3(
		finalPolicyV2ProfileDomain,
		new(big.Int).SetUint64(uint64(minimumQuorum)),
		calibrationProfileSetRoot,
	)
	return circomlibPoseidon3(
		finalPolicyV2Domain,
		big.NewInt(FinalPolicyV2Version),
		parameters,
	), nil
}

// finalPolicyCommitmentV2Emulated computes the same V2 commitment inside a
// circuit whose native field is not BN254 (for example BridgeBW over BW6-761).
// The caller must constrain the quorum to uint32, range-check the canonical
// BN254 profile-set root, and compare the result with the public commitment.
func finalPolicyCommitmentV2Emulated(
	api frontend.API,
	field *emulated.Field[sw_bn254.ScalarField],
	minimumQuorum frontend.Variable,
	calibrationProfileSetRoot *emulated.Element[sw_bn254.ScalarField],
) *emulated.Element[sw_bn254.ScalarField] {
	minimumQuorumElement := emulatedBN254Uint32(api, field, minimumQuorum)
	api.AssertIsDifferent(minimumQuorum, 0)
	field.AssertIsInRange(calibrationProfileSetRoot)
	parameters := circomlibPoseidon3Emulated(
		field,
		field.NewElement(finalPolicyV2ProfileDomain),
		minimumQuorumElement,
		calibrationProfileSetRoot,
	)
	return circomlibPoseidon3Emulated(
		field,
		field.NewElement(finalPolicyV2Domain),
		field.NewElement(FinalPolicyV2Version),
		parameters,
	)
}

// emulatedBN254Uint32 converts a native-field value to explicit little-endian
// limbs. Passing a BW6-native frontend.Variable directly to NewElement would
// incorrectly infer the full 377-bit native width as one BN254 limb.
func emulatedBN254Uint32(
	api frontend.API,
	field *emulated.Field[sw_bn254.ScalarField],
	value frontend.Variable,
) *emulated.Element[sw_bn254.ScalarField] {
	bits := api.ToBinary(value, 32)
	return field.NewElement([]frontend.Variable{api.FromBinary(bits...), 0, 0, 0})
}

// DeriveFinalVerdict applies the v1 quorum rule. A policy producing both a
// trusted and suspicious quorum is contradictory and cannot be finalized.
func DeriveFinalVerdict(consistentCount, suspiciousCount, minimumQuorum uint32) (FinalVerdict, error) {
	if minimumQuorum == 0 {
		return VerdictUndetermined, fmt.Errorf("minimum quorum must be greater than zero")
	}
	consistentReached := consistentCount >= minimumQuorum
	suspiciousReached := suspiciousCount >= minimumQuorum
	if consistentReached && suspiciousReached {
		return VerdictUndetermined, fmt.Errorf("conflicting verdict: both counts meet quorum")
	}
	if consistentReached {
		return VerdictNoInconsistencyObserved, nil
	}
	if suspiciousReached {
		return VerdictSpoofSuspected, nil
	}
	return VerdictUndetermined, nil
}

// FinalVerdictCircuit constrains only the policy commitment and the derived
// verdict. It is a reusable finalization gadget, not the complete FinalBN
// recursive circuit: it does not verify an aggregate proof or establish that
// the supplied counts came from valid leaves.
type FinalVerdictCircuit struct {
	PolicyCommitment frontend.Variable `gnark:",public"`
	ConsistentCount  frontend.Variable `gnark:",public"`
	SuspiciousCount  frontend.Variable `gnark:",public"`
	Verdict          frontend.Variable `gnark:",public"`
	MinimumQuorum    frontend.Variable
}

func (c *FinalVerdictCircuit) Define(api frontend.API) error {
	return constrainFinalPolicyAndVerdict(
		api,
		c.PolicyCommitment,
		c.ConsistentCount,
		c.SuspiciousCount,
		c.Verdict,
		c.MinimumQuorum,
	)
}

// FinalVerdictV2Circuit binds the final quorum decision to both the V2
// protocol domain and the approved RSSI calibration profile-set root. It is a
// finalization gadget only; it does not verify a recursive aggregate proof.
type FinalVerdictV2Circuit struct {
	ProtocolVersion           frontend.Variable `gnark:",public"`
	PolicyCommitment          frontend.Variable `gnark:",public"`
	ConsistentCount           frontend.Variable `gnark:",public"`
	SuspiciousCount           frontend.Variable `gnark:",public"`
	Verdict                   frontend.Variable `gnark:",public"`
	MinimumQuorum             frontend.Variable
	CalibrationProfileSetRoot frontend.Variable
}

func (c *FinalVerdictV2Circuit) Define(api frontend.API) error {
	api.AssertIsEqual(c.ProtocolVersion, FinalPolicyV2Version)
	if err := constrainFinalPolicyV2(api, c.PolicyCommitment, c.MinimumQuorum, c.CalibrationProfileSetRoot); err != nil {
		return err
	}
	return constrainFinalQuorumVerdict(api, c.ConsistentCount, c.SuspiciousCount, c.Verdict, c.MinimumQuorum)
}

func constrainFinalPolicyV2(api frontend.API, policyCommitment, minimumQuorum, calibrationProfileSetRoot frontend.Variable) error {
	api.ToBinary(minimumQuorum, 32)
	api.AssertIsDifferent(minimumQuorum, 0)
	parameters := circomlibPoseidon3Circuit(
		api,
		FinalPolicyV2ProfileDomainTag,
		minimumQuorum,
		calibrationProfileSetRoot,
	)
	commitment := circomlibPoseidon3Circuit(
		api,
		FinalPolicyV2DomainTag,
		FinalPolicyV2Version,
		parameters,
	)
	api.AssertIsEqual(policyCommitment, commitment)
	return nil
}

func constrainFinalPolicyAndVerdict(
	api frontend.API,
	policyCommitment, consistentCount, suspiciousCount, verdict, minimumQuorum frontend.Variable,
) error {
	commitment := circomlibPoseidon3Circuit(api, FinalPolicyDomainTag, FinalPolicyVersion, minimumQuorum)
	api.AssertIsEqual(policyCommitment, commitment)
	return constrainFinalQuorumVerdict(api, consistentCount, suspiciousCount, verdict, minimumQuorum)
}

func constrainFinalQuorumVerdict(api frontend.API, consistentCount, suspiciousCount, verdict, minimumQuorum frontend.Variable) error {
	api.ToBinary(minimumQuorum, 32)
	api.AssertIsDifferent(minimumQuorum, 0)
	api.ToBinary(consistentCount, 32)
	api.ToBinary(suspiciousCount, 32)

	// Cmp returns 1 only if quorum > count; otherwise the quorum is reached.
	consistentCmp := api.Cmp(minimumQuorum, consistentCount)
	suspiciousCmp := api.Cmp(minimumQuorum, suspiciousCount)
	consistentReached := api.Sub(1, api.IsZero(api.Sub(consistentCmp, 1)))
	suspiciousReached := api.Sub(1, api.IsZero(api.Sub(suspiciousCmp, 1)))
	api.AssertIsEqual(api.Mul(consistentReached, suspiciousReached), 0)
	expectedVerdict := api.Add(consistentReached, api.Mul(2, suspiciousReached))
	api.AssertIsEqual(verdict, expectedVerdict)
	return nil
}

func circomlibPoseidon3(inputs ...*big.Int) *big.Int {
	if len(inputs) != 3 {
		panic("Circomlib Poseidon3 requires exactly three inputs")
	}
	state := []*big.Int{big.NewInt(0), new(big.Int).Set(inputs[0]), new(big.Int).Set(inputs[1]), new(big.Int).Set(inputs[2])}
	for round := 0; round < 64; round++ {
		for i := range state {
			state[i] = modAdd(state[i], mustBigInt(circomPoseidonT4.RoundConstants[round*4+i]))
		}
		fullRound := round < 4 || round >= 60
		for i := range state {
			if fullRound || i == 0 {
				state[i] = pow5(state[i])
			}
		}
		next := make([]*big.Int, 4)
		for i := range next {
			next[i] = new(big.Int)
			for j := range state {
				next[i].Add(next[i], new(big.Int).Mul(mustBigInt(circomPoseidonT4.MDS[i][j]), state[j]))
			}
			next[i].Mod(next[i], bn254Modulus)
		}
		state = next
	}
	return state[0]
}

func circomlibPoseidon3Circuit(api frontend.API, in0, in1, in2 frontend.Variable) frontend.Variable {
	state := []frontend.Variable{0, in0, in1, in2}
	for round := 0; round < 64; round++ {
		for i := range state {
			state[i] = api.Add(state[i], mustBigInt(circomPoseidonT4.RoundConstants[round*4+i]))
		}
		fullRound := round < 4 || round >= 60
		for i := range state {
			if fullRound || i == 0 {
				x2 := api.Mul(state[i], state[i])
				x4 := api.Mul(x2, x2)
				state[i] = api.Mul(x4, state[i])
			}
		}
		next := make([]frontend.Variable, 4)
		for i := range next {
			terms := make([]frontend.Variable, 4)
			for j := range state {
				terms[j] = api.Mul(mustBigInt(circomPoseidonT4.MDS[i][j]), state[j])
			}
			next[i] = api.Add(terms[0], terms[1], terms[2], terms[3])
		}
		state = next
	}
	return state[0]
}

func circomlibPoseidon3Emulated(
	field *emulated.Field[sw_bn254.ScalarField],
	in0, in1, in2 *emulated.Element[sw_bn254.ScalarField],
) *emulated.Element[sw_bn254.ScalarField] {
	state := []*emulated.Element[sw_bn254.ScalarField]{field.Zero(), in0, in1, in2}
	for round := 0; round < 64; round++ {
		for i := range state {
			state[i] = field.Add(state[i], field.NewElement(mustBigInt(circomPoseidonT4.RoundConstants[round*4+i])))
		}
		fullRound := round < 4 || round >= 60
		for i := range state {
			if fullRound || i == 0 {
				x2 := field.Mul(state[i], state[i])
				x4 := field.Mul(x2, x2)
				state[i] = field.Mul(x4, state[i])
			}
		}
		next := make([]*emulated.Element[sw_bn254.ScalarField], len(state))
		for i := range next {
			terms := make([]*emulated.Element[sw_bn254.ScalarField], len(state))
			for j := range state {
				terms[j] = field.Mul(field.NewElement(mustBigInt(circomPoseidonT4.MDS[i][j])), state[j])
			}
			next[i] = terms[0]
			for j := 1; j < len(terms); j++ {
				next[i] = field.Add(next[i], terms[j])
			}
		}
		state = next
	}
	return state[0]
}

func modAdd(a, b *big.Int) *big.Int {
	return new(big.Int).Mod(new(big.Int).Add(a, b), bn254Modulus)
}

func pow5(x *big.Int) *big.Int {
	x2 := new(big.Int).Mul(x, x)
	x4 := new(big.Int).Mul(x2, x2)
	return new(big.Int).Mod(new(big.Int).Mul(x4, x), bn254Modulus)
}
