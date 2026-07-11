package membership

import (
	"math/big"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/test"
)

func toVars(xs []*big.Int) [Depth]frontend.Variable {
	var out [Depth]frontend.Variable
	for i := 0; i < Depth; i++ {
		out[i] = xs[i]
	}
	return out
}

func intsToVars(xs []int) [Depth]frontend.Variable {
	var out [Depth]frontend.Variable
	for i := 0; i < Depth; i++ {
		out[i] = xs[i]
	}
	return out
}

func TestMembership(t *testing.T) {
	assert := test.NewAssert(t)

	// 登録端末 5 台（それぞれ device_pubkey = (ax, ay)）
	type dev struct{ ax, ay *big.Int }
	devs := []dev{
		{big.NewInt(1001), big.NewInt(2001)},
		{big.NewInt(1002), big.NewInt(2002)},
		{big.NewInt(1003), big.NewInt(2003)},
		{big.NewInt(1004), big.NewInt(2004)},
		{big.NewInt(1005), big.NewInt(2005)},
	}
	leaves := make([]*big.Int, len(devs))
	for i, d := range devs {
		leaves[i] = MimcHash(d.ax, d.ay)
	}
	root, siblings, bits := BuildTree(leaves)

	// 集約する 3 台（インデックス 0,1,2）は登録済み → 通るはず
	valid := &Circuit{Root: root}
	for i := 0; i < N; i++ {
		valid.Ax[i] = devs[i].ax
		valid.Ay[i] = devs[i].ay
		valid.Siblings[i] = toVars(siblings[i])
		valid.PathBits[i] = intsToVars(bits[i])
	}
	assert.SolvingSucceeded(&Circuit{}, valid, test.WithCurves(ecc.BN254))

	// 未登録端末（ax を偽装）を混ぜる → メンバーシップ検証が失敗するはず
	bad := &Circuit{Root: root}
	*bad = *valid
	bad.Ax[2] = big.NewInt(999999) // 登録されていない鍵（パスは dev2 のまま）
	assert.SolvingFailed(&Circuit{}, bad, test.WithCurves(ecc.BN254))
}
