## 1. 表紙

Week23の調査と実行、Week24の概念整理とPi測定をまとめる。今回の資料作成で重い証明実験を再実行していない。

出典: week23/10_HyperNova実行と最新Sonobe安全性と秘密引継ぎ.md; week24/01_HyperNova_概念とPR246_実装対応.md; week24/03_ユークリッド距離_各方式のPi実装.md

## 2. 目次

概念説明と実行証拠を区別し、最後に用途を限定した採用判断を示す。

出典: week24/01_HyperNova_概念とPR246_実装対応.md; week23/05_PCD_BC比較と技術選定ADR.md

## 3. 今回確認したい保証

単一Prover IVC、跨Proverのprivacy-preserving handoff、外部提出の最終ZKは別々の要件。検証成功だけでprivacyが成立したとはしない。

出典: week23/11_HyperNova_IVCとブラインド状態引継ぎの検証.md; week24/01_HyperNova_概念とPR246_実装対応.md

## 4. HyperNovaの構成

概念はIACR公開概要と固定ソースの対応表に基づく説明。論文全文の定義・安全性定理を全て照合したとはしない。公開概要はCCS、multi-folding、NovaBlindFold、CycleFoldを説明する。

出典: https://eprint.iacr.org/2023/573; week24/01_HyperNova_概念とPR246_実装対応.md

## 5. 調査した実装と版

HyperNova head 9c4e61f8d1a5be87c00f28838a0ef657a3cf479f。core ff/ec等0.6.0へ固定し旧forkのjoint_scalar_mul_beをscalar_mul_leの和へ移植。2ファイルの研究patchでrelation、opening、SumCheck、transcriptの検査は削除していない。macros helper0.5は公式依存によるもの。main7f042351は対照実験の別ツリーでありHyperNova branchの実行と混同しない。

出典: week23/10_HyperNova実行と最新Sonobe安全性と秘密引継ぎ.md; week23/manifests/hypernova-current-and-secret.json

## 6. Foldingの実行結果

2 variants×2 hiding設定×6(M,N)条件×10round=240。test件数38とfold round数240は異なる。小規模代数回路の検査であり観測回路・独立A/B/Cの成立ではない。

出典: week23/logs/hypernova-execution.json; week23/10_HyperNova実行と最新Sonobe安全性と秘密引継ぎ.md

## 7. 単一ProverのIVC実行

上流2アダプタは各20step、追加toyは公開state session/RID/bucket/policy/count。記載時間は追加toyの単回prove+verifyで、中央値や性能倍率ではない。

出典: week23/logs/hypernova-handoff-probe.json; week23/11_HyperNova_IVCとブラインド状態引継ぎの検証.md

## 8. 生IVC状態とWitness

固定CycleFold Proofはprimary RW/RU, incoming IW/IU, secondary RW/RUのtuple。追加HyperNova probeのincoming witnessで7個の合成canaryが各stepに残ることを確認。値そのものは本資料へ掲載しない。内部Proofがwitnessを含むこと自体を、公開ZK APIの脆弱性発見とは表現しない。

出典: week24/01_HyperNova_概念とPR246_実装対応.md; week23/11_HyperNova_IVCとブラインド状態引継ぎの検証.md

## 9. ブラインド化と継続の試験

random fold後の元canary完全一致は0、relationとNIMFS verifyは成功。しかしIVCのhash bindingとaugmented circuit assignmentの整合を満たさず継続経路は失敗。proveがproofを返すことと最終verify成功は別。

出典: week23/logs/hypernova-handoff-probe.json; week23/11_HyperNova_IVCとブラインド状態引継ぎの検証.md

## 10. 追加binderの実験結果

2→1 NIMFSの部品。cm_out=cm0+rho cm1を非ネイティブ群演算で拘束。改竄5件＋元digest保持session変更1件を拒否。Mac M2/16GiB、swap used7692.5MiBが7500MiB上限を超え、exit-15。proof/publicは生成されずnative verify未実行。元IVC履歴binderの完成ではない。後続ADRにより追加開発・prove再試行は停止しており、この資料作成で再開しない。

出典: week23/12_HyperNova_Folding_binderの回路実装と検証.md; week23/logs/hypernova-binder-prove-resource.json

## 11. Pi上での単一Prover IVC

Piの公開ログから値を再確認。生成・検証は各7stepの標本中央値。setup8544.626084ms、unit32.633419682s、kernelpeak156119040bytes=148.88671875MiB。子上限512MiB。cgroup OOM/oom_killとSwap使用0。過去の電源フラグ0x50000は残り、現在下位4bitは0。時系列の形だけでスケーリング則や1Hz適合性を主張しない。

出典: week24/03_ユークリッド距離_各方式のPi実装.md; week24/logs/pi-euclidean/euclidean-hypernova-v1/benchmark.jsonl; week24/logs/pi-euclidean/euclidean-hypernova-v1/resource.json

## 12. 確認済み機能と未達の保証

2026-10-13の固定PRソース監査は94ファイル照合・全Rust90ファイル検索。名称0件やimpl text match0件はその調査結果であり、将来版・理論全体の不存在証明ではない。

出典: week24/01_HyperNova_概念とPR246_実装対応.md

## 13. 今回の採用判断

2026-10-12にユーザー承認したADRを維持。main7f042351/HyperNova9c4e61f8+patchの秘密非共有継続用途に不採用。binderのresource stopは補足制約であり中心理由を原理的不可能性にしない。秘密非共有の成立例は別方式のGo/gnark固定3段一般再帰PoCだが、本番適合性や動的参加の保証は未確認。

出典: week23/05_PCD_BC比較と技術選定ADR.md

## 14. 調査結果のまとめ

この資料の目的は過去の実行結果と採用判断の説明。新規の重い証明生成や跨Prover binder開発の再開ではない。

出典: week23/05_PCD_BC比較と技術選定ADR.md; week23/10_HyperNova実行と最新Sonobe安全性と秘密引継ぎ.md; week24/03_ユークリッド距離_各方式のPi実装.md
