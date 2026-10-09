// Command pcd3 prepares or proves a fixed three-observer recursive topology.
// V1 uses BridgeBW/FinalBN; --protocol=v2 selects BridgeBWV2/FinalBNV2 and a
// separate 10-input EVM registry. Run from the aggregator directory. The
// default "plan" stage is resource light; --stage=run enables setup/proving.
package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"math/big"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	"github.com/consensys/gnark/backend"
	groth16 "github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/solidity"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/constraint"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	recursion "github.com/consensys/gnark/std/recursion/groth16"

	"uav/aggregator/membership"
	"uav/aggregator/pcd"
	"uav/aggregator/snarkimport"
)

const (
	observerCount = 3
	artifactMode  = 0o600
)

type rosterManifest struct {
	Version    int    `json:"version"`
	Status     string `json:"status"`
	MemberRoot string `json:"memberRoot"`
	Members    []struct {
		PublicKeyX string `json:"publicKeyX"`
		PublicKeyY string `json:"publicKeyY"`
	} `json:"members"`
}

type stageMetadata struct {
	Version          int               `json:"version"`
	Stage            string            `json:"stage"`
	Curve            string            `json:"curve"`
	SetupMode        string            `json:"setupMode"`
	SourceHash       string            `json:"sourceHash"`
	Dependencies     map[string]string `json:"dependencies"`
	Constraints      int               `json:"constraints"`
	PublicInputs     int               `json:"publicInputs"`
	ConstraintHash   string            `json:"constraintHash"`
	ProvingKeyHash   string            `json:"provingKeyHash"`
	VerifyingKeyHash string            `json:"verifyingKeyHash"`
}

type stageArtifacts struct {
	CCS  constraint.ConstraintSystem
	PK   groth16.ProvingKey
	VK   groth16.VerifyingKey
	Dir  string
	Meta stageMetadata
}

type finalArtifact struct {
	ProtocolVersion int      `json:"protocolVersion"`
	MinimumQuorum   uint32   `json:"minimumQuorum"`
	Proof           string   `json:"proof"`
	PublicInputs    []string `json:"publicInputs"`
	VerifierSource  string   `json:"verifierSource"`
	VerifierSHA256  string   `json:"verifierSha256"`
}

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, "pcd3:", err)
		os.Exit(1)
	}
}

func run(args []string) error {
	flags := flag.NewFlagSet("pcd3", flag.ContinueOnError)
	stage := flags.String("stage", "plan", "plan or run; run performs Groth16 setup and proof generation")
	protocol := flags.String("protocol", "v1", "protocol circuit family: v1 or v2")
	leafVKPath := flags.String("leaf-vk", "../rapidsnark_app/assets/circuits/uav_witness/distance30_witness_attestation_verification_key.json", "release-pinned Circom leaf verification key")
	proofDir := flags.String("proof-dir", "../contracts/test/fixtures", "directory containing input_dev0..2 proof/public JSON files")
	rosterPath := flags.String("roster", "pcd/testdata/observer-roster-v1.json", "registered observer roster manifest")
	activeRootArg := flags.String("active-member-root", "", "active member root obtained independently from the observer registry")
	allowManifestRootForTest := flags.Bool("allow-manifest-root-for-test", false, "TEST ONLY: use the roster manifest root as a stand-in for an external registry query")
	artifactDir := flags.String("artifacts", "pcd3-artifacts", "write-once local setup keys and final proof output directory")
	quorum := flags.Uint("quorum", 2, "minimum quorum committed by the selected protocol policy")
	profileArg := flags.String("calibration-profile-ids", "1", "comma-separated V2 allowlisted calibration profile IDs (decimal uint32)")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if flags.NArg() != 0 {
		return fmt.Errorf("unexpected positional arguments: %s", strings.Join(flags.Args(), " "))
	}
	if *stage != "plan" && *stage != "run" {
		return fmt.Errorf("--stage must be plan or run")
	}
	if *protocol != "v1" && *protocol != "v2" {
		return fmt.Errorf("--protocol must be v1 or v2")
	}
	if *quorum == 0 || *quorum > 0xffffffff {
		return fmt.Errorf("--quorum must be a nonzero uint32")
	}

	leafVK, observations, roster, activeRoot, rosterStatus, err := loadInputs(*leafVKPath, *proofDir, *rosterPath, *activeRootArg, *allowManifestRootForTest)
	if err != nil {
		return err
	}
	if *protocol == "v2" {
		profileIDs, err := parseCalibrationProfileIDs(*profileArg)
		if err != nil {
			return err
		}
		batch, err := pcd.PrepareObserverBatchV2(leafVK, observations, roster, activeRoot, profileIDs, uint32(*quorum))
		if err != nil {
			return fmt.Errorf("preflight actual V2 leaf batch: %w", err)
		}
		printPlanV2(batch, rosterStatus)
		if *stage == "plan" {
			fmt.Println("Plan only: no circuit compile, Groth16 setup, or proof was performed.")
			return nil
		}
		fmt.Fprintln(os.Stderr, "WARNING: run performs local Groth16 setup. These keys are research-only; this is not an MPC/trusted ceremony and must not be deployed as a production trust root.")
		return runProofPipelineV2(*artifactDir, leafVK, observations, batch, uint32(*quorum))
	}
	batch, err := pcd.PrepareObserverBatch(leafVK, observations, roster, activeRoot, uint32(*quorum))
	if err != nil {
		return fmt.Errorf("preflight actual leaf batch: %w", err)
	}
	printPlan(batch, rosterStatus)
	if *stage == "plan" {
		fmt.Println("Plan only: no circuit compile, Groth16 setup, or proof was performed.")
		return nil
	}
	if *stage == "run" {
		fmt.Fprintln(os.Stderr, "WARNING: run performs local Groth16 setup. These keys are research-only; this is not an MPC/trusted ceremony and must not be deployed as a production trust root.")
	}
	return runProofPipeline(*artifactDir, leafVK, observations, batch, uint32(*quorum))
}

