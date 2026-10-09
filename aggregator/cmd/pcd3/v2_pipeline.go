package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"github.com/consensys/gnark-crypto/ecc"
	groth16 "github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/frontend"

	"uav/aggregator/pcd"
)

func runProofPipelineV2(artifactDir string, leafVK groth16.VerifyingKey, observations []pcd.LeafObservation, batch *pcd.PreparedObserverBatchV2, quorum uint32) error {
	if len(observations) != observerCount || len(batch.Observers) != observerCount {
		return fmt.Errorf("V2 recursive runner requires exactly %d observers", observerCount)
	}
	leafVKHash, err := fileHashFromWriter(leafVK)
	if err != nil {
		return fmt.Errorf("hash pinned V2 leaf VK: %w", err)
	}
	bridge, err := ensureStage(artifactDir, "bridge-bw-v2", ecc.BW6_761, map[string]string{"leaf-vk": leafVKHash}, func() (frontend.Circuit, error) {
		return pcd.NewBridgeBWV2FromSample(leafVK, observations[0].Proof, observations[0].Public)
	})
	if err != nil {
		return err
	}
	nodeBLS, err := ensureStage(artifactDir, "node-bls-v2", ecc.BLS12_377, stageHashes(bridge), func() (frontend.Circuit, error) {
		return pcd.NewNodeBLSForProtocol(bridge.CCS, bridge.VK, uint32(pcd.FinalPolicyV2Version))
	})
	if err != nil {
		return err
	}
	promoteBLS, err := ensureStage(artifactDir, "promote-bls-v2", ecc.BLS12_377, stageHashes(bridge), func() (frontend.Circuit, error) {
		return pcd.NewPromoteBLSForProtocol(bridge.CCS, bridge.VK, uint32(pcd.FinalPolicyV2Version))
	})
	if err != nil {
		return err
	}
	nodeBW, err := ensureStage(artifactDir, "node-bw-v2", ecc.BW6_761, mergeStageHashes(nodeBLS, promoteBLS), func() (frontend.Circuit, error) {
		return pcd.NewNodeBWWithChildKeysForProtocol(nodeBLS.CCS, nodeBLS.VK, promoteBLS.CCS, promoteBLS.VK, uint32(pcd.FinalPolicyV2Version))
	})
	if err != nil {
		return err
	}
	finalBN, err := ensureStage(artifactDir, "final-bn-v2", ecc.BN254, stageHashes(nodeBW), func() (frontend.Circuit, error) {
		return pcd.NewFinalBNV2(nodeBW.CCS, nodeBW.VK)
	})
	if err != nil {
		return err
	}
	verifierPath, verifierHash, err := ensureSolidityVerifierV2(finalBN)
	if err != nil {
		return err
	}

	bridgeProofs := make([]groth16.Proof, observerCount)
	bridgePublics := make([]witness.Witness, observerCount)
	for i, observer := range batch.Observers {
		assignment, err := observer.BridgeAssignment()
		if err != nil {
			return fmt.Errorf("build BridgeBWV2 assignment %d: %w", i, err)
		}
		cacheLabel := fmt.Sprintf("bridge-bw-v2-observer-%d", i)
		bridgeProofs[i], bridgePublics[i], err = proveAndVerifyCached(artifactDir, cacheLabel, bridge, assignment, ecc.BW6_761, ecc.BN254, false)
		if err != nil {
			return fmt.Errorf("BridgeBWV2 observer %d: %w", i, err)
		}
	}

	state01, leaves01, err := pcd.MergeObserverStates(batch.Observers[0].State, batch.Observers[1].State, batch.Observers[0].NullifierLeaves, batch.Observers[1].NullifierLeaves)
	if err != nil {
		return err
	}
	nodeBLSAssignment, err := pcd.NodeBLSAssignment(bridgeProofs[0], bridgePublics[0], bridgeProofs[1], bridgePublics[1], state01,
		pcd.NullifierSetWitness{Left: batch.Observers[0].NullifierLeaves, Right: batch.Observers[1].NullifierLeaves})
	if err != nil {
		return fmt.Errorf("build NodeBLS V2 assignment: %w", err)
	}
	nodeBLSProof, nodeBLSPublic, err := proveAndVerifyCached(artifactDir, "node-bls-v2", nodeBLS, nodeBLSAssignment, ecc.BLS12_377, ecc.BW6_761, false)
	if err != nil {
		return err
	}

	promoteAssignment, err := pcd.PromoteBLSAssignmentForProtocol(bridgeProofs[2], bridgePublics[2], batch.Observers[2].State, uint32(pcd.FinalPolicyV2Version))
	if err != nil {
		return fmt.Errorf("build PromoteBLS V2 assignment: %w", err)
	}
	promoteProof, promotePublic, err := proveAndVerifyCached(artifactDir, "promote-bls-v2", promoteBLS, promoteAssignment, ecc.BLS12_377, ecc.BW6_761, false)
	if err != nil {
		return err
	}

	rootState, leaves012, err := pcd.MergeObserverStates(state01, batch.Observers[2].State, leaves01, batch.Observers[2].NullifierLeaves)
	if err != nil {
		return err
	}
	for i := range rootState {
		if rootState[i].Cmp(batch.RootState[i]) != 0 {
			return fmt.Errorf("computed V2 recursive root state[%d] disagrees with preflight batch", i)
		}
	}
	if lenLeaves(leaves012) != observerCount {
		return fmt.Errorf("V2 recursive nullifier union contains %d observers, want %d", lenLeaves(leaves012), observerCount)
	}
	nodeBWAssignment, err := pcd.NodeBWAssignment(nodeBLSProof, nodeBLSPublic, promoteProof, promotePublic, rootState,
		pcd.NullifierSetWitness{Left: leaves01, Right: batch.Observers[2].NullifierLeaves})
	if err != nil {
		return fmt.Errorf("build NodeBW V2 assignment: %w", err)
	}
	nodeBWProof, nodeBWPublic, err := proveAndVerifyCached(artifactDir, "node-bw-v2", nodeBW, nodeBWAssignment, ecc.BW6_761, ecc.BLS12_377, false)
	if err != nil {
		return err
	}
	finalAssignment, err := pcd.FinalBNV2Assignment(nodeBWProof, nodeBWPublic, batch.FinalStatement, quorum)
	if err != nil {
		return fmt.Errorf("build FinalBNV2 assignment: %w", err)
	}
	finalProof, finalPublic, err := proveAndVerifyCached(artifactDir, "final-bn-v2", finalBN, finalAssignment, ecc.BN254, ecc.BW6_761, true)
	if err != nil {
		return err
	}
	return writeFinalArtifactV2(artifactDir, batch, quorum, finalProof, finalPublic, verifierPath, verifierHash)
}

