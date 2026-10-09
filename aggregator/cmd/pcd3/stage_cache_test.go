package main

import (
	"errors"
	"os"
	"path/filepath"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	groth16 "github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
)

type tinyStageCacheCircuit struct {
	Value frontend.Variable `gnark:",public"`
}

func (c *tinyStageCacheCircuit) Define(api frontend.API) error {
	api.AssertIsEqual(c.Value, 1)
	return nil
}

func TestRecoverStageCachePublishesOnlyValidatedCompleteCache(t *testing.T) {
	setupDir := t.TempDir()
	partialDir := filepath.Join(setupDir, ".bridge-bw.tmp-partial")
	completeDir := filepath.Join(setupDir, ".bridge-bw.tmp-complete")
	stageDir := filepath.Join(setupDir, "bridge-bw")
	for _, dir := range []string{partialDir, completeDir} {
		if err := os.Mkdir(dir, 0o700); err != nil {
			t.Fatalf("create temp stage %q: %v", dir, err)
		}
	}
	if err := os.WriteFile(filepath.Join(completeDir, "complete.marker"), []byte("verified"), 0o600); err != nil {
		t.Fatalf("write complete-stage marker: %v", err)
	}

	validate := func(dir string) (stageArtifacts, error) {
		marker, err := os.ReadFile(filepath.Join(dir, "complete.marker"))
		if err != nil {
			return stageArtifacts{}, err
		}
		if string(marker) != "verified" {
			return stageArtifacts{}, os.ErrInvalid
		}
		return stageArtifacts{Dir: dir, Meta: stageMetadata{Stage: "bridge-bw"}}, nil
	}

	got, recovered, err := recoverStageCache(setupDir, "bridge-bw", stageDir, validate)
	if err != nil {
		t.Fatalf("recover complete stage: %v", err)
	}
	if !recovered {
		t.Fatal("complete temporary cache was not recovered")
	}
	if got.Dir != stageDir || got.Meta.Stage != "bridge-bw" {
		t.Fatalf("recovered stage = %#v, want published cache at %q", got, stageDir)
	}
	if _, err := os.Stat(filepath.Join(stageDir, "complete.marker")); err != nil {
		t.Fatalf("published cache is missing marker: %v", err)
	}
	if _, err := os.Stat(partialDir); err != nil {
		t.Fatalf("unvalidated partial cache should be preserved for inspection: %v", err)
	}
	if _, err := os.Stat(completeDir); !os.IsNotExist(err) {
		t.Fatalf("validated temporary cache should have been moved, stat err=%v", err)
	}
}

func TestRecoverStageCacheLeavesInvalidCacheUntouched(t *testing.T) {
	setupDir := t.TempDir()
	partialDir := filepath.Join(setupDir, ".node-bw.tmp-partial")
	stageDir := filepath.Join(setupDir, "node-bw")
	if err := os.Mkdir(partialDir, 0o700); err != nil {
		t.Fatalf("create partial stage: %v", err)
	}
	validate := func(dir string) (stageArtifacts, error) {
		return stageArtifacts{}, errors.New("incomplete cache")
	}

	_, recovered, err := recoverStageCache(setupDir, "node-bw", stageDir, validate)
	if err != nil {
		t.Fatalf("scan incomplete cache: %v", err)
	}
	if recovered {
		t.Fatal("incomplete cache was incorrectly recovered")
	}
	if _, err := os.Stat(partialDir); err != nil {
		t.Fatalf("incomplete cache was removed: %v", err)
	}
	if _, err := os.Stat(stageDir); !os.IsNotExist(err) {
		t.Fatalf("incomplete cache created a published directory: stat err=%v", err)
	}
}

func TestRecoverStageCacheRejectsTamperedSetupKey(t *testing.T) {
	ccs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &tinyStageCacheCircuit{})
	if err != nil {
		t.Fatalf("compile tiny cache test circuit: %v", err)
	}
	pk, vk, err := groth16.Setup(ccs)
	if err != nil {
		t.Fatalf("setup tiny cache test circuit: %v", err)
	}

	setupDir := t.TempDir()
	invalidDir := filepath.Join(setupDir, ".tiny-stage.tmp-a-invalid")
	validDir := filepath.Join(setupDir, ".tiny-stage.tmp-b-valid")
	stageDir := filepath.Join(setupDir, "tiny-stage")
	if err := os.Mkdir(invalidDir, 0o700); err != nil {
		t.Fatalf("create invalid temp cache: %v", err)
	}
	if _, err := saveStage(invalidDir, "tiny-stage", ecc.BN254, "source", map[string]string{"input": "hash"}, ccs, pk, vk); err != nil {
		t.Fatalf("write invalid temp cache: %v", err)
	}
	if err := os.WriteFile(filepath.Join(invalidDir, "proving.key"), []byte("tampered"), 0o600); err != nil {
		t.Fatalf("tamper test proving key: %v", err)
	}
	if err := os.Mkdir(validDir, 0o700); err != nil {
		t.Fatalf("create valid temp cache: %v", err)
	}
	if _, err := saveStage(validDir, "tiny-stage", ecc.BN254, "source", map[string]string{"input": "hash"}, ccs, pk, vk); err != nil {
		t.Fatalf("write valid temp cache: %v", err)
	}

	validate := func(dir string) (stageArtifacts, error) {
		return loadStage(dir, "tiny-stage", ecc.BN254, "source", map[string]string{"input": "hash"})
	}
	got, recovered, err := recoverStageCache(setupDir, "tiny-stage", stageDir, validate)
	if err != nil {
		t.Fatalf("recover verified setup cache: %v", err)
	}
	if !recovered || got.Dir != stageDir {
		t.Fatalf("recovery result = recovered %v at %q, want published verified cache %q", recovered, got.Dir, stageDir)
	}
	if _, err := os.Stat(invalidDir); err != nil {
		t.Fatalf("tampered cache should be preserved for inspection: %v", err)
	}
	if err := verifyFileHash(filepath.Join(stageDir, "proving.key"), got.Meta.ProvingKeyHash); err != nil {
		t.Fatalf("published proving key failed integrity check: %v", err)
	}
}
