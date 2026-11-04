# Week24：Circom＋snarkjs／RapidSnarkの比較追加

同じ回路の証明生成実装を比較する2構成を、順次実行プログラムへ追加した。
同じPi上の貢献済みGroth16 test fixture、WASM Witness generator、共通のRapidSnark native verifierを使用する。
snarkjsは単一スレッドNode API、RapidSnarkはnative prover。CPU25%・1CPU・子Max256MiB・7入力×3回を揃える。

Piのsnarkjsは既存0.7.5。sourceでAPIのoptions伝播とsingleThreadを確認し、version/hashを保存して使用する。
Macの0.7.6による実proof確認は正当性チェックのみ。Pi性能へ加算しない。
この2構成は証明生成の差を見るもので、snarkjsだけの証明生成＋検証の評価とは区別する。

## 自動処理

1. 安全性チェック保持・構文・CSV結合の回帰検査。
2. Macでsnarkjs実proofを生成し、正常検証と公開入力改変の拒否を確認。
3. Pi ready確認、hash検証、owner-onlyの新directoryへ配置。
4. snarkjs、RapidSnarkを順に実行。各warmup7＋測定21、既存の否定テストを維持。
5. 許可した測定ログだけを1接続で回収。
6. CSV/JSON・統計・図を生成し、既存7構成とsource hash付きで結合。工程差のあるcohortは別図。
7. CI結果・ログも保存し、チャットでは完了待ちしない。

[起動方法と結果ファイル](../experiments/circom-prover-comparison/README.md)。初回はcircom-1017aの新jobとして起動する。
旧測定とPlonky3 partialを保持し、完走／失敗／未実施をCSV/JSONへ保存する。実行開始は測定完了ではない。
鍵・使い捨てsetup/VK/proof実体、実capture・実座標は公開・deployしない。
研究PoCであり、DRIP trust chain・sensor honesty・observer hardware／航空機認証を保証しない。
