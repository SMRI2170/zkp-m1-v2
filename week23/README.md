# Week23：秘密Witnessを共有しない証明継続の評価

実施開始: 2026-10-11。親Issue: [#38](https://github.com/SMRI2170/zkp-m1-v2/issues/38)。
順序: **#39（実装/API調査）・#40（旧版再現）→ #41（秘密非共有PoC）→ #42（比較ADR）**。

本リポジトリは研究PoCである。V2はclaimed RIDをグループ化し、観測者署名を検証する。
DRIP trust chain、センサーの真実性、観測者ハードウェア認証、実UAVの同一性は証明しない。
今回の入力は合成fixtureのみ。実キャプチャ、実座標、秘密鍵を使用しない。

| 作業 | 状態 | 記録 |
|---|---|---|
| #39 | IN_PROGRESS：API入出力・検証責務を追記。Arecibo標準テスト成功、HyperNovaブランチ依存不整合を記録 | [02](02_Nova系実装とAPI対応調査.md) |
| #40 | LOCAL_COMPLETE_WITH_FINDINGS：両Hの露出・単一fold逆算・元KZG構成を再現。受信ゲートは改竄拒否、元verifyの失敗は保存 | [03](03_旧Sonobe_Witness露出再現.md) |
| #41 | IN_PROGRESS：A/B/Cと別観測のC分岐2本を検証。永続replay・離脱・同時提出の受信テスト成功 | [04](04_秘密保護型A_B_C連鎖PoC.md) |
| #42 | IN_PROGRESS：共同署名の競合とBesu共通履歴を比較実測。ZKPオンチェーンの同等比較は残る | [05](05_PCD_BC比較と技術選定ADR.md) |

状態はローカルの実行証拠に合わせて更新する。GitHubへのコメント投稿・Issueクローズはまだ行っていない。
旧成果を変更せず、実験ソースは `poc/`、依存版・パッチは `manifests/`、公開できるログは `logs/` に残す。
ビルド・合成秘密のシリアライズ・setup/proofは ignored `.cache/week23/` に保管し、Gitへ追加しない。

今回のローカルPoCはA→B→Cの秘密非共有計算連鎖まで成立した。
旧Sonobeの最終ZK proofをそのままfold継続するAPIは型不一致を再現したため、別方式として記録する。
全IssueをDONEとはしていない。Rust版の秘密継続、動的資格/参加、Pi/Pixel実機、Besu実測、同等条件の比較は残る。


2026-10-11の追加実施: #40の固定旧API再現はLOCAL_COMPLETE_WITH_FINDINGS。
#39はArecibo標準テスト成功・API追加調査、HyperNova依存固定と論文の詳細照合は残る。
#41は別観測の分岐proof・永続受信・同時提出/離脱を追加。固定rosterのローカルPoCであり任意参加/実機は残る。
#42は4-validator自己転送の確定遅延/停止台数を測定。ZKP用の使い捨てVK/proofはデプロイしない。
GitHub Issueの状態変更は行っていない。

追加実行と残件の一覧: [06](06_追加実行と残件.md)。

#42の共同署名・競合解決・共通履歴の比較結果：[07](07_BCなし共同署名とBesu共通履歴の比較実験.md)。