func loadInputs(vkPath, proofDir, rosterPath, activeRootArg string, allowManifestRootForTest bool) (
	groth16.VerifyingKey,
	[]pcd.LeafObservation,
	[]pcd.DeviceCredential,
	*big.Int,
	string,
	error,
) {
	leafVK, err := snarkimport.LoadVK(vkPath)
	if err != nil {
		return nil, nil, nil, nil, "", fmt.Errorf("load leaf VK %q: %w", vkPath, err)
	}
	observations := make([]pcd.LeafObservation, observerCount)
	for i := range observations {
		proofPath := filepath.Join(proofDir, fmt.Sprintf("input_dev%d_proof.json", i))
		publicPath := filepath.Join(proofDir, fmt.Sprintf("input_dev%d_public.json", i))
		proof, err := snarkimport.LoadProof(proofPath)
		if err != nil {
			return nil, nil, nil, nil, "", fmt.Errorf("load leaf proof %d: %w", i, err)
		}
		public, err := snarkimport.LoadPublicWitness(publicPath)
		if err != nil {
			return nil, nil, nil, nil, "", fmt.Errorf("load leaf public signals %d: %w", i, err)
		}
		observations[i] = pcd.LeafObservation{Proof: proof, Public: public}
	}
	manifestJSON, err := os.ReadFile(rosterPath)
	if err != nil {
		return nil, nil, nil, nil, "", fmt.Errorf("read roster manifest %q: %w", rosterPath, err)
	}
	roster, activeRoot, rosterStatus, err := decodeRosterManifest(manifestJSON, activeRootArg, allowManifestRootForTest)
	if err != nil {
		return nil, nil, nil, nil, "", err
	}
	return leafVK, observations, roster, activeRoot, rosterStatus, nil
}

// decodeRosterManifest checks the manifest's own commitment before comparing
// it with a separately obtained registry root. The explicit test-only switch
// keeps synthetic fixtures usable without making a local JSON file silently
// become an operational trust anchor.
func decodeRosterManifest(raw []byte, activeRootArg string, allowManifestRootForTest bool) ([]pcd.DeviceCredential, *big.Int, string, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	var manifest rosterManifest
	if err := decoder.Decode(&manifest); err != nil {
		return nil, nil, "", fmt.Errorf("decode roster manifest: %w", err)
	}
	if err := decoder.Decode(new(any)); err != io.EOF {
		if err == nil {
			return nil, nil, "", fmt.Errorf("decode roster manifest: unexpected trailing JSON value")
		}
		return nil, nil, "", fmt.Errorf("decode roster manifest trailing data: %w", err)
	}
	if manifest.Version != 1 || strings.TrimSpace(manifest.Status) == "" {
		return nil, nil, "", fmt.Errorf("roster manifest must have version 1 and a status disclosure")
	}
	if len(manifest.Members) == 0 || len(manifest.Members) > 1<<membership.Depth {
		return nil, nil, "", fmt.Errorf("roster must contain between 1 and %d members", 1<<membership.Depth)
	}
	if activeRootArg == "" && !allowManifestRootForTest {
		return nil, nil, "", fmt.Errorf("--active-member-root is required; --allow-manifest-root-for-test is only for synthetic offline tests")
	}

	fieldModulus := ecc.BN254.ScalarField()
	parseField := func(raw, label string) (*big.Int, error) {
		value, ok := new(big.Int).SetString(raw, 10)
		if !ok || value.Sign() < 0 || value.Cmp(fieldModulus) >= 0 || value.String() != raw {
			return nil, fmt.Errorf("%s must be a canonical decimal BN254 scalar", label)
		}
		return value, nil
	}
	declaredRoot, err := parseField(manifest.MemberRoot, "roster manifest memberRoot")
	if err != nil {
		return nil, nil, "", err
	}
	roster := make([]pcd.DeviceCredential, len(manifest.Members))
	memberLeaves := make([]*big.Int, len(manifest.Members))
	seen := make(map[string]struct{}, len(manifest.Members))
	for i, member := range manifest.Members {
		roster[i].PublicKeyX, err = parseField(member.PublicKeyX, fmt.Sprintf("roster member %d publicKeyX", i))
		if err != nil {
			return nil, nil, "", err
		}
		roster[i].PublicKeyY, err = parseField(member.PublicKeyY, fmt.Sprintf("roster member %d publicKeyY", i))
		if err != nil {
			return nil, nil, "", err
		}
		key := roster[i].PublicKeyX.String() + ":" + roster[i].PublicKeyY.String()
		if _, exists := seen[key]; exists {
			return nil, nil, "", fmt.Errorf("roster member public key is duplicated")
		}
		seen[key] = struct{}{}
		memberLeaves[i] = membership.MimcHash(roster[i].PublicKeyX, roster[i].PublicKeyY)
	}
	computedRoot, _, _ := membership.BuildTree(memberLeaves)
	if computedRoot.Cmp(declaredRoot) != 0 {
		return nil, nil, "", fmt.Errorf("roster member list does not match the manifest memberRoot")
	}

	activeRoot := declaredRoot
	rootSource := "manifest test-only opt-in"
	if activeRootArg != "" {
		activeRoot, err = parseField(activeRootArg, "--active-member-root")
		if err != nil {
			return nil, nil, "", err
		}
		rootSource = "explicit --active-member-root (operator must obtain it from the authoritative registry)"
	} else if !allowManifestRootForTest {
		return nil, nil, "", fmt.Errorf("an external registry root is required")
	}
	if computedRoot.Cmp(activeRoot) != 0 {
		return nil, nil, "", fmt.Errorf("roster member list does not match the active member root")
	}
	status := fmt.Sprintf("%s; active root source: %s", manifest.Status, rootSource)
	return roster, activeRoot, status, nil
}

