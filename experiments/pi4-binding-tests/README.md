# 署名付き観測回路の追加境界テスト

旧ベンチのsourceとsource hashは変更しない。
`run.py`が報告08のmanifestで`main.go`／既存test／go.mod／go.sumを検証し、ignoredな一時ディレクトリへ複製して追加テストを実行する。
依存版と回路は既存gnark Groth16 workloadと同じ。鍵・署名・assignmentはRAM内だけで生成する。

```sh
python3 experiments/pi4-binding-tests/run.py
```

追加16ケース：

- 正常5件：距離0、3–4–5、平方根の切捨て、u16座標の最大値、Session/Policy/RIDの最大値。
- 拒否11件：座標／距離二乗／Session／Policyの範囲外、rootの上下誤り、別public key、別署名者の署名、別RID、観測順の入替、集合rootの改変。

境界ケースは各入力を新たに正しく署名するため、古い署名との不一致だけで拒否された結果にしない。
これはconstraint solverの検査。無効assignmentからproofを強制生成したものや、実verifierが無効proofを拒否した検査ではない。
field値へ変換する前の非canonical入力、永続replay管理、資格失効、ログ漏出／side-channel検査は未実装。
`d2_overflow`では座標範囲も超えるため、単独のD2制約だけの検査とは扱わない。
