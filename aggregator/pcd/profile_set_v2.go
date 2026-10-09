package pcd

import (
	"fmt"
	"math/big"
	"sort"

	"uav/aggregator/membership"
)

type calibrationProfilePathV2 struct {
	Siblings [membership.Depth]*big.Int
	Bits     [membership.Depth]int
}

// buildCalibrationProfileSetV2 canonicalizes an allowlist and derives a
// domain-separated MiMC Merkle root plus one membership opening per profile.
// The fixed-depth tree supports at most 16 immutable profile IDs.
func buildCalibrationProfileSetV2(profileIDs []*big.Int) (*big.Int, map[string]calibrationProfilePathV2, error) {
	ids, err := canonicalCalibrationProfileIDsV2(profileIDs)
	if err != nil {
		return nil, nil, err
	}

	leaves := make([]*big.Int, len(ids))
	for i, id := range ids {
		leaves[i] = membership.MimcHash(finalPolicyV2ProfileDomain, id)
	}
	root, siblings, bits := membership.BuildTree(leaves)
	paths := make(map[string]calibrationProfilePathV2, len(ids))
	for i, id := range ids {
		path := calibrationProfilePathV2{}
		for depth := 0; depth < membership.Depth; depth++ {
			path.Siblings[depth] = new(big.Int).Set(siblings[i][depth])
			path.Bits[depth] = bits[i][depth]
		}
		paths[id.String()] = path
	}
	return new(big.Int).Set(root), paths, nil
}

func canonicalCalibrationProfileIDsV2(profileIDs []*big.Int) ([]*big.Int, error) {
	if len(profileIDs) == 0 || len(profileIDs) > 1<<membership.Depth {
		return nil, fmt.Errorf("calibration profile set must contain 1..%d IDs", 1<<membership.Depth)
	}
	ids := make([]*big.Int, len(profileIDs))
	seen := make(map[string]struct{}, len(profileIDs))
	for i, id := range profileIDs {
		if !canonicalBN254(id) || id.BitLen() > 32 {
			return nil, fmt.Errorf("calibration profile %d is not a canonical uint32", i)
		}
		key := id.String()
		if _, duplicate := seen[key]; duplicate {
			return nil, fmt.Errorf("calibration profile %s is duplicated", key)
		}
		seen[key] = struct{}{}
		ids[i] = new(big.Int).Set(id)
	}
	sort.Slice(ids, func(i, j int) bool { return ids[i].Cmp(ids[j]) < 0 })
	return ids, nil
}

func calibrationProfilePathRootV2(profileID *big.Int, path calibrationProfilePathV2) (*big.Int, error) {
	if !canonicalBN254(profileID) || profileID.BitLen() > 32 {
		return nil, fmt.Errorf("calibration profile ID must be a canonical uint32")
	}
	current := membership.MimcHash(finalPolicyV2ProfileDomain, profileID)
	for depth := 0; depth < membership.Depth; depth++ {
		sibling := path.Siblings[depth]
		if !canonicalBN254(sibling) {
			return nil, fmt.Errorf("calibration profile sibling %d is not canonical", depth)
		}
		if path.Bits[depth] != 0 && path.Bits[depth] != 1 {
			return nil, fmt.Errorf("calibration profile path bit %d is not boolean", depth)
		}
		if path.Bits[depth] == 0 {
			current = membership.MimcHash(current, sibling)
		} else {
			current = membership.MimcHash(sibling, current)
		}
	}
	return current, nil
}