func printPlan(batch *pcd.PreparedObserverBatch, rosterStatus string) {
	fmt.Printf("Verified leaf proofs: %d; distinct registered observers: %d\n", len(batch.Observers), countRoster(batch))
	fmt.Printf("Member root: %s\n", batch.MemberRoot)
	fmt.Printf("Nullifier root: %s\n", batch.MergedNullRoot)
	fmt.Printf("Counts: consistent=%s suspicious=%s verdict=%s\n",
		batch.FinalStatement[6], batch.FinalStatement[7], batch.FinalStatement[8])
	fmt.Printf("Roster disclosure: %s\n", rosterStatus)
	for _, warning := range planSecurityWarnings() {
		fmt.Println(warning)
	}
	fmt.Println("Finite proof topology: BridgeBW x3 -> NodeBLS(0,1) + PromoteBLS(2) -> NodeBW -> FinalBN")
}

func printPlanV2(batch *pcd.PreparedObserverBatchV2, rosterStatus string) {
	fmt.Printf("Verified V2 leaf proofs: %d; distinct registered observers: %d\n", len(batch.Observers), len(batch.Observers))
	fmt.Printf("Member root: %s\n", batch.MemberRoot)
	fmt.Printf("Nullifier root: %s\n", batch.MergedNullRoot)
	profileIDs := make([]string, len(batch.AllowedCalibrationProfiles))
	for i, profileID := range batch.AllowedCalibrationProfiles {
		profileIDs[i] = profileID.String()
	}
	fmt.Printf("Approved calibration profile-set root: %s; policy commitment: %s\n", batch.CalibrationProfileSetRoot, batch.PolicyCommitment)
	fmt.Printf("Approved calibration profile IDs: %s\n", strings.Join(profileIDs, ","))
	fmt.Printf("Counts: consistent=%s suspicious=%s decision=%s (verdict=%s)\n",
		batch.FinalStatement[7], batch.FinalStatement[8],
		pcd.FinalVerdictV2Label(pcd.FinalVerdict(batch.FinalStatement[9].Uint64())), batch.FinalStatement[9])
	fmt.Printf("Roster disclosure: %s\n", rosterStatus)
	fmt.Println("Finite V2 proof topology: BridgeBWV2 x3 -> NodeBLSV2(0,1) + PromoteBLSV2(2) -> NodeBWV2 -> FinalBNV2")
	fmt.Println("Security note: V2 groups the claimed RID only; it does not authenticate the aircraft or verify a DRIP trust chain.")
}

func parseCalibrationProfileIDs(raw string) ([]*big.Int, error) {
	parts := strings.Split(raw, ",")
	if len(parts) == 0 {
		return nil, fmt.Errorf("--calibration-profile-ids must contain at least one decimal uint32 ID")
	}
	ids := make([]*big.Int, len(parts))
	for i, part := range parts {
		part = strings.TrimSpace(part)
		id, ok := new(big.Int).SetString(part, 10)
		if !ok || id.Sign() < 0 || id.BitLen() > 32 {
			return nil, fmt.Errorf("--calibration-profile-ids item %q must be a decimal uint32", part)
		}
		ids[i] = id
	}
	return ids, nil
}

func planSecurityWarnings() []string {
	return []string{
		"Remote ID auth: legacy prover-supplied signature only; key-to-ID trust-root binding is NOT proven",
		"RSSI evidence: V1 observer signature does not bind measured_range_cm or consistency_ok; result is NOT observer-authenticated",
	}
}

