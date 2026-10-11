# Week23：秘密Witnessを共有しない証明継続の評価

実施開始: 2026-10-11。親Issue: [#38](https://github.com/SMRI2170/zkp-m1-v2/issues/38)。
順序: **#39（実装/API調査）・#40（旧版再現）→ #41（秘密非共有PoC）→ #42（比較ADR）**。

本リポジトリは研究PoCである。V2はclaimed RIDをグループ化し、観測者署名を検証する。
DRIP trust chain、センサーの真実性、観測者ハードウェア認証、実UAVの同一性は証明しない。
今回の入力は合成fixtureのみ。実キャプチャ、実座標、秘密鍵を使用しない。

| 作業 | 状態 | 記録 |
|---|---|---|
| #39 | IN_PROGRESS：main/旧版/開発ブランチのソースを固定、論文改訂を確認 | [02](02_Nova系実装とAPI対応調査.md) |
| #40 | IN_PROGRESS：A/B・両Hで元canaryの直接露出を再現。commitment改竄の拒否テストは未達 | [03](03_旧Sonobe_Witness露出再現.md) |
| #41 | IN_PROGRESS：有限3段Go一般再帰のA/B/C生成・最終verify成功。署名転送・否定系も確認 | [04](04_秘密保護型A_B_C連鎖PoC.md) |
| #42 | IN_PROGRESS：個別proof＋共同署名baseline成功。比較の採否判断は保留 | [05](05_PCD_BC比較と技術選定ADR.md) |

状態はローカルの実行証拠に合わせて更新する。GitHubへのコメント投稿・Issueクローズはまだ行っていない。
旧成果を変更せず、実験ソースは `poc/`、依存版・パッチは `manifests/`、公開できるログは `logs/` に残す。
ビルド・合成秘密のシリアライズ・setup/proofは ignored `.cache/week23/` に保管し、Gitへ追加しない。

今回のローカルPoCはA→B→Cの秘密非共有計算連鎖まで成立した。
旧Sonobeの最終ZK proofをそのままfold継続するAPIは型不一致を再現したため、別方式として記録する。
全IssueをDONEとはしていない。Rust版の秘密継続、動的資格/参加、Pi/Pixel実機、Besu実測、同等条件の比較は残る。
