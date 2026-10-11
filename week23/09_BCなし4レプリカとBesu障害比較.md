# ② BCなし4レプリカ・③ Besu障害実験

2026-10-12。合成データ、Mac、実機なし。今回の入力は[08](08_ZKP検証からBesu履歴への統合と資格管理.md)で
実際に検証した再帰normal/outlier receiptの同じSHA-256。
[BCなし結果](logs/quorum-log.json)、[QC否定検査](logs/quorum-security.json)、[Besu結果](logs/besu-network-faults.json)。

## 実装したBCなし方式

4個の独立Pythonプロセス、Ed25519署名、quorum=3、固定leader、prepare→commit→decisionの2段階証明書。
レプリカごとに投票/commit/decisionをowner-onlyファイルへfsync＋atomic renameで保存する。
署名者の重複、署名改竄、session/epoch/policy/parent不一致、検証済みreceipt以外を拒否する。
3-of-4の証明書どうしは少なくとも2レプリカで交差する。1 Byzantineを仮定したとき、正直な交差レプリカの永続投票ロックで競合を防ぐ。

**これは固定1スロットの最小quorum logであり、PBFT/HotStuffの完成実装ではない。**
view change/投票ロック解除/動的資格更新はない。leader停止や2対2への票分散後に復旧できない場合を測定結果として残した。
leaderによるequivocation、3対1、再送・並べ替え・200 ms遅延、プロセス再起動後の二重投票拒否を試した。
入力receiptの有効性は統合実験の事前条件とし、合意中にZKPを再検証していない。
通信はharnessが制御するstdio配送で、実WAN性能ではない。

## Besu側の障害注入

新しい4 Besu 26.9.0プロセスを起動し、12方向のloopback TCPプロキシへstatic peer接続を通した。
P2P discoveryは無効。分断時は境界の既存TCP接続を閉じ、境界への接続/転送を止める。
契約は07の署名ダイジェスト・first-write履歴を使用する。
3/3観測者署名を作成するが、07契約の最低受理閾値は2/3のまま。資格試験の08契約とは分離したtransport試験である。
ZKP/VK/proofはチェーンへ載せていない。

| 故障・条件 | BCなし4レプリカ | Besu4validator |
|---|---|---|
| 正常 | 4者で同じdecision | 4者で同じreceipt/履歴 |
| フォロワー1台停止 | 残り3者で進行 | 07の別実験で3block進行確認済み。今回は分断試験 |
| leader停止 | **停止。view changeなし** | validator1台停止は07で確認。特定proposerの攻撃/停止は未測定 |
| 2台停止/2対2分断 | quorum不足で停止。競合する少数QCを拒否 | height [4,4,4,4]→同値、12秒の観測窓で停止。提出txはreceiptなし |
| 2対2の通信復旧 | 分散済み票のunlockなし、進行保証なし | pending txが確定し4者一致。復旧後43.175秒 |
| 3対1分断 | 多数3者で同じdecision、少数へQCを渡すと追従 | 多数側進行/少数height 5のまま、少数にreceiptなし |
| 3対1の復旧 | QC配送で追従 | 少数側も同じreceipt。復旧後42.019秒 |
| 遅延/再送 | 200 ms配送遅延・順序変更後同じdecision、再送は冪等 | TCP readごと200 ms遅延で4者一致。receipt約2.981秒。raw tx再送はNonce too low、イベント増加なし |
| leader二重提案/不正署名 | 競合投票・改竄署名を拒否 | 悪意validator署名/QBFT安全性攻撃は未測定 |
| 受付拒否 | leaderが提案しなければ進行しない（設計上の制約） | 実HTTP入口が403拒否。全ノードにtxなし。別RPC入口から提出して成功 |

Besu正常receiptは単回2.521秒、3対1多数側3.808秒。復旧時間は単回で、一般の復旧上限を示さない。
約42〜43秒の復旧にはstatic peer再接続やQBFTタイマーが影響しうるが、原因を分解測定していない。
「分断解除と同時に即復旧」とは言えない。
TCP遅延はchunk/read単位であり、正確なpacket/WAN遅延ではない。
再提出された競合のfresh nonce txはstatus 0。最終成功イベント5件と全内容/順序が4ノードで一致した。

プロキシ転送は697,794 bytes（起動/空block/合意/同期を含む全実験）。
BCなし正常ケースのJSON/stdio要求＋応答は21,759 bytes、13要求、wall約48.1 ms（プロセス起動待ちを含む単回）。
両者の測定境界、トランスポート、暗号、タイマーが異なるため速度/通信倍率は計算しない。
同条件のp50/p95・RAM・通信比較は⑧に残す。

## 結論と反証条件

**共通履歴を作るためにBCは唯一の方法ではない。** 4レプリカ署名QCでも正常/1 follower停止下の唯一決定を作れた。
ただし今回の最小方式はleader障害と票分散の復旧機構が足りない。
Besuは今回の分断復旧で既存の共通履歴へ再同期できた。共通履歴研究の参照実装として維持する根拠が増えた。
単一ホスト/単一運営者であり、独立組織の耐障害実証ではない。

入口が受け取らなければ、有効な証拠でも台帳に存在しない。
受付拒否（403/未送信）、合意待ち（pending/receiptなし）、契約拒否（status 0）、履歴確定（status 1）を別イベントにした。
BCを採用しただけで検閲不可や提出集合完全性は得られない。

正直レプリカの競合decision、Besu4ノードの最終履歴不一致、少数側の独立確定が生じれば安全性の今回の結論を撤回する。
本採用は独立運営、復旧遅延予算、資格authority、包含方針、証拠保持・監査の要件を満たすことが条件。
#20/#42全体は同条件benchmarkや運営モデル評価が残るためIN_PROGRESS。
