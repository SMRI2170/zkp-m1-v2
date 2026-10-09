package main

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend"
	groth16 "github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/solidity"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/frontend"
	recursion "github.com/consensys/gnark/std/recursion/groth16"
)

const proofCacheVersion = 1

type proofCacheMetadata struct {
	Version             int    `json:"version"`
	Label               string `json:"label"`
	CircuitStage        string `json:"circuitStage"`
	Curve               string `json:"curve"`
	InnerCurve          string `json:"innerCurve"`
	SolidityTarget      bool   `json:"solidityTarget"`
	SourceHash          string `json:"sourceHash"`
	ConstraintHash      string `json:"constraintHash"`
	VerifyingKeyHash    string `json:"verifyingKeyHash"`
	AssignmentSHA256    string `json:"assignmentSha256"`
	PublicWitnessSHA256 string `json:"publicWitnessSha256"`
	ProofSHA256         string `json:"proofSha256"`
}

// proveAndVerifyCached persists only the proof and public witness. The private
// assignment is hashed in memory and is never written to disk. Cache identity
// binds the complete serialized assignment to the exact circuit source and VK.
func proveAndVerifyCached(
	artifactDir, label string,
	stage stageArtifacts,
	assignment frontend.Circuit,
	outerCurve, innerCurve ecc.ID,
	solidityTarget bool,
) (groth16.Proof, witness.Witness, error) {
	if !safeProofCacheLabel(label) {
		return nil, nil, fmt.Errorf("unsafe proof-cache label %q", label)
	}
	if stage.VK == nil || stage.VK.CurveID() != outerCurve {
		return nil, nil, fmt.Errorf("%s proof cache curve does not match its verifying key", label)
	}
	if stage.Meta.Curve != curveName(outerCurve) {
		return nil, nil, fmt.Errorf("%s proof cache metadata curve does not match the proving stage", label)
	}
	actualVKHash, err := fileHashFromWriter(stage.VK)
	if err != nil {
		return nil, nil, fmt.Errorf("%s proving-stage VK fingerprint: %w", label, err)
	}
	if actualVKHash != stage.Meta.VerifyingKeyHash {
		return nil, nil, fmt.Errorf("%s proving-stage VK does not match its cached metadata", label)
	}
	fullWitness, err := frontend.NewWitness(assignment, outerCurve.ScalarField())
	if err != nil {
		return nil, nil, fmt.Errorf("%s witness: %w", label, err)
	}
	public, err := fullWitness.Public()
	if err != nil {
		return nil, nil, fmt.Errorf("%s public witness: %w", label, err)
	}
	assignmentHash, err := fileHashFromWriter(fullWitness)
	if err != nil {
		return nil, nil, fmt.Errorf("%s assignment fingerprint: %w", label, err)
	}
	publicHash, err := fileHashFromWriter(public)
	if err != nil {
		return nil, nil, fmt.Errorf("%s public-witness fingerprint: %w", label, err)
	}
	cacheKey := proofCacheKey(label, stage, outerCurve, innerCurve, solidityTarget, assignmentHash)
	cacheDir := proofCacheDirectory(artifactDir, label, cacheKey)
	if err := ensurePrivateProofCacheAncestors(cacheDir); err != nil {
		return nil, nil, err
	}

	if info, err := os.Lstat(cacheDir); err == nil {
		if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
			return nil, nil, fmt.Errorf("proof cache path %q is not a regular directory", cacheDir)
		}
		return loadProofCache(cacheDir, label, stage, outerCurve, innerCurve, solidityTarget, assignmentHash, publicHash)
	} else if !errors.Is(err, os.ErrNotExist) {
		return nil, nil, err
	}

	proof, public, err := proveAndVerifyWitness(label, stage, fullWitness, public, outerCurve, innerCurve, solidityTarget)
	if err != nil {
		return nil, nil, err
	}
	if err := saveProofCache(cacheDir, label, stage, outerCurve, innerCurve, solidityTarget, assignmentHash, publicHash, proof, public); err != nil {
		// A concurrent invocation may have published the same assignment cache.
		// Accept it only after the complete cache passes all integrity checks.
		if info, statErr := os.Lstat(cacheDir); statErr == nil && info.IsDir() && info.Mode()&os.ModeSymlink == 0 {
			return loadProofCache(cacheDir, label, stage, outerCurve, innerCurve, solidityTarget, assignmentHash, publicHash)
		}
		return nil, nil, err
	}
	return proof, public, nil
}

