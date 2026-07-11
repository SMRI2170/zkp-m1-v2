package membership

import (
	"math/big"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark-crypto/hash"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/test"
)

// MiMC_BN254 でハッシュ（回路内 mimc.Write(...).Sum() と一致させる）。
func mimcHash(elems ...*big.Int) *big.Int {
	h := hash.MIMC_BN254.New()
	buf := make([]byte, 32)
	for _, e := range elems {
		e.FillBytes(buf)
		h.Write(buf)
	}
	var out big.Int
	out.SetBytes(h.Sum(nil))
	return &out
}

// leaves(2^Depth)からルートと各インデックスのパスを計算する。
func buildTree(leaves []*big.Int) (root *big.Int, siblings [][]*big.Int, bits [][]int) {
	size := 1 << Depth
	level := make([]*big.Int, size)
	for i := 0; i < size; i++ {
		if i < len(leaves) {
			level[i] = leaves[i]
		} else {
			level[i] = big.NewInt(0) // 空きは 0 パディング
		}
	}
	siblings = make([][]*big.Int, size)
	bits = make([][]int, size)
	for i := 0; i < size; i++ {
		siblings[i] = make([]*big.Int, Depth)
		bits[i] = make([]int, Depth)
	}
	cur := level
	for d := 0; d < Depth; d++ {
		next := make([]*big.Int, len(cur)/2)
		for i := 0; i < size; i++ {
			pairIdx := i >> d
			b := pairIdx & 1
			bits[i][d] = b
			if b == 0 {
				siblings[i][d] = cur[pairIdx+1] // 自分は左 → 兄弟は右
			} else {
				siblings[i][d] = cur[pairIdx-1]
			}
		}
		for j := 0; j < len(next); j++ {
			next[j] = mimcHash(cur[2*j], cur[2*j+1])
		}
		cur = next
	}
	return cur[0], siblings, bits
}

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
		leaves[i] = mimcHash(d.ax, d.ay)
	}
	root, siblings, bits := buildTree(leaves)

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