func countRoster(batch *pcd.PreparedObserverBatch) int {
	seen := make(map[int]struct{}, len(batch.Observers))
	for _, observer := range batch.Observers {
		seen[observer.MemberIndex] = struct{}{}
	}
	return len(seen)
}

func runProofPipeline(artifactDir string, leafVK groth16.VerifyingKey, observations []pcd.LeafObservation, batch *pcd.PreparedObserverBatch, quorum uint32) error {
	leafVKHash, err := fileHashFromWriter(leafVK)
	if err != nil {
		return fmt.Errorf("hash pinned leaf VK: %w", err)
	}
	bridge, err := ensureStage(artifactDir, "bridge-bw", ecc.BW6_761, map[string]string{"leaf-vk": leafVKHash}, func() (frontend.Circuit, error) {
		return pcd.NewBridgeBWFromSample(leafVK, observations[0].Proof, observations[0].Public)
	})
	if err != nil {
		return err
	}

	nodeBLS, err := ensureStage(artifactDir, "node-bls", ecc.BLS12_377, stageHashes(bridge), func() (frontend.Circuit, error) {
		return pcd.NewNodeBLS(bridge.CCS, bridge.VK)
	})
	if err != nil {
		return err
	}
	promoteBLS, err := ensureStage(artifactDir, "promote-bls", ecc.BLS12_377, stageHashes(bridge), func() (frontend.Circuit, error) {
		return pcd.NewPromoteBLS(bridge.CCS, bridge.VK)
	})
	if err != nil {
		return err
	}
	nodeBW, err := ensureStage(artifactDir, "node-bw", ecc.BW6_761, mergeStageHashes(nodeBLS, promoteBLS), func() (frontend.Circuit, error) {
		return pcd.NewNodeBWWithChildKeys(nodeBLS.CCS, nodeBLS.VK, promoteBLS.CCS, promoteBLS.VK)
	})
	if err != nil {
		return err
	}
	finalBN, err := ensureStage(artifactDir, "final-bn", ecc.BN254, stageHashes(nodeBW), func() (frontend.Circuit, error) {
		return pcd.NewFinalBN(nodeBW.CCS, nodeBW.VK)
	})
	if err != nil {
		return err
	}
	verifierPath, verifierHash, err := ensureSolidityVerifier(finalBN)
	if err != nil {
		return err
	}

	bridgeProofs := make([]groth16.Proof, observerCount)
	bridgePublics := make([]witness.Witness, observerCount)
	for i, observer := range batch.Observers {
		assignment, err := observer.BridgeAssignment()
		if err != nil {
			return fmt.Errorf("build BridgeBW assignment %d: %w", i, err)
		}
		bridgeProofs[i], bridgePublics[i], err = proveAndVerify("BridgeBW", bridge, assignment, ecc.BW6_761, ecc.BN254, false)
		if err != nil {
			return fmt.Errorf("BridgeBW observer %d: %w", i, err)
		}
	}

	state01, leaves01, err := pcd.MergeObserverStates(
		batch.Observers[0].State, batch.Observers[1].State,
		batch.Observers[0].NullifierLeaves, batch.Observers[1].NullifierLeaves,
	)
	if err != nil {
		return err
	}
	nodeBLSAssignment, err := pcd.NodeBLSAssignment(
		bridgeProofs[0], bridgePublics[0], bridgeProofs[1], bridgePublics[1], state01,
		pcd.NullifierSetWitness{Left: batch.Observers[0].NullifierLeaves, Right: batch.Observers[1].NullifierLeaves},
	)
	if err != nil {
		return fmt.Errorf("build NodeBLS assignment: %w", err)
	}
	nodeBLSProof, nodeBLSPublic, err := proveAndVerify("NodeBLS", nodeBLS, nodeBLSAssignment, ecc.BLS12_377, ecc.BW6_761, false)
	if err != nil {
		return err
	}

	promoteAssignment, err := pcd.PromoteBLSAssignment(bridgeProofs[2], bridgePublics[2], batch.Observers[2].State)
	if err != nil {
		return fmt.Errorf("build PromoteBLS assignment: %w", err)
	}
	promoteProof, promotePublic, err := proveAndVerify("PromoteBLS", promoteBLS, promoteAssignment, ecc.BLS12_377, ecc.BW6_761, false)
	if err != nil {
		return err
	}

	rootState, leaves012, err := pcd.MergeObserverStates(state01, batch.Observers[2].State, leaves01, batch.Observers[2].NullifierLeaves)
	if err != nil {
		return err
	}
	nodeBWAssignment, err := pcd.NodeBWAssignment(
		nodeBLSProof, nodeBLSPublic, promoteProof, promotePublic, rootState,
		pcd.NullifierSetWitness{Left: leaves01, Right: batch.Observers[2].NullifierLeaves},
	)
	if err != nil {
		return fmt.Errorf("build NodeBW assignment: %w", err)
	}
	nodeBWProof, nodeBWPublic, err := proveAndVerify("NodeBW", nodeBW, nodeBWAssignment, ecc.BW6_761, ecc.BLS12_377, false)
	if err != nil {
		return err
	}
	if rootState[stateIndexNewNullifierRoot].Cmp(batch.MergedNullRoot) != 0 || lenLeaves(leaves012) != observerCount {
		return fmt.Errorf("computed recursive root state disagrees with preflight batch")
	}

	finalAssignment, err := pcd.FinalBNAssignment(nodeBWProof, nodeBWPublic, batch.FinalStatement, quorum)
	if err != nil {
		return fmt.Errorf("build FinalBN assignment: %w", err)
	}
	finalProof, finalPublic, err := proveAndVerify("FinalBN", finalBN, finalAssignment, ecc.BN254, ecc.BW6_761, true)
	if err != nil {
		return err
	}
	return writeFinalArtifact(artifactDir, batch, quorum, finalProof, finalPublic, verifierPath, verifierHash)
}

