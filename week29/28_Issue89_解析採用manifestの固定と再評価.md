# Issue89：解析採用manifestの固定と既存評価の再実行

## 完了した範囲

時刻・GPS監査、取得間隔、距離分析で用いていた入力と採用条件を、一つの機械可読manifestへまとめた。行単位の採否はprivate capturesだけに保持し、Git用には匿名の件数・理由・未成立条件を出力した。C/Dの4時間監視には操作を行っていない。

新たな測位精度・検出性能の実験ではなく、既存の実測解析の再現性を確保する作業である。Issue89全体の完了ではない。

## 採用条件と分母

同端末内の時刻・測位対応を既存監査が通過した行を前提に、既知boot、正の観測monotonic時刻、測位時刻差0〜2秒、OS水平精度0〜20m、正の申告水平距離、精度申告／申告距離が0.25以下、有限RSSIを要求する。20m・0.25は既存解析に用いた探索的条件であり、真値精度を保証する閾値ではない。

| 端末 | 対象申告IDの保存行 | 採用 | 保留 | 今回の保留理由 |
|---|---:|---:|---:|---|
| Pixel（6 Pro） | 132 | 105 | 27 | 精度申告／申告水平距離が0.25超 |
| ASUS-1 | 146 | 0 | 146 | 同上 |
| ASUS-2 | 46 | 0 | 46 | 同上 |
| Pixel 8 | 0 | 0 | 0 | 対象行なし。GPS不良・受信率0%とは判定しない |

分母は324保存行。独立した物理パケット数・送信総数ではない。ASUS-1の146観測キーは40種類のPack内容、ASUS-2の46観測キーは12種類の内容で、同内容の反復が含まれる。採用されなかったことを端末一般の性能順位とはしない。

[公開manifest](results/issue89-quality-manifest-a/manifest.json)／[採用件数CSV](results/issue89-quality-manifest-a/selection-counts.csv)。排他的な最初の保留理由と、重複を許す全理由の件数を分けた。

## 入力の保持・改変拒否

- 既存位置CSV・監査集計・間隔集計・時刻監査・距離分析のSHA-256をprivate manifestに束縛した。
- 元SQLite 4件が既存位置監査時のハッシュと一致することを確認した。DBを変更していない。
- 対象行の分母が位置監査と間隔監査で一致しない場合、元DBの変更、従来の距離分析と採用件数が異なる場合は停止する。
- private maskは位置CSVの行順とハッシュに束縛する。利用時はポリシーと各行の採否・理由を再計算し、入力差し替えやmaskの改変を拒否する。
- 元CSVにない個別の鮮度／mock情報は独立に再判定したと主張しない。既存の時刻・位置照合結果を継承し、その証拠ファイルを束縛する。
- private manifestは秘密鍵署名付きの証拠ではない。署名・ハード認証・独立真値を新たに提供しない。

## 下流評価の実行結果

距離分析とIssue96の評価に`--selection-manifest`を追加し、凍結したマスクで再実行した。オプション未指定時の既存挙動は維持した。

- 距離分析のノード別統計は旧結果と一致。
- 採用105行、時間分割52／26／27行、モデル・閾値・警報率は旧結果と一致。
- 攻撃集計CSVと時間block別CSVは旧結果とバイト単位で一致。
- 未改変の警報率13/27＝48.15%という不十分な結果を維持した。manifestを導入したことで検出器が採用可能になったとは評価しない。

[再実行照合](results/issue89-quality-manifest-a/downstream-verification.json)／[距離集計](results/issue89-manifest-distance-a/summary.json)／[合成攻撃評価](results/issue89-manifest-attacks-a/summary.json)。RSSIは実測、位置変更・電力加算は合成条件。

## 未成立の条件・残件

独立した暦時刻アンカーは0件。端末間の確定同期、同一物理送信、3D高度基準、独立真位置、PDR、機種間の公平な受信性能比較は未成立として固定した。水平解析を通った行をこれらの用途へ自動昇格させない。#95の同一送信候補分類を今回新たに実行したわけではない。

追加の独立時刻根拠・高度基準・真値が得られた場合は、証拠監査と明示的な新ポリシーを作成する。今回のmaskを上書きしない。

## 再現

入力設定は`captures/week29/issue89-quality-manifest-input-private.json`。位置CSV、位置監査・間隔監査・時刻監査・距離集計、元DBの監査manifestを指定する。接続情報や生座標は公開しない。

```sh
python3 week29/scripts/build_quality_manifest.py \
  --config captures/week29/issue89-quality-manifest-input-private.json \
  --private-output captures/week29/issue89-quality-manifest-a \
  --output week29/results/issue89-quality-manifest-a

.cache/week26-mac-venv/bin/python week29/scripts/analyze_claim_distance_rssi.py \
  --positions captures/week29/issue91-position-a/target-position-quality-private.csv \
  --selection-manifest captures/week29/issue89-quality-manifest-a/selection-private.json \
  --output week29/results/issue89-manifest-distance-a

.cache/week26-mac-venv/bin/python week29/scripts/evaluate_claim_attacks.py \
  --positions captures/week29/issue91-position-a/target-position-quality-private.csv \
  --selection-manifest captures/week29/issue89-quality-manifest-a/selection-private.json \
  --private-output captures/week29/issue89-manifest-attacks-a \
  --output week29/results/issue89-manifest-attacks-a

python3 -m unittest discover -s week29/tests -v
```

manifest生成の出力先は新規ディレクトリを指定する。再実行時は別名へ変更する。private出力は0700／0600、非symlinkのcaptures配下に限定した。

## 検証

新規8テスト：採用境界、古い／不明な時刻、負値・非有限値、分母不一致、上流の変更、採用件数不一致、mask改変、入力変更、未成立保証の維持を確認した。

Week29全69件、UAV88件、Go、contracts48件は成功。既存成果を削除せず別出力へ実行した。コード／MDのcommit・push・GitHub Actions実行は未実施。
