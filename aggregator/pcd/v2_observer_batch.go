package pcd

import (
	"fmt"
	"math/big"

	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"

	"uav/aggregator/membership"
	"uav/aggregator/nullifier"
)

const (
	leafPublicSignalCountV2    = 8
	leafObservationEligibleV2  = 0
	leafDroneIDV2              = 1
	leafObserverPublicKeyXV2   = 2
	leafObserverPublicKeyYV2   = 3
	leafTimeBucketV2           = 4
	leafConsistencyOKV2        = 5
	leafFreshnessV2            = 6
	leafCalibrationProfileIDV2 = 7
	leafTimeBucketSecondsV2    = 60
)

// VerifiedObserverBatchV2 is a host-side, cryptographically verified summary
// of V2 leaves. It is deliberately not a recursive PCD proof or final
// attestation; version-pinned recursive V2 circuit templates exist, but this
// verification/preflight type does not generate their proofs.
type VerifiedObserverBatchV2 struct {
	DroneIDCommitment          *big.Int
	TimeBucket                 *big.Int
	CalibrationProfileSetRoot  *big.Int
	AllowedCalibrationProfiles []*big.Int
	PolicyCommitment           *big.Int
	MemberRoot                 *big.Int
	ObserverCount              uint32
	ConsistentCount            uint32
	SuspiciousCount            uint32
	MinimumQuorum              uint32
	ProvisionalVerdict         FinalVerdict
	verifiedLeaves             []verifiedV2Observation
}

type verifiedV2Observation struct {
	Proof       groth16.Proof
	Public      witness.Witness
	Signals     []*big.Int
	MemberIndex int
	ProfilePath calibrationProfilePathV2
}