// stateIndexNewNullifierRoot is the fixed internal PCD state index, kept local
// to the command so external callers do not need to depend on unexported names.
const stateIndexNewNullifierRoot = 6

func lenLeaves(leaves pcd.NullifierLeaves) int {
	count := 0
	for _, leaf := range leaves {
		if leaf != nil && leaf.Sign() != 0 {
			count++
		}
	}
	return count
}

func proveAndVerify(
	label string,
	stage stageArtifacts,
	assignment frontend.Circuit,
	outerCurve, innerCurve ecc.ID,
	solidityTarget bool,
) (groth16.Proof, witness.Witness, error) {
	fullWitness, err := frontend.NewWitness(assignment, outerCurve.ScalarField())
	if err != nil {
		return nil, nil, fmt.Errorf("%s witness: %w", label, err)
	}
	public, err := fullWitness.Public()
	if err != nil {
		return nil, nil, fmt.Errorf("%s public witness: %w", label, err)
	}
	return proveAndVerifyWitness(label, stage, fullWitness, public, outerCurve, innerCurve, solidityTarget)
}

func proveAndVerifyWitness(
	label string,
	stage stageArtifacts,
	fullWitness witness.Witness,
	public witness.Witness,
	outerCurve, innerCurve ecc.ID,
	solidityTarget bool,
) (groth16.Proof, witness.Witness, error) {
	proverOptions := []backend.ProverOption{recursion.GetNativeProverOptions(outerCurve.ScalarField(), innerCurve.ScalarField())}
	verifierOptions := []backend.VerifierOption{recursion.GetNativeVerifierOptions(outerCurve.ScalarField(), innerCurve.ScalarField())}
	if solidityTarget {
		proverOptions = append(proverOptions, solidity.WithProverTargetSolidityVerifier(backend.GROTH16))
		verifierOptions = append(verifierOptions, solidity.WithVerifierTargetSolidityVerifier(backend.GROTH16))
	}
	proof, err := groth16.Prove(stage.CCS, stage.PK, fullWitness, proverOptions...)
	if err != nil {
		return nil, nil, fmt.Errorf("%s prove: %w", label, err)
	}
	if err := groth16.Verify(proof, stage.VK, public, verifierOptions...); err != nil {
		return nil, nil, fmt.Errorf("%s native verify: %w", label, err)
	}
	return proof, public, nil
}

func ensureStage(
	artifactDir string,
	name string,
	curve ecc.ID,
	dependencies map[string]string,
	build func() (frontend.Circuit, error),
) (stageArtifacts, error) {
	setupDir := filepath.Join(artifactDir, "setup")
	if err := os.MkdirAll(setupDir, 0o700); err != nil {
		return stageArtifacts{}, err
	}
	stageDir := filepath.Join(setupDir, name)
	sourceHash, err := sourceFingerprint()
	if err != nil {
		return stageArtifacts{}, err
	}
	if info, err := os.Lstat(stageDir); err == nil {
		if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
			return stageArtifacts{}, fmt.Errorf("cached %s path %q is not a regular directory", name, stageDir)
		}
		return loadStage(stageDir, name, curve, sourceHash, dependencies)
	} else if !errors.Is(err, os.ErrNotExist) {
		return stageArtifacts{}, err
	}
	if recovered, ok, err := recoverStageCache(setupDir, name, stageDir, func(dir string) (stageArtifacts, error) {
		return loadStage(dir, name, curve, sourceHash, dependencies)
	}); err != nil {
		return stageArtifacts{}, err
	} else if ok {
		return recovered, nil
	}
	template, err := build()
	if err != nil {
		return stageArtifacts{}, fmt.Errorf("build %s template: %w", name, err)
	}
	fmt.Printf("[%s] compile (%s)\n", name, curveName(curve))
	ccs, err := frontend.Compile(curve.ScalarField(), r1cs.NewBuilder, template)
	if err != nil {
		return stageArtifacts{}, fmt.Errorf("compile %s: %w", name, err)
	}
	fmt.Printf("[%s] constraints=%d publicInputs=%d; local Groth16 setup starts\n", name, ccs.GetNbConstraints(), ccs.GetNbPublicVariables()-1)
	pk, vk, err := groth16.Setup(ccs)
	if err != nil {
		return stageArtifacts{}, fmt.Errorf("setup %s: %w", name, err)
	}
	tempDir, err := os.MkdirTemp(setupDir, "."+name+".tmp-")
	if err != nil {
		return stageArtifacts{}, err
	}
	meta, err := saveStage(tempDir, name, curve, sourceHash, dependencies, ccs, pk, vk)
	if err != nil {
		return stageArtifacts{}, fmt.Errorf("save %s stage in preserved temporary directory %q: %w", name, tempDir, err)
	}
	if err := os.Rename(tempDir, stageDir); err != nil {
		// Another pcd3 process may have completed the same stage while this one
		// was setting it up. Reuse only that independently validated cache.
		if info, statErr := os.Lstat(stageDir); statErr == nil && info.IsDir() && info.Mode()&os.ModeSymlink == 0 {
			return loadStage(stageDir, name, curve, sourceHash, dependencies)
		}
		return stageArtifacts{}, fmt.Errorf("publish completed %s stage cache: %w (complete temporary cache preserved at %q)", name, err, tempDir)
	}
	return stageArtifacts{CCS: ccs, PK: pk, VK: vk, Dir: stageDir, Meta: meta}, nil
}

