// Package membership は、集約に含める各 device_pubkey が「登録端末の Merkle ルート」の
// メンバーであることを回路内で検証する（M2 の Sybil ギャップを塞ぐ）。
//
// 現状の M2 集約は device_pubkey の相異（distinct）のみ強制し、登録済みかは未検証だった。
// 本回路を集約に組み込むと、集約は「相異なる"登録済み"K台」を保証でき、契約側は
// 集約が公開する Root がオンチェーンの登録ルートと一致することだけ確認すればよい（定数gas）。
package membership

import (
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/hash/mimc"
)

const (
	N     = 3 // 集約する端末数
	Depth = 4 // Merkle 木の深さ（最大 2^Depth 台の登録端末）
)

// Circuit: N 個の device_pubkey(ax,ay) が Root のメンバーであることを検証。
type Circuit struct {
	Root     frontend.Variable `gnark:",public"` // 登録端末ルート（契約が registry と照合）
	Ax       [N]frontend.Variable
	Ay       [N]frontend.Variable
	Siblings [N][Depth]frontend.Variable
	PathBits [N][Depth]frontend.Variable // 各段 0/1（0=自分が左, 1=自分が右）
}

func (c *Circuit) Define(api frontend.API) error {
	for i := 0; i < N; i++ {
		// leaf = MiMC(ax, ay)
		h, err := mimc.NewMiMC(api)
		if err != nil {
			return err
		}
		h.Write(c.Ax[i], c.Ay[i])
		cur := h.Sum()

		// Merkle パスを畳んでルートへ
		for d := 0; d < Depth; d++ {
			bit := c.PathBits[i][d]
			api.AssertIsBoolean(bit)
			sib := c.Siblings[i][d]
			left := api.Select(bit, sib, cur)  // bit=1: 自分は右 → 左は sibling
			right := api.Select(bit, cur, sib) // bit=1: 右は自分
			hh, err := mimc.NewMiMC(api)
			if err != nil {
				return err
			}
			hh.Write(left, right)
			cur = hh.Sum()
		}
		api.AssertIsEqual(cur, c.Root)
	}
	return nil
}
