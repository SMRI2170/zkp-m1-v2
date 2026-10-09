package pcd

import (
	"math/big"
	"testing"
)

func TestCalibrationProfileSetV2MerkleOpenings(t *testing.T) {
	ids := []*big.Int{big.NewInt(31), big.NewInt(7), big.NewInt(12)}
	root, paths, err := buildCalibrationProfileSetV2(ids)
	if err != nil {
		t.Fatal(err)
	}
	reversedRoot, _, err := buildCalibrationProfileSetV2([]*big.Int{big.NewInt(12), big.NewInt(31), big.NewInt(7)})
	if err != nil {
		t.Fatal(err)
	}
	if root.Cmp(reversedRoot) != 0 {
		t.Fatal("profile set root depends on caller ordering")
	}
	for _, id := range ids {
		path, ok := paths[id.String()]
		if !ok {
			t.Fatalf("profile %s has no derived membership path", id)
		}
		opened, err := calibrationProfilePathRootV2(id, path)
		if err != nil {
			t.Fatal(err)
		}
		if opened.Cmp(root) != 0 {
			t.Fatalf("profile %s opened root %s, want %s", id, opened, root)
		}
	}

	badPath := paths["7"]
	badPath.Siblings[0].Add(badPath.Siblings[0], big.NewInt(1))
	opened, err := calibrationProfilePathRootV2(big.NewInt(7), badPath)
	if err != nil {
		t.Fatal(err)
	}
	if opened.Cmp(root) == 0 {
		t.Fatal("tampered profile sibling opened the approved set root")
	}
}

func TestCalibrationProfileSetV2SingleProfileVector(t *testing.T) {
	root, _, err := buildCalibrationProfileSetV2([]*big.Int{big.NewInt(1)})
	if err != nil {
		t.Fatal(err)
	}
	const want = "11903723632731301064031894262307537750160534275783405584132746318593138032559"
	if root.String() != want {
		t.Fatalf("single-profile depth-4 MiMC root = %s, want frozen vector %s", root, want)
	}
}

func TestCalibrationProfileSetV2RejectsMalformedSets(t *testing.T) {
	tooMany := make([]*big.Int, 1<<4+1)
	for i := range tooMany {
		tooMany[i] = new(big.Int).SetInt64(int64(i))
	}
	for name, ids := range map[string][]*big.Int{
		"empty":       nil,
		"duplicate":   {big.NewInt(1), big.NewInt(1)},
		"negative":    {big.NewInt(-1)},
		"oversized":   {new(big.Int).Lsh(big.NewInt(1), 32)},
		"too many":    tooMany,
		"nil profile": {nil},
	} {
		t.Run(name, func(t *testing.T) {
			if _, _, err := buildCalibrationProfileSetV2(ids); err == nil {
				t.Fatal("malformed profile set was accepted")
			}
		})
	}
}