func saveStage(
	dir, name string,
	curve ecc.ID,
	sourceHash string,
	dependencies map[string]string,
	ccs constraint.ConstraintSystem,
	pk groth16.ProvingKey,
	vk groth16.VerifyingKey,
) (stageMetadata, error) {
	artifacts := []struct {
		filename string
		writer   interface {
			WriteTo(io.Writer) (int64, error)
		}
	}{
		{filename: "circuit.ccs", writer: ccs},
		{filename: "proving.key", writer: pk},
		{filename: "verifying.key", writer: vk},
	}
	for _, artifact := range artifacts {
		filename, writer := artifact.filename, artifact.writer
		if err := writeBinaryNew(filepath.Join(dir, filename), writer); err != nil {
			return stageMetadata{}, fmt.Errorf("write %s artifact: %w", filename, err)
		}
	}
	csHash, err := fileHash(filepath.Join(dir, "circuit.ccs"))
	if err != nil {
		return stageMetadata{}, err
	}
	pkHash, err := fileHash(filepath.Join(dir, "proving.key"))
	if err != nil {
		return stageMetadata{}, err
	}
	vkHash, err := fileHash(filepath.Join(dir, "verifying.key"))
	if err != nil {
		return stageMetadata{}, err
	}
	meta := stageMetadata{
		Version: 1, Stage: name, Curve: curveName(curve),
		SetupMode:  "local-random-groth16-not-mpc-not-for-production",
		SourceHash: sourceHash, Dependencies: dependencies,
		Constraints: ccs.GetNbConstraints(), PublicInputs: ccs.GetNbPublicVariables() - 1,
		ConstraintHash: csHash, ProvingKeyHash: pkHash, VerifyingKeyHash: vkHash,
	}
	if err := writeJSONNew(filepath.Join(dir, "stage.json"), meta); err != nil {
		return stageMetadata{}, err
	}
	return meta, nil
}

func loadStage(dir, name string, curve ecc.ID, sourceHash string, dependencies map[string]string) (stageArtifacts, error) {
	var meta stageMetadata
	if err := readJSON(filepath.Join(dir, "stage.json"), &meta); err != nil {
		return stageArtifacts{}, fmt.Errorf("incomplete stage directory %q; preserve it and use a new --artifacts path or inspect it before cleanup: %w", dir, err)
	}
	if meta.Version != 1 || meta.Stage != name || meta.Curve != curveName(curve) || meta.SourceHash != sourceHash || !sameMap(meta.Dependencies, dependencies) {
		return stageArtifacts{}, fmt.Errorf("cached %s artifacts do not match current source/dependencies; use a new --artifacts directory", name)
	}
	if err := verifyFileHash(filepath.Join(dir, "circuit.ccs"), meta.ConstraintHash); err != nil {
		return stageArtifacts{}, err
	}
	if err := verifyFileHash(filepath.Join(dir, "proving.key"), meta.ProvingKeyHash); err != nil {
		return stageArtifacts{}, err
	}
	if err := verifyFileHash(filepath.Join(dir, "verifying.key"), meta.VerifyingKeyHash); err != nil {
		return stageArtifacts{}, err
	}
	ccs := groth16.NewCS(curve)
	pk := groth16.NewProvingKey(curve)
	vk := groth16.NewVerifyingKey(curve)
	if err := readBinary(filepath.Join(dir, "circuit.ccs"), ccs); err != nil {
		return stageArtifacts{}, fmt.Errorf("read %s CCS: %w", name, err)
	}
	if err := readBinary(filepath.Join(dir, "proving.key"), pk); err != nil {
		return stageArtifacts{}, fmt.Errorf("read %s proving key: %w", name, err)
	}
	if err := readBinary(filepath.Join(dir, "verifying.key"), vk); err != nil {
		return stageArtifacts{}, fmt.Errorf("read %s verifying key: %w", name, err)
	}
	if ccs.GetNbConstraints() != meta.Constraints || ccs.GetNbPublicVariables()-1 != meta.PublicInputs {
		return stageArtifacts{}, fmt.Errorf("cached %s CCS metadata does not match serialized circuit", name)
	}
	fmt.Printf("[%s] loaded verified cache (%d constraints)\n", name, meta.Constraints)
	return stageArtifacts{CCS: ccs, PK: pk, VK: vk, Dir: dir, Meta: meta}, nil
}