// VerifyV2ObserverBatch verifies each V2 Groth16 leaf against the caller's
// separately pinned V2 verification key, checks registration against the
// externally supplied active roster root, and enforces one RID commitment and
// time bucket. The commitment groups equal
// claimed broadcast IDs only; it is not proof of physical-aircraft identity or
// Remote ID authenticity. Each observer may use a different profile when every profile is
// included in the same policy-committed allowlist root.
//
// This is only a verification/preflight boundary. It does not create nullifier
// paths, a recursive PCD, or a final proof. The V2 circuit has no
// drone-authentication output; RID trust-chain validation remains a separate,
// currently unimplemented boundary.
func VerifyV2ObserverBatch(
	leafVK groth16.VerifyingKey,
	observations []LeafObservation,
	registered []DeviceCredential,
	activeMemberRoot *big.Int,
	allowedCalibrationProfileIDs []*big.Int,
	minimumQuorum uint32,
) (*VerifiedObserverBatchV2, error) {
	if !canonicalBN254(activeMemberRoot) {
		return nil, fmt.Errorf("active member root must be a canonical BN254 scalar")
	}
	if leafVK == nil || leafVK.NbPublicWitness() != leafPublicSignalCountV2 {
		got := 0
		if leafVK != nil {
			got = leafVK.NbPublicWitness()
		}
		return nil, fmt.Errorf("V2 observer batch requires a pinned leaf VK with %d public signals, got %d", leafPublicSignalCountV2, got)
	}
	if len(observations) < 2 {
		return nil, fmt.Errorf("V2 observer batch requires at least two independent observations")
	}
	if len(observations) > nullifier.TreeSize {
		return nil, fmt.Errorf("V2 observer batch has %d observations; registry capacity is %d", len(observations), nullifier.TreeSize)
	}
	if len(registered) == 0 || len(registered) > nullifier.TreeSize {
		return nil, fmt.Errorf("registered roster size must be between 1 and %d", nullifier.TreeSize)
	}
	if minimumQuorum == 0 {
		return nil, fmt.Errorf("minimum quorum must be greater than zero")
	}
	canonicalProfiles, err := canonicalCalibrationProfileIDsV2(allowedCalibrationProfileIDs)
	if err != nil {
		return nil, err
	}
	profileSetRoot, profilePaths, err := buildCalibrationProfileSetV2(canonicalProfiles)
	if err != nil {
		return nil, err
	}

	registeredIndex := make(map[string]int, len(registered))
	memberLeaves := make([]*big.Int, len(registered))
	for i, credential := range registered {
		if !canonicalBN254(credential.PublicKeyX) || !canonicalBN254(credential.PublicKeyY) {
			return nil, fmt.Errorf("registered observer %d has a noncanonical BN254 public key", i)
		}
		key := deviceKey(credential.PublicKeyX, credential.PublicKeyY)
		if _, exists := registeredIndex[key]; exists {
			return nil, fmt.Errorf("registered observer public key is duplicated")
		}
		registeredIndex[key] = i
		memberLeaves[i] = membership.MimcHash(credential.PublicKeyX, credential.PublicKeyY)
	}
	memberRoot, _, _ := membership.BuildTree(memberLeaves)
	if memberRoot.Cmp(activeMemberRoot) != 0 {
		return nil, fmt.Errorf("registered roster root does not match the active member root")
	}

	seenIndices := make(map[int]struct{}, len(observations))
	verifiedLeaves := make([]verifiedV2Observation, 0, len(observations))
	var droneID, timeBucket *big.Int
	var consistentCount, suspiciousCount uint32
	for i, observation := range observations {
		if observation.Proof == nil || observation.Public == nil {
			return nil, fmt.Errorf("observation %d is missing its proof or public witness", i)
		}
		public, err := observation.Public.Public()
		if err != nil {
			return nil, fmt.Errorf("observation %d public witness: %w", i, err)
		}
		signals, err := bn254PublicSignalsWithCount(public, leafPublicSignalCountV2)
		if err != nil {
			return nil, fmt.Errorf("observation %d: %w", i, err)
		}
		if err := groth16.Verify(observation.Proof, leafVK, public); err != nil {
			return nil, fmt.Errorf("observation %d V2 leaf proof verification failed: %w", i, err)
		}
		if !isOne(signals[leafObservationEligibleV2]) {
			return nil, fmt.Errorf("observation %d is not fresh or has no positive RSSI range", i)
		}
		if !isZero(signals[leafConsistencyOKV2]) && !isOne(signals[leafConsistencyOKV2]) {
			return nil, fmt.Errorf("observation %d consistency_ok is not boolean", i)
		}
		if signals[leafTimeBucketV2].BitLen() > 64 {
			return nil, fmt.Errorf("observation %d time bucket exceeds uint64", i)
		}
		if signals[leafFreshnessV2].BitLen() > 64 {
			return nil, fmt.Errorf("observation %d freshness timestamp exceeds uint64", i)
		}
		bucketStart := new(big.Int).Mul(signals[leafTimeBucketV2], big.NewInt(leafTimeBucketSecondsV2))
		bucketEnd := new(big.Int).Add(bucketStart, big.NewInt(leafTimeBucketSecondsV2))
		if signals[leafFreshnessV2].Cmp(bucketStart) < 0 || signals[leafFreshnessV2].Cmp(bucketEnd) >= 0 {
			return nil, fmt.Errorf("observation %d freshness timestamp is outside its time bucket", i)
		}
		if signals[leafCalibrationProfileIDV2].BitLen() > 32 {
			return nil, fmt.Errorf("observation %d calibration profile exceeds uint32", i)
		}
		profilePath, allowed := profilePaths[signals[leafCalibrationProfileIDV2].String()]
		if !allowed {
			return nil, fmt.Errorf("observation %d uses calibration profile %s not allowed by policy", i, signals[leafCalibrationProfileIDV2])
		}
		openedProfileRoot, err := calibrationProfilePathRootV2(signals[leafCalibrationProfileIDV2], profilePath)
		if err != nil || openedProfileRoot.Cmp(profileSetRoot) != 0 {
			return nil, fmt.Errorf("observation %d calibration profile does not open the approved profile-set root", i)
		}
		if i == 0 {
			droneID = new(big.Int).Set(signals[leafDroneIDV2])
			timeBucket = new(big.Int).Set(signals[leafTimeBucketV2])
		} else {
			if signals[leafDroneIDV2].Cmp(droneID) != 0 || signals[leafTimeBucketV2].Cmp(timeBucket) != 0 {
				return nil, fmt.Errorf("observation %d belongs to a different session-scoped RID commitment or time bucket", i)
			}
		}

		// The V2 wrapper exposes only the observer keys needed for roster checks.
		// Resolve them against the authoritative roster. This does not authenticate
		// the claimed RID; that trust-root path is not part of the V2 leaf yet.
		memberIndex, ok := registeredIndex[deviceKey(signals[leafObserverPublicKeyXV2], signals[leafObserverPublicKeyYV2])]
		if !ok {
			return nil, fmt.Errorf("observation %d observer is not in the registered roster", i)
		}
		if _, duplicate := seenIndices[memberIndex]; duplicate {
			return nil, fmt.Errorf("observer registry index %d is used more than once", memberIndex)
		}
		seenIndices[memberIndex] = struct{}{}
		verifiedLeaves = append(verifiedLeaves, verifiedV2Observation{
			Proof: observation.Proof, Public: public, Signals: signals, MemberIndex: memberIndex,
			ProfilePath: profilePath,
		})

		if isOne(signals[leafConsistencyOKV2]) {
			consistentCount++
		} else {
			suspiciousCount++
		}
	}

	verdict, err := DeriveFinalVerdict(consistentCount, suspiciousCount, minimumQuorum)
	if err != nil {
		return nil, err
	}
	policyCommitment, err := FinalPolicyCommitmentV2(minimumQuorum, profileSetRoot)
	if err != nil {
		return nil, err
	}
	return &VerifiedObserverBatchV2{
		DroneIDCommitment:          new(big.Int).Set(droneID),
		TimeBucket:                 new(big.Int).Set(timeBucket),
		CalibrationProfileSetRoot:  new(big.Int).Set(profileSetRoot),
		AllowedCalibrationProfiles: canonicalProfiles,
		PolicyCommitment:           policyCommitment,
		MemberRoot:                 new(big.Int).Set(memberRoot),
		ObserverCount:              uint32(len(observations)),
		ConsistentCount:            consistentCount,
		SuspiciousCount:            suspiciousCount,
		MinimumQuorum:              minimumQuorum,
		ProvisionalVerdict:         verdict,
		verifiedLeaves:             verifiedLeaves,
	}, nil
}

func bn254PublicSignalsWithCount(public witness.Witness, expected int) ([]*big.Int, error) {
	if public == nil {
		return nil, fmt.Errorf("public witness is nil")
	}
	values, ok := public.Vector().(fr.Vector)
	if !ok {
		return nil, fmt.Errorf("public witness is not a BN254 scalar vector")
	}
	if len(values) != expected {
		return nil, fmt.Errorf("leaf public witness has %d signals, expected %d", len(values), expected)
	}
	signals := make([]*big.Int, len(values))
	for i := range values {
		signals[i] = new(big.Int)
		values[i].BigInt(signals[i])
	}
	return signals, nil
}
