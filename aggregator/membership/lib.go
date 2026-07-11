package membership

import (
	"math/big"

	"github.com/consensys/gnark-crypto/hash"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/hash/mimc"
)

// ── 回路内（in-circuit）─────────────────────────────────────────────────────

// Leaf = MiMC(ax, ay)。device_pubkey の葉。
func Leaf(api frontend.API, ax, ay frontend.Variable) (frontend.Variable, error) {
	h, err := mimc.NewMiMC(api)
	if err != nil {
		return nil, err
	}
	h.Write(ax, ay)
	return h.Sum(), nil
}

// ComputeRoot は leaf から Merkle パスを畳んでルートを返す。
func ComputeRoot(api frontend.API, leaf frontend.Variable,
	siblings [Depth]frontend.Variable, bits [Depth]frontend.Variable) (frontend.Variable, error) {
	cur := leaf
	for d := 0; d < Depth; d++ {
		api.AssertIsBoolean(bits[d])
		left := api.Select(bits[d], siblings[d], cur)  // bit=1: 自分は右 → 左は sibling
		right := api.Select(bits[d], cur, siblings[d]) // bit=1: 右は自分
		h, err := mimc.NewMiMC(api)
		if err != nil {
			return nil, err
		}
		h.Write(left, right)
		cur = h.Sum()
	}
	return cur, nil
}

// ── 回路外（off-circuit）: 木の構築とパス生成 ──────────────────────────────

// MimcHash は MiMC_BN254 で複数体上要素をハッシュ（回路内 mimc.Write(...).Sum() と一致）。
func MimcHash(elems ...*big.Int) *big.Int {
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

// BuildTree は leaves(<=2^Depth)からルートと各インデックスのパス(siblings/bits)を返す。
func BuildTree(leaves []*big.Int) (root *big.Int, siblings [][]*big.Int, bits [][]int) {
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
		for i := 0; i < size; i++ {
			pairIdx := i >> d
			b := pairIdx & 1
			bits[i][d] = b
			if b == 0 {
				siblings[i][d] = cur[pairIdx+1]
			} else {
				siblings[i][d] = cur[pairIdx-1]
			}
		}
		next := make([]*big.Int, len(cur)/2)
		for j := 0; j < len(next); j++ {
			next[j] = MimcHash(cur[2*j], cur[2*j+1])
		}
		cur = next
	}
	return cur[0], siblings, bits
}