func stageHashes(stage stageArtifacts) map[string]string {
	return map[string]string{"constraint": stage.Meta.ConstraintHash, "vk": stage.Meta.VerifyingKeyHash}
}

func mergeStageHashes(left, right stageArtifacts) map[string]string {
	return map[string]string{
		"left.constraint": left.Meta.ConstraintHash, "left.vk": left.Meta.VerifyingKeyHash,
		"right.constraint": right.Meta.ConstraintHash, "right.vk": right.Meta.VerifyingKeyHash,
	}
}

func sourceFingerprint() (string, error) {
	root, err := aggregatorRoot()
	if err != nil {
		return "", err
	}
	paths, err := sourceFingerprintFiles()
	if err != nil {
		return "", err
	}
	h := sha256.New()
	for _, path := range paths {
		contents, err := os.ReadFile(filepath.Join(root, path))
		if err != nil {
			return "", fmt.Errorf("fingerprint source %s: %w", path, err)
		}
		io.WriteString(h, path)
		h.Write([]byte{0})
		h.Write(contents)
		h.Write([]byte{0})
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

func sourceFingerprintFiles() ([]string, error) {
	root, err := aggregatorRoot()
	if err != nil {
		return nil, err
	}
	paths := []string{"go.mod", "go.sum"}
	commandSources, err := filepath.Glob(filepath.Join(root, "cmd", "pcd3", "*.go"))
	if err != nil {
		return nil, err
	}
	for _, match := range commandSources {
		relative, err := filepath.Rel(root, match)
		if err != nil {
			return nil, err
		}
		paths = append(paths, relative)
	}
	for _, dir := range []string{"pcd", "membership", "nullifier"} {
		for _, extension := range []string{"go", "json"} {
			matches, err := filepath.Glob(filepath.Join(root, dir, "*."+extension))
			if err != nil {
				return nil, err
			}
			for _, match := range matches {
				relative, err := filepath.Rel(root, match)
				if err != nil {
					return nil, err
				}
				paths = append(paths, relative)
			}
		}
	}
	sort.Strings(paths)
	return paths, nil
}

func aggregatorRoot() (string, error) {
	current, err := os.Getwd()
	if err != nil {
		return "", err
	}
	for dir := current; ; dir = filepath.Dir(dir) {
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			pcdDirErr := statDir(filepath.Join(dir, "pcd"))
			membershipDirErr := statDir(filepath.Join(dir, "membership"))
			if pcdDirErr == nil && membershipDirErr == nil {
				return dir, nil
			}
		} else if !errors.Is(err, os.ErrNotExist) {
			return "", err
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return "", fmt.Errorf("could not locate aggregator module root above %s", current)
		}
	}
}

func statDir(path string) error {
	info, err := os.Stat(path)
	if err != nil {
		return err
	}
	if !info.IsDir() {
		return fmt.Errorf("%s is not a directory", path)
	}
	return nil
}

func ensureSolidityVerifier(finalBN stageArtifacts) (string, string, error) {
	var source bytes.Buffer
	if err := finalBN.VK.ExportSolidity(&source); err != nil {
		return "", "", fmt.Errorf("export FinalBN Solidity verifier: %w", err)
	}
	path := filepath.Join(finalBN.Dir, "FinalAttestationGroth16VerifierV1.sol")
	if existing, err := os.ReadFile(path); err == nil {
		if !bytes.Equal(existing, source.Bytes()) {
			return "", "", fmt.Errorf("cached Solidity verifier does not match FinalBN VK")
		}
	} else if errors.Is(err, os.ErrNotExist) {
		if err := writeBytesNew(path, source.Bytes()); err != nil {
			return "", "", err
		}
	} else {
		return "", "", err
	}
	return path, hashBytes(source.Bytes()), nil
}

func writeFinalArtifact(artifactDir string, batch *pcd.PreparedObserverBatch, quorum uint32, proof groth16.Proof, public witness.Witness, verifierPath, verifierHash string) error {
	proofBytes, ok := proof.(interface{ MarshalSolidity() []byte })
	if !ok {
		return fmt.Errorf("FinalBN proof has no Solidity encoding")
	}
	publicSignals, err := pcdPublicInputs(public)
	if err != nil {
		return err
	}
	if len(publicSignals) != len(batch.FinalStatement) {
		return fmt.Errorf("FinalBN proof exposes %d public signals, expected %d", len(publicSignals), len(batch.FinalStatement))
	}
	for i := range publicSignals {
		if publicSignals[i] != batch.FinalStatement[i].String() {
			return fmt.Errorf("FinalBN public input %d=%s, expected %s", i, publicSignals[i], batch.FinalStatement[i])
		}
	}
	solidityProof := proofBytes.MarshalSolidity()
	proofHex := "0x" + hex.EncodeToString(solidityProof)
	proofHash := sha256.Sum256(solidityProof)
	name := fmt.Sprintf("session-%s-%s-q%d", batch.FinalStatement[1], batch.FinalStatement[2], quorum)
	outDir := filepath.Join(artifactDir, "proofs", name)
	if err := os.MkdirAll(filepath.Dir(outDir), 0o700); err != nil {
		return err
	}
	if err := os.Mkdir(outDir, 0o700); err != nil {
		return fmt.Errorf("create proof output %q (refusing to overwrite): %w", outDir, err)
	}
	verifierRelativePath, err := filepath.Rel(outDir, verifierPath)
	if err != nil {
		return fmt.Errorf("compute verifier path relative to final artifact: %w", err)
	}
	artifact := finalArtifact{
		ProtocolVersion: 1, MinimumQuorum: quorum, Proof: proofHex,
		PublicInputs:   publicSignals,
		VerifierSource: verifierRelativePath,
		VerifierSHA256: verifierHash,
	}
	if err := writeJSONNew(filepath.Join(outDir, "final-proof-v1.json"), artifact); err != nil {
		return err
	}
	if err := writeTextNew(filepath.Join(outDir, "proof-sha256.txt"), hex.EncodeToString(proofHash[:])); err != nil {
		return err
	}
	fmt.Printf("Final proof verified; Solidity verifier: %s\n", verifierPath)
	fmt.Printf("Final proof artifact: %s\n", filepath.Join(outDir, "final-proof-v1.json"))
	return nil
}

func pcdPublicInputs(public witness.Witness) ([]string, error) {
	if public == nil {
		return nil, fmt.Errorf("final public witness is nil")
	}
	vector, ok := public.Vector().(fr.Vector)
	if !ok {
		return nil, fmt.Errorf("final public witness is not a BN254 scalar vector: %T", public.Vector())
	}
	values := make([]string, len(vector))
	for i := range vector {
		values[i] = vector[i].BigInt(new(big.Int)).String()
	}
	return values, nil
}

func curveName(curve ecc.ID) string { return curve.String() }

func sameMap(left, right map[string]string) bool {
	if len(left) != len(right) {
		return false
	}
	for key, value := range left {
		if right[key] != value {
			return false
		}
	}
	return true
}

func writeBinaryNew(path string, value interface {
	WriteTo(io.Writer) (int64, error)
}) error {
	file, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, artifactMode)
	if err != nil {
		return err
	}
	_, writeErr := value.WriteTo(file)
	syncErr := file.Sync()
	closeErr := file.Close()
	if writeErr != nil {
		return writeErr
	}
	if syncErr != nil {
		return syncErr
	}
	return closeErr
}

