# GitHub Issueの整理と引継ぎ（2026-11-17）

GitHub側の変更と読み戻し検証を完了した。**OPEN 64件→9件：全体管理1件＋現在の作業6件＋将来保留2件**。55件は`not_planned`で統合クローズし、完了・実験成功・要件充足の認定にはしていない。

全64件の元本文が変更後の各Issue内に保持されていることを照合した。チェック欄・参照PR・既存コメント・ソース・実験データは削除していない。PRはマージ／クローズしていない。

## 現在見るIssue

| 区分 | Issue | 管理する内容 |
|---|---|---|
| 全体管理 | [#88](https://github.com/SMRI2170/zkp-m1-v2/issues/88) | 現在の6課題・依存・次の作業・統合台帳 |
| 作業 | [#97](https://github.com/SMRI2170/zkp-m1-v2/issues/97) | Piの保存修正・A〜Fの収録保護・実機導入 |
| 作業 | [#84](https://github.com/SMRI2170/zkp-m1-v2/issues/84) | Android受信・自己位置・保存・権限・長時間検証 |
| 作業 | [#89](https://github.com/SMRI2170/zkp-m1-v2/issues/89) | 時刻・GPS・取得間隔・重複・キャッシュの品質 |
| 作業 | [#95](https://github.com/SMRI2170/zkp-m1-v2/issues/95) | 同一送信候補・同期・RSSI差分の成立条件 |
| 作業 | [#96](https://github.com/SMRI2170/zkp-m1-v2/issues/96) | RSSIモデル・合成攻撃・先行研究と検出限界 |
| 作業 | [#93](https://github.com/SMRI2170/zkp-m1-v2/issues/93) | 3D表示・1イベント説明図・結果と限界の報告 |
| 将来保留 | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) | ZKP・P2P・Besu統合・資格／認証／状態管理 |
| 将来保留 | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) | ZKP方式・秘匿IVC・Piベンチ・反復／境界検査 |

[全体管理 #88](https://github.com/SMRI2170/zkp-m1-v2/issues/88)に、#84/#89/#93/#95/#96/#97の6件をGitHubネイティブの子Issueとして揃えた。旧#90/#91/#92/#94と旧#44→#47は、閉じた旧Issueの進捗を現在の達成と誤認しないよう、現在の親子一覧から外した。#97は旧#90の下から#88の直下へ移した。

ラベルは`status:active`（全体＋作業）、`status:deferred`（将来保留）、`status:consolidated`（統合済み）を使用する。

## 全55件の引継ぎ先

| 旧Issue | 元の題名 | 正本となる統合先 |
|---|---|---|
| [#10](https://github.com/SMRI2170/zkp-m1-v2/issues/10) | [RID-P0] 利用主体・ユースケース・公開条件を定義する | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#11](https://github.com/SMRI2170/zkp-m1-v2/issues/11) | [RID-P0] Remote IDの信頼境界・攻撃モデル・保証レベルを定義する | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#12](https://github.com/SMRI2170/zkp-m1-v2/issues/12) | [RID-P0][Mode C] 観測・ZKP・P2P検証・共同確定のメッセージ契約を設計 | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#13](https://github.com/SMRI2170/zkp-m1-v2/issues/13) | [RID-P1][Mode C] Pixel 8 Observer：受信・秘密観測・ZKP・相互検証を連携 | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#14](https://github.com/SMRI2170/zkp-m1-v2/issues/14) | [RID-P1][Mode C] Raspberry Pi 4×2 Observer：受信・ローカルZKP・他2台の検証 | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#15](https://github.com/SMRI2170/zkp-m1-v2/issues/15) | [RID-P1] Remote ID認証・鮮度・出所検証を独立モジュール化する | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#16](https://github.com/SMRI2170/zkp-m1-v2/issues/16) | [RID-P1][Mode C] 3台P2P通信・セッション同期・証拠複製を実装する | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#17](https://github.com/SMRI2170/zkp-m1-v2/issues/17) | [RID-P1][Mode C] 各ノード共通の誤差考慮型ローカル判定と3観測融合を設計 | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#18](https://github.com/SMRI2170/zkp-m1-v2/issues/18) | [RID-P2][Mode C] Pi4×2・Pixel8の個別ZKP生成と他2台の相互検証を実装 | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#19](https://github.com/SMRI2170/zkp-m1-v2/issues/19) | [RID-P2][Mode C] 3台の提出集合確定・相互投票・共同署名証明書を実装 | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#20](https://github.com/SMRI2170/zkp-m1-v2/issues/20) | [RID-P2] Merkleログ・複数検証者・許可型BCを同条件で比較する | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#21](https://github.com/SMRI2170/zkp-m1-v2/issues/21) | [RID-P3] 一般利用者向け：周辺UAVと接近リスクの表示を実装する | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#24](https://github.com/SMRI2170/zkp-m1-v2/issues/24) | [RID-P4][Mode C] 3観測ノードのZKP・相互検証・故障攻撃E2E試験 | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#25](https://github.com/SMRI2170/zkp-m1-v2/issues/25) | [RID-P4][Mode C] 3ノードの精度・ZKP・相互検証コストを実測する | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#26](https://github.com/SMRI2170/zkp-m1-v2/issues/26) | [RID-C-v1][Protocol] 3観測ノードが観測・ZKP生成・相互検証・共同確定するプロトコルを実装する | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#29](https://github.com/SMRI2170/zkp-m1-v2/issues/29) | [RID-BC][P0] 信頼モデル・検証ステートメント・公開ABI／状態機械を確定する | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#30](https://github.com/SMRI2170/zkp-m1-v2/issues/30) | [RID-BC][P1] Besu QBFT 4 Validator＋RPCの再現可能な開発環境を構築する | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#31](https://github.com/SMRI2170/zkp-m1-v2/issues/31) | [RID-BC][P1] Circom＋RapidSnark＋SolidityでRemote ID個別証明を相互運用する | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#32](https://github.com/SMRI2170/zkp-m1-v2/issues/32) | [RID-BC][P2] Pixel 8・Raspberry Piの端末資格／ハードウェアアテステーションを設計する | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#33](https://github.com/SMRI2170/zkp-m1-v2/issues/33) | [RID-BC][P2] Solidity DeviceRegistry／PolicyRegistryと権限・鍵更新を実装する | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#34](https://github.com/SMRI2170/zkp-m1-v2/issues/34) | [RID-BC][P2] Solidity Groth16オンチェーン検証・Remote IDセッション集約を実装する | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#35](https://github.com/SMRI2170/zkp-m1-v2/issues/35) | [RID-BC][P2] 速報Fast Path：ZKP／BC確定を待たずに危険候補を通知する | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#36](https://github.com/SMRI2170/zkp-m1-v2/issues/36) | [RID-BC][P3] 3実機E2E・攻撃耐性・性能評価とBCなし方式との比較 | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#37](https://github.com/SMRI2170/zkp-m1-v2/issues/37) | [RID-BC][P4] 国内標準化を見据えた公開プロトコル・適合性試験・参照実装を整備する | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#38](https://github.com/SMRI2170/zkp-m1-v2/issues/38) | [Week23][Epic] Nova系ZK-PCDのWitness秘匿・3ノード証明継続とBC採用判断 | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#39](https://github.com/SMRI2170/zkp-m1-v2/issues/39) | [Week23][P0] Nova・SuperNova・HyperNova・KiloNova／Sonobe実装とZK引継ぎAPIの調査 | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#40](https://github.com/SMRI2170/zkp-m1-v2/issues/40) | [Week23][P0] Sonobe旧IVCProofのWitness露出と状態検証漏れをコードで再現 | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#41](https://github.com/SMRI2170/zkp-m1-v2/issues/41) | [Week23][P1] 秘密Witness非共有のA→B→C ZK-IVC／PCD最小PoCを実装・否定テスト | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#42](https://github.com/SMRI2170/zkp-m1-v2/issues/42) | [Week23][P2] PCD・3台個別ZKP・Besuの保証／性能比較と技術選定ADR | [#28](https://github.com/SMRI2170/zkp-m1-v2/issues/28) |
| [#43](https://github.com/SMRI2170/zkp-m1-v2/issues/43) | [教授フィードバック][研究再設計] HyperNova PR #246の概念実装調査・研究新規性・Pi 4軽量IVC・端末内時系列証明 | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#45](https://github.com/SMRI2170/zkp-m1-v2/issues/45) | [Week24][調査] モバイル・Raspberry Pi軽量ZKP候補とBesu/EVMオンチェーン検証の適合性比較 | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#46](https://github.com/SMRI2170/zkp-m1-v2/issues/46) | [Week24][Mobile][手順明確化] Rust ZKP共通coreでJNI・UniFFI・Flutter FFI・KMPを段階比較 | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#47](https://github.com/SMRI2170/zkp-m1-v2/issues/47) | [Week24][追加評価Epic] Pi安定稼働・署名付き観測回路・反復／長時間評価の残タスク | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#48](https://github.com/SMRI2170/zkp-m1-v2/issues/48) | [Week24][P0] Pi再起動の背景と安定稼働・メモリ保護を確認 | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#50](https://github.com/SMRI2170/zkp-m1-v2/issues/50) | [Week24][P0] Kimchi・Binius64・Joltへ同等の署名付き観測workloadを移植 | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#51](https://github.com/SMRI2170/zkp-m1-v2/issues/51) | [Week24][P1] 独立cold反復とwarm反復を増やし統計・メモリ評価を強化 | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#52](https://github.com/SMRI2170/zkp-m1-v2/issues/52) | [Week24][P1] 持続1Hz入力のキュー・欠測・長時間メモリを段階評価 | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#53](https://github.com/SMRI2170/zkp-m1-v2/issues/53) | [Week24][P1] 署名・session・replay・境界値の否定テストを拡充 | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#54](https://github.com/SMRI2170/zkp-m1-v2/issues/54) | [Week24][P2] 合成RSSI・時系列・観測者資格／期限条件へworkloadを拡張 | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#55](https://github.com/SMRI2170/zkp-m1-v2/issues/55) | [Week24][P1] 未完了backendのPiケースとzkVMビルド・実行制約を整理 | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#58](https://github.com/SMRI2170/zkp-m1-v2/issues/58) | [Week24][P1] 距離回路ベンチを同じ7入力×3回に統一し統計・比較図を再生成 | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#60](https://github.com/SMRI2170/zkp-m1-v2/issues/60) | [Week24][P1] Pi接続を復旧し8構成の21件ベンチと比較図を実測する | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#61](https://github.com/SMRI2170/zkp-m1-v2/issues/61) | [Week24][P1] 残る10構成を均等反復ベンチまたはIVC専用評価へ対応させる | [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44) |
| [#66](https://github.com/SMRI2170/zkp-m1-v2/issues/66) | [Week25][研究] 1時間離れた複数ノード観測・未知送信電力下の検証可能性と限界 | [#96](https://github.com/SMRI2170/zkp-m1-v2/issues/96) |
| [#67](https://github.com/SMRI2170/zkp-m1-v2/issues/67) | [Week26][技術調査→方式選定→デモ] 非同期・未知送信電力のRSSI測距／異常検出とZKP適用可能性 | [#96](https://github.com/SMRI2170/zkp-m1-v2/issues/96) |
| [#68](https://github.com/SMRI2170/zkp-m1-v2/issues/68) | [Week27][研究] GhostBuster・方向推定の再調査と実UAV電波データによる位置偽装検出の成立条件評価 | [#96](https://github.com/SMRI2170/zkp-m1-v2/issues/96) |
| [#69](https://github.com/SMRI2170/zkp-m1-v2/issues/69) | [Week27][P4/可視化] UAV・ユーザ・受信ノードの状態を同一イベントで理解できる説明用ビュー | [#93](https://github.com/SMRI2170/zkp-m1-v2/issues/93) |
| [#70](https://github.com/SMRI2170/zkp-m1-v2/issues/70) | [Week27][P0/実装] uli-net-simを用いたRemote ID相当Beacon×RSSI位置偽装・未知送信電力・非同期観測の再現実験 | [#96](https://github.com/SMRI2170/zkp-m1-v2/issues/96) |
| [#75](https://github.com/SMRI2170/zkp-m1-v2/issues/75) | [Week27][PR5][研究実装] 観測局適応型Tx電力補償攻撃と非同期1RSSI検出限界の追試 | [#96](https://github.com/SMRI2170/zkp-m1-v2/issues/96) |
| [#77](https://github.com/SMRI2170/zkp-m1-v2/issues/77) | [Week28][PR6][研究実装] Remote ID相当Beacon×RSSI検出の外的妥当性：局配置・偽装方向・伝搬不一致 | [#96](https://github.com/SMRI2170/zkp-m1-v2/issues/96) |
| [#83](https://github.com/SMRI2170/zkp-m1-v2/issues/83) | [Week28][実機/実測] Wi-Fi Beacon・Remote ID受信ノードの多点展開とRSSI観測基盤構築 | [#97](https://github.com/SMRI2170/zkp-m1-v2/issues/97) |
| [#90](https://github.com/SMRI2170/zkp-m1-v2/issues/90) | [Week29][P0] 記録停止と受信空白の原因分析・保存修正後の確認 | [#97](https://github.com/SMRI2170/zkp-m1-v2/issues/97) |
| [#91](https://github.com/SMRI2170/zkp-m1-v2/issues/91) | [Week29][P1] Androidの自己位置・測位精度・欠測と観測時刻対応の監査 | [#89](https://github.com/SMRI2170/zkp-m1-v2/issues/89) |
| [#92](https://github.com/SMRI2170/zkp-m1-v2/issues/92) | [Week29][P1] Raspberry PiとAndroidのRID取得間隔・重複・キャッシュの比較 | [#89](https://github.com/SMRI2170/zkp-m1-v2/issues/89) |
| [#94](https://github.com/SMRI2170/zkp-m1-v2/issues/94) | [Week29][P1] 実機RIDの申告距離・高度と実測RSSIの関係・ばらつき分析 | [#96](https://github.com/SMRI2170/zkp-m1-v2/issues/96) |

## 運用ルール

- 既存6件のチェックリストで扱える作業は、方式・条件・週番号ごとに新Issueを作らない。
- 独立した成果物・担当・完了条件が必要な場合だけ分割する。
- ローカル実装、実機実行、GitHub公開、CI確認、研究上の成立を別々に記録する。
- 過去の未完了は移管先で追跡する。閉じた旧Issueの未チェック欄を、もう一つの現在タスクとして数えない。
- 将来保留を再開するときは#28/#44から対象を選び、既存コード・PR・未実行条件を確認する。Sonobe跨Prover秘匿引継ぎの不採用など、既往判断を整理だけで撤回しない。
- 間違って統合した項目があれば、旧Issueをreopenして引継ぎ先・全体一覧を更新できる。元の本文とGitHub編集履歴は保持している。

## 公開・データの境界

この**Issue整理はGitHubへ反映済み**。Week29で追加した解析・保存修正・新規MDのソース公開／commit／push／CIとは別作業であり、それらが反映済みになったわけではない。公開一覧には生capture・実座標・実ID・BSSID・鍵・パスワードを含めていない。

研究PoC。観測・計算・署名の整合と、物理真位置・機体／ハード認証・DRIP・センサの正直さを混同しない。
