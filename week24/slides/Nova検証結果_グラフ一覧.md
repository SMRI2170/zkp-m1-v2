# Novaの検証グラフ

Novaは未着手ではなく、SonobeのNova / CycleFoldについて実行済み。Microsoft Novaの圧縮APIのソース調査とは区別する。

## 個別グラフ

| 図 | 見るもの | 範囲 |
|---|---|---|
| [生成・検証時間](../figures/nova-validation-v2/nova-step-times.png) | 7stepそれぞれの生成・検証時間 | Piの単一Prover raw IVC。異なる7入力を各1回 |
| [メモリ推移](../figures/nova-validation-v2/nova-memory.png) | 実行全体のcgroupメモリ | 完走したNova v2のみ。setup・初期処理・負例検査を含む |
| [改竄拒否数](../figures/nova-validation-v2/nova-tamper.png) | A/B/Cと両Hで各22件を拒否 | 固定Sonobe mainのtoy回路。計132件 |
| [生状態の識別用入力](../figures/nova-validation-v2/nova-canaries.png) | 当該段の入力7個がincoming Witnessに残ること | 生状態の配列を読む検査。暗号を解読した結果ではない |

各図は同じディレクトリにSVG版も保存した。

## 数値と元記録

- [Piの7step CSV](../figures/nova-validation-v2/pi-steps.csv)
- [固定main検査の集計CSV](../figures/nova-validation-v2/security.csv)
- [元ログのSHA-256](../figures/nova-validation-v2/sources.json)
- [Pi測定報告](../03_ユークリッド距離_各方式のPi実装.md)
- [旧版の再現と固定mainの比較](../../week23/03_旧Sonobe_Witness露出再現.md)

Piでは正常7stepと公開state改変21件の拒否を確認した。生成中央値1.900秒、検証中央値2.946秒、全unit 38.168秒、最大メモリ187.086 MiB。これらは外部提出用最終ZKの測定ではない。

改竄拒否と秘匿性は別の結果である。固定mainで改竄を拒否できても、生状態を別Proverへ渡すと元Witnessが渡る。旧版のRandomizedIVCProof生成・検証成功も、秘密非共有の継続経路の完成とは分ける。

初回Nova v1は現在の電源フラグでguard停止した記録を保持し、正常runと混ぜていない。OOMによる停止ではなかった。今回、証明実験は再実行せず、保存済みの公開可能な合成データのメトリクスだけから図を生成した。

## 再生成

```sh
python3 experiments/all-framework-plots/plot_nova_validation.py \
  --out week24/figures/nova-validation-new
```

新規の出力先を指定する。元の秘密assignment・生Proof・鍵を読み込む処理はなく、ログ中の件数・時間・メモリだけを使用する。