func ensureSolidityVerifierV2(finalBN stageArtifacts) (string, string, error) {
	var source bytes.Buffer
	if err := finalBN.VK.ExportSolidity(&source); err != nil {
		return "", "", fmt.Errorf("export FinalBNV2 Solidity verifier: %w", err)
	}
	path := filepath.Join(finalBN.Dir, "FinalAttestationGroth16VerifierV2.sol")
	if existing, err := os.ReadFile(path); err == nil {
		if !bytes.Equal(existing, source.Bytes()) {
			return "", "", fmt.Errorf("cached Solidity V2 verifier does not match FinalBNV2 VK")
		}
	} else if os.IsNotExist(err) {
		if err := writeBytesNew(path, source.Bytes()); err != nil {
			return "", "", err
		}
	} else {
		return "", "", err
	}
	return path, hashBytes(source.Bytes()), nil
}

func writeFinalArtifactV2(artifactDir string, batch *pcd.PreparedObserverBatchV2, quorum uint32, proof groth16.Proof, public witness.Witness, verifierPath, verifierHash string) error {
	proofBytes, ok := proof.(interface{ MarshalSolidity() []byte })
	if !ok {
		return fmt.Errorf("FinalBNV2 proof has no Solidity encoding")
	}
	publicSignals, err := pcdPublicInputs(public)
	if err != nil {
		return err
	}
	if len(publicSignals) != len(batch.FinalStatement) {
		return fmt.Errorf("FinalBNV2 proof exposes %d public signals, expected %d", len(publicSignals), len(batch.FinalStatement))
	}
	for i := range publicSignals {
		if publicSignals[i] != batch.FinalStatement[i].String() {
			return fmt.Errorf("FinalBNV2 public input %d=%s, expected %s", i, publicSignals[i], batch.FinalStatement[i])
		}
	}
	solidityProof := proofBytes.MarshalSolidity()
	proofHash := sha256.Sum256(solidityProof)
	identity, err := json.Marshal(struct {
		Domain          string   `json:"domain"`
		ProtocolVersion int      `json:"protocolVersion"`
		MinimumQuorum   uint32   `json:"minimumQuorum"`
		PublicInputs    []string `json:"publicInputs"`
		VerifierSHA256  string   `json:"verifierSha256"`
		ProofSHA256     string   `json:"proofSha256"`
	}{"pcd3-final-artifact-v2", 2, quorum, publicSignals, verifierHash, hex.EncodeToString(proofHash[:])})
	if err != nil {
		return fmt.Errorf("encode final V2 artifact identity: %w", err)
	}
	name := "session-" + hashBytes(identity)
	outDir := filepath.Join(artifactDir, "proofs-v2", name)
	verifierRelativePath, err := filepath.Rel(outDir, verifierPath)
	if err != nil {
		return fmt.Errorf("compute V2 verifier path relative to final artifact: %w", err)
	}
	artifact := finalArtifact{
		ProtocolVersion: 2, MinimumQuorum: quorum,
		Proof: "0x" + hex.EncodeToString(solidityProof), PublicInputs: publicSignals,
		VerifierSource: verifierRelativePath, VerifierSHA256: verifierHash,
	}
	artifactBytes, err := json.MarshalIndent(artifact, "", "  ")
	if err != nil {
		return fmt.Errorf("encode final V2 proof artifact: %w", err)
	}
	artifactBytes = append(artifactBytes, '\n')
	if err := publishArtifactDirectory(outDir, map[string][]byte{
		"final-proof-v2.json": artifactBytes,
		"proof-sha256.txt":    []byte(hex.EncodeToString(proofHash[:]) + "\n"),
	}); err != nil {
		return err
	}
	fmt.Printf("Final V2 proof verified; Solidity verifier: %s\n", verifierPath)
	fmt.Printf("Final V2 proof artifact: %s\n", filepath.Join(outDir, "final-proof-v2.json"))
	return nil
}
