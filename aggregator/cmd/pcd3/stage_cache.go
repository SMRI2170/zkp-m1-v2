package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// recoverStageCache publishes a fully written temporary stage after verifying
// it. Incomplete or stale temporary directories are deliberately preserved;
// they are never trusted as cache entries and are not deleted automatically.
func recoverStageCache(
	setupDir, name, stageDir string,
	validate func(string) (stageArtifacts, error),
) (stageArtifacts, bool, error) {
	entries, err := os.ReadDir(setupDir)
	if err != nil {
		return stageArtifacts{}, false, err
	}
	prefix := "." + name + ".tmp-"
	for _, entry := range entries {
		if !strings.HasPrefix(entry.Name(), prefix) {
			continue
		}
		info, err := entry.Info()
		if err != nil {
			if os.IsNotExist(err) {
				continue
			}
			return stageArtifacts{}, false, err
		}
		if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
			continue
		}

		tempDir := filepath.Join(setupDir, entry.Name())
		cached, err := validate(tempDir)
		if err != nil {
			fmt.Fprintf(os.Stderr, "[%s] keeping unverified temporary cache %q (not reused): %v\n", name, tempDir, err)
			continue
		}
		if err := os.Rename(tempDir, stageDir); err != nil {
			// A concurrent invocation can publish the same stage first. Accept
			// that only if the winner's cache passes the same integrity checks.
			if info, statErr := os.Lstat(stageDir); statErr == nil && info.IsDir() && info.Mode()&os.ModeSymlink == 0 {
				winner, validateErr := validate(stageDir)
				if validateErr == nil {
					winner.Dir = stageDir
					return winner, true, nil
				}
			}
			return stageArtifacts{}, false, fmt.Errorf("publish recovered %s stage cache: %w", name, err)
		}
		cached.Dir = stageDir
		fmt.Printf("[%s] recovered verified cache from interrupted publication\n", name)
		return cached, true, nil
	}
	return stageArtifacts{}, false, nil
}
