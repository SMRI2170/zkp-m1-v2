package main

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// publishArtifactDirectory exposes a complete generated artifact directory in
// one rename. Existing output is accepted only when it is the exact same set
// of regular files and bytes; partial or altered output is preserved and
// rejected so a resume cannot silently replace evidence.
func publishArtifactDirectory(outDir string, files map[string][]byte) error {
	if len(files) == 0 {
		return fmt.Errorf("refusing to publish an empty artifact directory")
	}
	for name := range files {
		if name == "" || name == "." || name == ".." || filepath.Base(name) != name || strings.ContainsAny(name, `/\\`) {
			return fmt.Errorf("unsafe artifact filename %q", name)
		}
	}
	parent := filepath.Dir(outDir)
	if err := ensureOwnerOnlyDirectory(parent); err != nil {
		return err
	}
	if _, err := os.Lstat(outDir); err == nil {
		return verifyArtifactDirectory(outDir, files)
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}

	tempDir, err := os.MkdirTemp(parent, ".artifact.tmp-")
	if err != nil {
		return err
	}
	names := make([]string, 0, len(files))
	for name := range files {
		names = append(names, name)
	}
	sort.Strings(names)
	for _, name := range names {
		if err := writeBytesNew(filepath.Join(tempDir, name), files[name]); err != nil {
			return fmt.Errorf("write artifact in preserved temporary directory %q: %w", tempDir, err)
		}
	}
	if err := syncDirectory(tempDir); err != nil {
		return fmt.Errorf("sync complete artifact in preserved temporary directory %q: %w", tempDir, err)
	}
	if err := os.Rename(tempDir, outDir); err != nil {
		// Another identical invocation may have published the same content.
		// Only that exact complete result is safe to accept.
		if _, statErr := os.Lstat(outDir); statErr == nil {
			if verifyErr := verifyArtifactDirectory(outDir, files); verifyErr == nil {
				return nil
			} else {
				return fmt.Errorf("publish artifact directory %q: %w (complete temporary output preserved at %q)", outDir, verifyErr, tempDir)
			}
		}
		return fmt.Errorf("publish artifact directory %q: %w (complete temporary output preserved at %q)", outDir, err, tempDir)
	}
	if err := syncDirectory(parent); err != nil {
		return fmt.Errorf("artifact directory %q was published but parent sync failed: %w", outDir, err)
	}
	return nil
}

func verifyArtifactDirectory(outDir string, expected map[string][]byte) error {
	if err := ensureOwnerOnlyDirectory(outDir); err != nil {
		return fmt.Errorf("existing artifact output is not safe to reuse: %w", err)
	}
	entries, err := os.ReadDir(outDir)
	if err != nil {
		return err
	}
	if len(entries) != len(expected) {
		return fmt.Errorf("existing artifact directory %q has %d entries; expected %d (preserving it)", outDir, len(entries), len(expected))
	}
	for _, entry := range entries {
		name := entry.Name()
		want, ok := expected[name]
		if !ok {
			return fmt.Errorf("existing artifact directory %q contains unexpected entry %q (preserving it)", outDir, name)
		}
		path := filepath.Join(outDir, name)
		info, err := os.Lstat(path)
		if err != nil {
			return err
		}
		if !info.Mode().IsRegular() || info.Mode().Perm()&0o077 != 0 {
			return fmt.Errorf("existing artifact file %q is not a private regular file (preserving it)", path)
		}
		got, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		if !bytes.Equal(got, want) {
			return fmt.Errorf("existing artifact file %q differs from expected content (preserving it)", path)
		}
	}
	return nil
}

func syncDirectory(path string) error {
	dir, err := os.Open(path)
	if err != nil {
		return err
	}
	syncErr := dir.Sync()
	closeErr := dir.Close()
	if syncErr != nil {
		return syncErr
	}
	return closeErr
}