func proofCacheKey(label string, stage stageArtifacts, outerCurve, innerCurve ecc.ID, solidityTarget bool, assignmentHash string) string {
	h := sha256.New()
	for _, value := range []string{
		"pcd3-proof-cache-v1",
		label,
		stage.Meta.Stage,
		curveName(outerCurve),
		curveName(innerCurve),
		stage.Meta.SourceHash,
		stage.Meta.ConstraintHash,
		stage.Meta.VerifyingKeyHash,
		fmt.Sprintf("solidity-target=%t", solidityTarget),
		assignmentHash,
	} {
		_, _ = h.Write([]byte(value))
		_, _ = h.Write([]byte{0})
	}
	return hex.EncodeToString(h.Sum(nil))
}

func proofCacheDirectory(artifactDir, label, key string) string {
	return filepath.Join(artifactDir, "proof-cache-v1", label, key)
}

func safeProofCacheLabel(label string) bool {
	if label == "" || label == "." || label == ".." || strings.ContainsAny(label, `/\\`) {
		return false
	}
	return true
}

func saveProofCache(
	cacheDir, label string,
	stage stageArtifacts,
	outerCurve, innerCurve ecc.ID,
	solidityTarget bool,
	assignmentHash, publicHash string,
	proof groth16.Proof,
	public witness.Witness,
) error {
	parent := filepath.Dir(cacheDir)
	if err := ensurePrivateProofCacheAncestors(cacheDir); err != nil {
		return err
	}
	tempDir, err := os.MkdirTemp(parent, ".proof.tmp-")
	if err != nil {
		return err
	}
	if err := writeBinaryNew(filepath.Join(tempDir, "proof.bin"), proof); err != nil {
		return fmt.Errorf("save proof cache in preserved temporary directory %q: %w", tempDir, err)
	}
	if err := writeBinaryNew(filepath.Join(tempDir, "public.witness"), public); err != nil {
		return fmt.Errorf("save public-witness cache in preserved temporary directory %q: %w", tempDir, err)
	}
	proofHash, err := fileHash(filepath.Join(tempDir, "proof.bin"))
	if err != nil {
		return err
	}
	storedPublicHash, err := fileHash(filepath.Join(tempDir, "public.witness"))
	if err != nil {
		return err
	}
	if storedPublicHash != publicHash {
		return fmt.Errorf("public witness changed while saving proof cache")
	}
	meta := proofCacheMetadata{
		Version: proofCacheVersion, Label: label, CircuitStage: stage.Meta.Stage,
		Curve: curveName(outerCurve), InnerCurve: curveName(innerCurve), SolidityTarget: solidityTarget,
		SourceHash:     stage.Meta.SourceHash,
		ConstraintHash: stage.Meta.ConstraintHash, VerifyingKeyHash: stage.Meta.VerifyingKeyHash,
		AssignmentSHA256: assignmentHash, PublicWitnessSHA256: publicHash, ProofSHA256: proofHash,
	}
	if err := writeJSONNew(filepath.Join(tempDir, "cache.json"), meta); err != nil {
		return fmt.Errorf("save proof-cache metadata in preserved temporary directory %q: %w", tempDir, err)
	}
	if err := os.Rename(tempDir, cacheDir); err != nil {
		return fmt.Errorf("publish proof cache: %w (complete temporary cache preserved at %q)", err, tempDir)
	}
	return nil
}

