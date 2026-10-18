## 1. 表紙

Novaについて実行済みの旧Sonobe、固定main、Piの記録を説明する。HyperNovaとは別資料。新規の重い証明実験は再実行しない。

出典: week23/03_旧Sonobe_Witness露出再現.md; week23/logs/sonobe-current-security.json; week24/03_ユークリッド距離_各方式のPi実装.md

## 2. 目次

検証の正当性、秘密を渡すかどうか、性能計測を分ける。

出典: week23/02_Nova系実装とAPI対応調査.md; week24/03_ユークリッド距離_各方式のPi実装.md

## 3. Novaも実行済み

固定mainのprobeはsonobe_fs::nova、NovaNovaIVCを使用。Pi実装もNovaNovaIVCとHyperNovaNovaIVCを分けて実行する。Microsoft NovaのCompressedSNARKは今回の実行ログと混同しない。

出典: week23/02_Nova系実装とAPI対応調査.md; week23/poc/sonobe-current/src/main.rs; experiments/pi4-euclidean/sonobe/src/main.rs

## 4. Novaで検証するもの

理論の概要はIACR 2021/370の公開abstractを確認。foldingは2関係を1関係へ縮約しIVCへつなぐ。生RecursiveSNARK/IVCProofと最終圧縮・ランダム化証明のAPIを区別する。

出典: https://eprint.iacr.org/2021/370; week23/02_Nova系実装とAPI対応調査.md

## 5. 旧Sonobeでの再現結果

旧版9b7dd34f0e0341046baeabc6f900f5ee63007f18+移植patch。Pedersen/Pedersen両Hと、元KZG/Pedersen H=falseで再現。生state8441240bytesは秘密を含み公開proofサイズとは扱わない。受信guardは別の研究CLIの検査であり上流ライブラリ修正とは扱わない。単一fold逆算は既知の前running witnessという条件があり、最終ZK proofの解読ではない。

出典: week23/03_旧Sonobe_Witness露出再現.md

## 6. 固定mainでの改竄拒否

2026-10-12時点で固定したmain7f042351e73d38f99c05167ba41f1e282178b067。NovaNovaIVCで6独立プロセスの正常経路と22改竄×3段×2設定=132件拒否。省略6件を132に加算して同じ検査種類とは扱わない。信頼区間や確率推定の図ではない。

出典: week23/logs/sonobe-current-security.json; week23/10_HyperNova実行と最新Sonobe安全性と秘密引継ぎ.md

## 7. 生状態に残る識別用入力

固定main各runの当該stageのauditからowner_stageが同じcanaryのみを集計し、incoming_w_indicesが非空の数を算出。両H各3段で7件。canaryの値そのものや秘密assignmentは資料へ埋め込まない。serialized witnessの直接可視性と暗号学的なcommitmentの破壊を区別する。

出典: week23/logs/sonobe-current-security.json; week24/figures/nova-validation-v2/security.csv

## 8. Pi上でのNova / CycleFold

benchmark relation valid7 invalid6、claimed_state_rejections3×7、all_verifiedtrue、final_zkfalse、raw_ivc_contains_witnesstrue。setup8610.061128ms、unit38.168350018sec、peak196173824bytes。CPU quota25%の後続21件実験と混ぜない。

出典: week24/03_ユークリッド距離_各方式のPi実装.md; week24/logs/pi-euclidean/euclidean-nova-v2/benchmark.jsonl; week24/logs/pi-euclidean/euclidean-nova-v2/resource.json

## 9. stepごとの生成・検証時間

正常採用run v2のcase_id0..6を順に線で結ぶ。生成median1900.210576ms、検証median2946.230978ms。長期スケーリング則や定常レイテンシを推定しない。

出典: week24/logs/pi-euclidean/euclidean-nova-v2/benchmark.jsonl; week24/figures/nova-validation-v2/pi-steps.csv

## 10. 実行全体のメモリ推移

memory.jsonlのcgroup_current_bytesを使用し、kernel peakはresource.jsonから別の破線として表示。Nova v2のみで、失敗v1を混ぜない。親High1200/Max1536MiB、子High384/Max512MiB、Swap0。OOM/oom_killイベント増分0。

出典: week24/logs/pi-euclidean/euclidean-nova-v2/memory.jsonl; week24/logs/pi-euclidean/euclidean-nova-v2/resource.json; week24/figures/nova-validation-v2/sources.json

## 11. HyperNovaとの同一回路での比較

同じFCircuitをNovaNovaIVC/HyperNovaNovaIVCで実行。全unitにはsetupや公開state負例を含む。いずれも7stepで最終ZKは含まず、後続n21の方式比較へ合流させない。

出典: week24/03_ユークリッド距離_各方式のPi実装.md; week24/logs/pi-euclidean/euclidean-nova-v2/benchmark.jsonl; week24/logs/pi-euclidean/euclidean-hypernova-v1/benchmark.jsonl

## 12. 失敗runと再実行の扱い

v1exit-15、stop_reason current_undervoltage_or_throttling、before0x50000 after0x50005。v2exit0、stop_reasonnull、before/after0x50000。いずれもOOMイベント0・swap0。電源フラグによるguard停止の観測で、他の全SSH断原因も電源と断定するものではない。

出典: week24/logs/pi-euclidean/euclidean-nova-v1/resource.json; week24/logs/pi-euclidean/euclidean-nova-v2/resource.json

## 13. 最終証明と継続状態を区別する

旧Sonobe H=trueのRandomizedIVCProof::new/verifyを実行。canary完全一致0は直接一致検査であり暗号学的安全性の証明ではない。from_ivc_proofはIVCProofを要求し、RandomizedIVCProofからの復元APIは調査範囲内で未確認。Microsoft CompressedSNARKとは別の実装・実験。

出典: week23/logs/witness-zk-final.jsonl; week23/02_Nova系実装とAPI対応調査.md

## 14. Novaの検証結果まとめ

Novaも実装・実行済みであり未着手ではない。ただしSonobeのraw IVC handoffがprivacy要件を満たしていないという用途限定の結果。単一端末内IVCの動作結果と両立する。

出典: week23/05_PCD_BC比較と技術選定ADR.md; week23/logs/sonobe-current-security.json; week24/03_ユークリッド距離_各方式のPi実装.md
