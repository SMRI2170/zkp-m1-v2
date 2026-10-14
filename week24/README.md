# Week24：端末内時系列証明と軽量ZKPの評価

親Issue [#43](https://github.com/SMRI2170/zkp-m1-v2/issues/43)。実行トラック [#44](https://github.com/SMRI2170/zkp-m1-v2/issues/44)、候補調査 [#45](https://github.com/SMRI2170/zkp-m1-v2/issues/45)、モバイル/FFI比較 [#46](https://github.com/SMRI2170/zkp-m1-v2/issues/46)。

| 作業 | 状態 | 記録 |
|---|---|---|
| HyperNova概念・PR #246対応 | IN_PROGRESS：版固定・ソース照合・API境界とギャップ整理。最新論文PDFは403で全文照合未完了 | [01](01_HyperNova_概念とPR246_実装対応.md) |
| Pi4 4GB・複数ZKPベンチ | IN_PROGRESS：gnark Groth16 toyのPi-native 4trial成功。メモリ統計・上限・SSH保護を検証。共通距離回路は[03](03_ユークリッド距離_各方式のPi実装.md)で7構成成功。RSSI／長期は残る | [02](02_Pi4_4GB_複数ZKP実装と性能評価.md) |
| 共通ユークリッド距離回路 | COMPLETE：7構成のPi-native生成／検証。Nova／HyperNovaはIVCのみ、最終ZKなし | [03](03_ユークリッド距離_各方式のPi実装.md) |
| 距離回路の平均・サイズ可視化 | COMPLETE：75ケースの平均フロー、生成／更新、平均・peakメモリ、proofサイズと内訳 | [04](04_ユークリッド距離_平均処理時間とサイズ比較.md) |
| 追加方式／EVM適合性 | 追加5方式でPi-native生成／検証成功。Plonky2は低電圧等で未完了、RISC Zero／SP1は事前評価。EVM適合性は残る | [05](05_追加フレームワークのPi評価.md) |
| 未完了方式の追加実行 | Plonky2はPi2件・Mac7件成功、RISC ZeroはMac実proof成功、Halo2 KZGのr改変拒否完了。SP1はswap保護停止。Pi長時間実行は電源条件が残る | [06](06_未完了方式の追加実行.md) |
| Kimchi／Binius64／Jolt追加 | Mac3方式全7件。Pi Kimchi／Binius64全7件、Jolt正常1件＋不正2件。CPU25%測定・グラフ・保護設定を記録 | [07](07_Kimchi_Binius64_Joltの追加評価.md) |
| 追加評価データ収集 | 同一入力3反復・phase別memory・拒否段階・サイズをCSV/JSONL保存。gnark署名負荷1/2観測と短い1Hz queue成功、4観測は再起動でpartial | [08](08_追加評価データの収集と反復測定.md) |
| モバイル／Native FFI比較 | RESEARCH_PLANNED | #46 |

Pi4のSSH接続と機種/OS/RAMを確認し、初回toyの暗号処理・資源測定を実施済み。
実施順序・測定項目・停止条件：[実機評価計画](00_Pi4_実機評価計画.md)。

Week23の跨Prover Sonobe／HyperNova不採用・binder開発停止を維持する。
ここではWitnessを端末内に留める単一Prover時系列IVCを別用途として評価する。
Folding／IVCの動作と、外部提出用の最終ZK証明の完成を区別する。
今回のsource監査はPi性能や終端ZKの実証ではない。

公開可能な報告・source hashは本directory、取得資料とビルドはignored `.cache/week24/`。
秘密・VK/proofの扱いはroot AGENTS.mdに従う。実captureをこのdirectoryへ入れない。
