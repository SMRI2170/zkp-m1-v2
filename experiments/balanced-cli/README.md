# Issue #61：Circom／Noirの均等反復CLIドライバ

旧sourceをhash照合し、回路・ZK設定・否定テストを変えず、測定loopを新しい28件へ変更する。
7入力各1回warmup、その後7入力を3巡して21件を集計する。1process内のwarm反復。
この追加では実proofを生成していない。Noirのdispatcher試験は偽CLIによる配線・回数・一時ファイル削除のテスト。
Circomはsource保持・JavaScript構文までの確認であり、実prover/verifier試験は残件。

```sh
python3 experiments/balanced-cli/render.py circom --out .cache/week24/balanced-cli-new/circom
python3 experiments/balanced-cli/render.py noir --out .cache/week24/balanced-cli-new/noir
python3 -m unittest discover -s experiments/balanced-cli -p 'test_*.py'
python3 experiments/balanced-cli/check_results.py
```

出力先を上書きしない。`rendered/`は同じ生成結果の監査用snapshot。元の実験source・図・manifestは変更しない。

## 実行時の引数

```sh
node bench.cjs PRIVATE_CONTRIBUTED_FIXTURE RAPIDSNARK_PROVER RAPIDSNARK_VERIFIER
python3 bench.py NOIR_PROJECT NARGO_BINARY BB_BINARY
```

これらを直接無制限に実行せず、Piの保護確認済みrunner内で実行する。
実測は #60/#61 の保護・preflight・予算確認後に行う。このフォルダには実機launcherや配備成功の主張はない。
Circomは貢献済み使い捨てfixtureのphase1/phase2・zkey検証・hash・owner-only権限を確認する。
Noirは既存beta25/bb5.2.0構成と`-t evm`のZK設定を維持する。新しいversionへ黙って更新しない。

## 時間・サイズ・一時ファイル

- Circom：WASM witness、native prove/verify（CLI起動込み）。WTNSファイル書込はwitness timer外。proofはJSONサイズでnative binaryと同一encodingではない。
- Noir：executeはcompile＋witness、proveはVK生成を含む。`witness_ms`/`prove_ms`へaliasするが、元の具体的なfield名も保持する。setup除外の定常prover時間とは混ぜない。
- Noirのproof出力先はsample IDごとに分離し、後の反復で前の出力を再利用しない。
- 両方式ともproof/publicのサイズだけを公開ログへ出し、実体はowner-only tmpfs内。終了・例外時に専用directoryを削除する。SIGKILL／電源断後の残存確認は必要。
- 全28sampleを保存し、warmupを除いた21件だけを集計する。summaryのsamplesは21、warmupsは7。

収集時には`distance-u16-balanced-v1`を確認し、既存collectorの条件表へ`phase_notes`とencodingを渡す。
Noirのようにcompile/VKを含むフローは、他方式のsetup除外フローと別cohortにする。
新しいPi実測・性能図・他8構成への対応、実proofによる改竄拒否の再確認は未完了。

研究PoCの合成距離計算。観測の真実性、DRIP trust chain、hardware／航空機認証を保証しない。
実capture・実座標・private key・使い捨てsetup/VK/proof実体は公開・deployしない。