func readBinary(path string, value interface {
	ReadFrom(io.Reader) (int64, error)
}) error {
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	_, readErr := value.ReadFrom(file)
	closeErr := file.Close()
	if readErr != nil {
		return readErr
	}
	return closeErr
}

func writeJSONNew(path string, value any) error {
	file, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, artifactMode)
	if err != nil {
		return err
	}
	encoder := json.NewEncoder(file)
	encoder.SetIndent("", "  ")
	writeErr := encoder.Encode(value)
	syncErr := file.Sync()
	closeErr := file.Close()
	if writeErr != nil {
		return writeErr
	}
	if syncErr != nil {
		return syncErr
	}
	return closeErr
}

func readJSON(path string, target any) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, target)
}

func writeBytesNew(path string, data []byte) error {
	file, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, artifactMode)
	if err != nil {
		return err
	}
	_, writeErr := file.Write(data)
	syncErr := file.Sync()
	closeErr := file.Close()
	if writeErr != nil {
		return writeErr
	}
	if syncErr != nil {
		return syncErr
	}
	return closeErr
}

func writeTextNew(path, text string) error { return writeBytesNew(path, []byte(text+"\n")) }

func fileHash(path string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	h := sha256.New()
	_, copyErr := io.Copy(h, file)
	closeErr := file.Close()
	if copyErr != nil {
		return "", copyErr
	}
	if closeErr != nil {
		return "", closeErr
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

func fileHashFromWriter(writer io.WriterTo) (string, error) {
	h := sha256.New()
	if _, err := writer.WriteTo(h); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

func hashBytes(data []byte) string {
	h := sha256.Sum256(data)
	return hex.EncodeToString(h[:])
}

func verifyFileHash(path, expected string) error {
	actual, err := fileHash(path)
	if err != nil {
		return err
	}
	if actual != expected {
		return fmt.Errorf("artifact hash mismatch for %s", path)
	}
	return nil
}
