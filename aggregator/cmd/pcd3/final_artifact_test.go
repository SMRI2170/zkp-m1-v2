package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPublishArtifactDirectoryIsAtomicAndIdempotent(t *testing.T) {
	root := t.TempDir()
	outDir := filepath.Join(root, "proofs-v2", "session-test")
	want := map[string][]byte{
		"final-proof-v2.json": []byte("{\"proof\":\"0x1234\"}\n"),
		"proof-sha256.txt":    []byte("abcd\n"),
	}
	if err := publishArtifactDirectory(outDir, want); err != nil {
		t.Fatalf("publish artifact directory: %v", err)
	}
	if err := verifyArtifactDirectory(outDir, want); err != nil {
		t.Fatalf("verify complete artifact directory: %v", err)
	}
	entries, err := os.ReadDir(filepath.Dir(outDir))
	if err != nil {
		t.Fatalf("list artifact parent: %v", err)
	}
	if len(entries) != 1 || entries[0].Name() != "session-test" {
		t.Fatalf("artifact parent contains temporary or unexpected entries: %v", entries)
	}
	for name := range want {
		info, err := os.Stat(filepath.Join(outDir, name))
		if err != nil {
			t.Fatalf("stat published artifact %q: %v", name, err)
		}
		if info.Mode().Perm() != 0o600 {
			t.Errorf("published artifact %q mode = %04o, want 0600", name, info.Mode().Perm())
		}
	}
	if err := publishArtifactDirectory(outDir, want); err != nil {
		t.Fatalf("identical publish should be idempotent: %v", err)
	}
}

func TestPublishArtifactDirectoryPreservesAlteredAndPartialOutput(t *testing.T) {
	t.Run("altered output", func(t *testing.T) {
		root := t.TempDir()
		outDir := filepath.Join(root, "proofs-v2", "session-test")
		want := map[string][]byte{"final-proof-v2.json": []byte("expected\n"), "proof-sha256.txt": []byte("hash\n")}
		if err := publishArtifactDirectory(outDir, want); err != nil {
			t.Fatal(err)
		}
		proofPath := filepath.Join(outDir, "final-proof-v2.json")
		if err := os.WriteFile(proofPath, []byte("altered\n"), 0o600); err != nil {
			t.Fatal(err)
		}
		if err := publishArtifactDirectory(outDir, want); err == nil || !strings.Contains(err.Error(), "differs from expected content") {
			t.Fatalf("altered output was accepted: %v", err)
		}
		got, err := os.ReadFile(proofPath)
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(got, []byte("altered\n")) {
			t.Fatalf("altered output was overwritten: %q", got)
		}
	})

	t.Run("partial output", func(t *testing.T) {
		root := t.TempDir()
		outDir := filepath.Join(root, "proofs-v2", "session-test")
		if err := os.MkdirAll(outDir, 0o700); err != nil {
			t.Fatal(err)
		}
		partialPath := filepath.Join(outDir, "final-proof-v2.json")
		if err := os.WriteFile(partialPath, []byte("partial\n"), 0o600); err != nil {
			t.Fatal(err)
		}
		want := map[string][]byte{"final-proof-v2.json": []byte("complete\n"), "proof-sha256.txt": []byte("hash\n")}
		if err := publishArtifactDirectory(outDir, want); err == nil || !strings.Contains(err.Error(), "expected 2") {
			t.Fatalf("partial output was accepted: %v", err)
		}
		got, err := os.ReadFile(partialPath)
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(got, []byte("partial\n")) {
			t.Fatalf("partial output was overwritten: %q", got)
		}
	})
}