func loadProofCache(
	cacheDir, label string,
	stage stageArtifacts,
	outerCurve, innerCurve ecc.ID,
	solidityTarget bool,
	assignmentHash, publicHash string,
) (groth16.Proof, witness.Witness, error) {
	if err := ensurePrivateProofCacheAncestors(cacheDir); err != nil {
		return nil, nil, err
	}
	if err := ensureOwnerOnlyDirectory(cacheDir); err != nil {
		return nil, nil, err
	}
	var meta proofCacheMetadata
	if err := readJSON(filepath.Join(cacheDir, "cache.json"), &meta); err != nil {
		return nil, nil, fmt.Errorf("incomplete proof cache %q; preserve it and use a new artifact directory or inspect it: %w", cacheDir, err)
	}
	if meta.Version != proofCacheVersion || meta.Label != label || meta.CircuitStage != stage.Meta.Stage ||
		meta.Curve != curveName(outerCurve) || meta.InnerCurve != curveName(innerCurve) ||
		meta.SolidityTarget != solidityTarget || meta.SourceHash != stage.Meta.SourceHash ||
		meta.ConstraintHash != stage.Meta.ConstraintHash || meta.VerifyingKeyHash != stage.Meta.VerifyingKeyHash ||
		meta.AssignmentSHA256 != assignmentHash || meta.PublicWitnessSHA256 != publicHash {
		return nil, nil, fmt.Errorf("cached %s proof metadata does not match current source, VK, or assignment; use a new artifact directory", label)
	}
	if err := verifyFileHash(filepath.Join(cacheDir, "proof.bin"), meta.ProofSHA256); err != nil {
		return nil, nil, err
	}
	if err := verifyFileHash(filepath.Join(cacheDir, "public.witness"), meta.PublicWitnessSHA256); err != nil {
		return nil, nil, err
	}
	proof := groth16.NewProof(outerCurve)
	public, err := witness.New(outerCurve.ScalarField())
	if err != nil {
		return nil, nil, err
	}
	if err := readBinary(filepath.Join(cacheDir, "proof.bin"), proof); err != nil {
		return nil, nil, fmt.Errorf("read cached %s proof: %w", label, err)
	}
	if err := readBinary(filepath.Join(cacheDir, "public.witness"), public); err != nil {
		return nil, nil, fmt.Errorf("read cached %s public witness: %w", label, err)
	}
	if proof.CurveID() != outerCurve {
		return nil, nil, fmt.Errorf("cached %s proof is on curve %s, expected %s", label, proof.CurveID(), outerCurve)
	}
	verifierOptions := []backend.VerifierOption{recursion.GetNativeVerifierOptions(outerCurve.ScalarField(), innerCurve.ScalarField())}
	if solidityTarget {
		verifierOptions = append(verifierOptions, solidity.WithVerifierTargetSolidityVerifier(backend.GROTH16))
	}
	if err := groth16.Verify(proof, stage.VK, public, verifierOptions...); err != nil {
		return nil, nil, fmt.Errorf("cached %s proof failed native verification: %w", label, err)
	}
	fmt.Printf("[%s] loaded verified proof cache\n", label)
	return proof, public, nil
}

func ensurePrivateProofCacheAncestors(cacheDir string) error {
	labelDir := filepath.Dir(cacheDir)
	rootDir := filepath.Dir(labelDir)
	if err := ensureOwnerOnlyDirectory(rootDir); err != nil {
		return err
	}
	return ensureOwnerOnlyDirectory(labelDir)
}

func ensureOwnerOnlyDirectory(path string) error {
	if _, err := os.Lstat(path); errors.Is(err, os.ErrNotExist) {
		if err := os.MkdirAll(path, 0o700); err != nil {
			return err
		}
	} else if err != nil {
		return err
	}
	info, err := os.Lstat(path)
	if err != nil {
		return err
	}
	if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("path %q is not a regular directory", path)
	}
	if info.Mode().Perm()&0o077 != 0 {
		return fmt.Errorf("directory %q must be owner-only (mode 0700)", path)
	}
	return nil
}
