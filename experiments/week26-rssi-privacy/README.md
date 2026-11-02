# Week26：Macでの独立再解析

## Three findings: matched observations and explanation figures

`explain_three_results.py` reuses the predeclared synthetic generators. It
reproduces saved baseline counts, compares normal / position-only / joint-power
cases on the same 12,294 received events, and saves normalized score histograms.
The matched cohort is conditional on reception under both normal and attack
conditions, not an unbiased all-transmission causal estimate. No real RF or
private observation rows are written. New output directories are required.

```sh
.cache/week26-mac-venv/bin/python experiments/week26-rssi-privacy/explain_three_results.py --out week26/results/new-three-findings
.cache/week26-mac-venv/bin/python experiments/week26-rssi-privacy/plot_three_results.py week26/results/new-three-findings
```

Results: `week26/results/mac-three-findings-paired-20261102/`. Report:
[three findings and conditions](../../week26/19_3つの結論を説明する追加シミュレーション.md).
The slide deck is `week26/slides/Week26_3つの結果_条件と追加比較_v4.pptx`.


## Common-flight multi-observer scenarios

`event_scenarios.py` and `event_scenarios_config.json` define a new, entirely
synthetic experiment: one smooth 3D trajectory is observed by multiple nodes.
It compares full/partial/no overlap of physical transmissions, unknown and
variable common power, claim displacement, wrong event association and ideal
delayed upload. No real packet parsing, clocks, RF capture, ZKP, power-dependent
reception or aircraft authentication is implemented. Geometry-only reception
and normal true-position claims are favorable assumptions. A circle-layout
counterexample explicitly demonstrates the remaining geometric ambiguity.

```sh
.cache/week26-mac-venv/bin/python -u experiments/week26-rssi-privacy/event_scenarios.py \
  --out week26/results/mac-event-scenarios-reproduction
.cache/week26-mac-venv/bin/python experiments/week26-rssi-privacy/audit_event_scenarios.py \
  week26/results/mac-event-scenarios-reproduction
.cache/week26-mac-venv/bin/python experiments/week26-rssi-privacy/plot_event_scenarios.py \
  week26/results/mac-event-scenarios-reproduction
```

Dependencies: the existing `requirements-synthetic.txt`; plots require a Japanese
font (Hiragino Sans, Noto Sans CJK JP or IPAexGothic). Results include seed-level
CSV, aggregate CSV/JSON, progress/status, source/config hashes and five PNG/SVG
figure pairs. Undefined conditional rates are saved as null/blank, never zero.
The Japanese report is `week26/15_位置偽装検知の成立条件と限界_複数ノード合成評価.md`.

`identifiability_minimal.py`はGitHubから取得した合成反例。`recheck_ble.py`は文書06から再構成した別実装であり、元の添付ZIPコードではない。

## 実行

リポジトリルートで実行する。解析だけならPython標準ライブラリのみ。`--plots`はmatplotlibが必要。

```sh
python3 -m venv .cache/week26-mac-venv
.cache/week26-mac-venv/bin/pip install matplotlib
.cache/week26-mac-venv/bin/python experiments/week26-rssi-privacy/recheck_ble.py --download --plots --out week26/results/new-run
.cache/week26-mac-venv/bin/python -m unittest discover -s experiments/week26-rssi-privacy -p 'test_recheck_ble.py'
```

出力先は新規ディレクトリを指定。既存runは上書きしない。入力は固定コミットとSHA-256で検査。`--download`を省けば取得済みの`captures/week26-public-ble/`を検査・使用する。

- JSON：データ出典・ハッシュ・集計・方法・実行環境・限界。
- CSV：集計、分割別の分母／警報数／閾値、旧報告との照合。
- PNG／SVG：設定変更に対する警報率、電力設定差とRSSI中央値差。
- 原CSVはignored captures/内、owner-only。生RSSIや位置の行データを成果物へ複製しない。

結果は[報告07](../../week26/07_Macでの公開BLE再解析と再現確認.md)。公開の屋内固定BLEデータであり、UAV受信・原因特定・位置認証・ZKP実装の評価ではない。セッション交絡、セクター単位の依存、未知地点への適用限界を保持する。

## 独立3D合成評価

`simulate3d_independent.py`は文書04の元ZIPの復元ではなく、設定を明示した別実装。パラメータは例示値で、RF校正・3GPP準拠・実機評価ではない。距離回帰4手法と隠れた真値を使うOracle参考を比較する。GP／MLPの区間校正単位はパケットでなく飛行。

今回の実行環境はPython3.15.1・Mac ARM64。使用版は各runの`python-packages.txt`に保存。以下は主評価、境界重視評価、検査、描画を順に実行する例。出力は新しいrun名を指定する。

```sh
.cache/week26-mac-venv/bin/pip install -r experiments/week26-rssi-privacy/requirements-synthetic.txt
.cache/week26-mac-venv/bin/python -m unittest discover -s experiments/week26-rssi-privacy -p 'test_*.py'
.cache/week26-mac-venv/bin/python -u experiments/week26-rssi-privacy/simulate3d_independent.py --out week26/results/new-3d-run
.cache/week26-mac-venv/bin/python experiments/week26-rssi-privacy/audit_synthetic3d.py week26/results/new-3d-run
.cache/week26-mac-venv/bin/python experiments/week26-rssi-privacy/plot_synthetic3d.py week26/results/new-3d-run
.cache/week26-mac-venv/bin/python -u experiments/week26-rssi-privacy/simulate3d_independent.py --config experiments/week26-rssi-privacy/synthetic3d_threshold_config.json --out week26/results/new-threshold-run
.cache/week26-mac-venv/bin/python experiments/week26-rssi-privacy/audit_synthetic3d.py week26/results/new-threshold-run
.cache/week26-mac-venv/bin/python experiments/week26-rssi-privacy/plot_synthetic3d.py week26/results/new-threshold-run
```

重い処理は並列化せず、BLAS等も1スレッド。学習時の警告をJSONへ保存。進捗は`progress.jsonl`、失敗／完了状態は`status.json`へ記録し、既存runを上書きしない。

- `summary.csv/json`：全条件の誤差・包含率・区間幅・保留率・全件中／判定した件数中の誤り、学習設定・警告・資源。
- `flight-metrics.csv`：各seed・条件・方式・飛行の合計誤差、分母、警報・包含・判定・誤判定数。
- `scenario-ranges.csv`：発信／受信数、各条件の実効基準電力の範囲。
- `geometry-and-prior-diagnostic.json`：距離分布の偏り、RSSI不使用の定数予測対照、対応のある正常／位置のみの整合確認。
- PNG／SVG：距離誤差、包含率と保留、警報と受信、チャネル比較。図は保存済みJSONから描き直せる。

これらのrunは合成データのみ。受信率は各条件の発信数を分母とし、距離誤差等は受信件数を分母とする。欠測を誤差0にしない。詳細は[報告08](../../week26/08_Macでの独立3D非同期RSSI合成評価.md)。

## 偽装距離・端末数・時間差・RID別学習

[調査と設計09](../../week26/09_追加文献調査と感度実験の設計.md)の条件を別研究として分離した追加runner。既存runを変更しない。依存は上の`requirements-synthetic.txt`と同じ。

```sh
.cache/week26-mac-venv/bin/python -m unittest discover -s experiments/week26-rssi-privacy -p 'test_*.py'
.cache/week26-mac-venv/bin/python -u experiments/week26-rssi-privacy/sensitivity_suite.py --out week26/results/new-sensitivity-run
.cache/week26-mac-venv/bin/python experiments/week26-rssi-privacy/audit_sensitivity.py week26/results/new-sensitivity-run
.cache/week26-mac-venv/bin/python experiments/week26-rssi-privacy/plot_sensitivity.py week26/results/new-sensitivity-run
```

`sensitivity_config.json`を実行前に固定し、5研究×10seedを1スレッドで直列実行。各seedの完了ごとにCSVと進捗を保存。`status.json`はrunning／complete／failedを区別する。解析コード自体にデタッチ処理はなく、SSHやターミナル切断からの常駐保証はない。今回のMac実行は完了しており、待機中の実験はない。

- `position-*`：外向き／内向き／同距離方向、電力連動・有界連動、真距離帯別の警報数と正常対照。
- `synchronous-*`：同一パケット・複数受信の別条件。既知配置・伝搬指数を用いる申告整合性で、3D位置推定そのものではない。
- `asynchronous-*`：総データ量を固定し、ノード数だけを変更。単一RSSIのまま。
- `time-*`：実際の電力共分散を時間差で変えるOU感度実験。直前アンカーの独立真距離が既知という条件。
- `personalization-*`：共通、RID切片、縮約切片、RID別OLS。真距離ラベル量・ID差・飛行差・同名別送信機等を比較。
- `rid-improvement.csv`：共通モデル比の改善率・seed間の範囲・改善seed数。信頼区間ではない。
- `sampled-detection-limits.csv`：格子上の到達点のみ。未到達を0mとしない。

原則としてCSVは集計値のみ。実測RSSI・実座標・秘密鍵・ZKP成果物は新規生成しない。結果は[報告10](../../week26/10_偽装距離_端末数_時間差_RID別学習の追加評価.md)。実機の期待性能ではない。

## 実測残差・誤教師・モデル失効のストレス評価

[追加文献と設計11](../../week26/11_実測揺らぎ_学習汚染_モデル変化の追加調査.md)に対応。`robustness_suite.py`は前回の有利な仮定を崩す4研究で、先行論文の再現や認証機能の実装ではない。依存は同じ。

```sh
.cache/week26-mac-venv/bin/python -m unittest discover -s experiments/week26-rssi-privacy -p 'test_*.py'
.cache/week26-mac-venv/bin/python -u experiments/week26-rssi-privacy/robustness_suite.py --out week26/results/new-robustness-run
.cache/week26-mac-venv/bin/python experiments/week26-rssi-privacy/audit_robustness.py week26/results/new-robustness-run
.cache/week26-mac-venv/bin/python experiments/week26-rssi-privacy/plot_robustness.py week26/results/new-robustness-run
```

入力は`captures/week26-public-ble/`の固定SHA-256付き公開CSV3個。ディレクトリがなければ固定コミットからowner-onlyで取得。途中の不整合や改変は上書きせず停止する。既存ディレクトリに一部ファイルしかなければ、先に`recheck_ble.py --download`で取得・照合する。

- `empirical_sync-*`：原データの先頭50行の基準と後半50行の残差を区別し、セクター奇偶を入れ替えて校正／評価を分離。仮想リンクへ独立再標本化する屋内残差ストレスで、UAVや実際の複数受信機のデータではない。
- `poisoning-*`：対象IDの学習教師だけを距離2／4倍へ変更。平均・中央値・Huber切片補正。共通モデルの外部学習は保護されているという条件。
- `anchor_gate-*`：独立真距離を持つ新しいアンカーで、個別モデルを使うか保留するかを点検。点検後の攻撃は通過し得る。全件保留の誤差はnull。
- `time_mismatch-*`：真の相関時間と仮定した時間を交差させ、区間包含の破綻を保存。

4研究×10seedを直列実行し、CSVはseedごとに保存。新しい出力先を指定し、過去runを上書きしない。`status.json`がcompleteの場合に実行完了。結果は[報告12](../../week26/12_実測揺らぎと学習汚染_モデル失効の追加評価.md)。実機RF・ZKP・TEE等の作業は含まない。
## Public UAV-received LoRa reanalysis (2026-11-01)

`recheck_lora.py` downloads the pinned public Zenodo v2 archive into ignored,
owner-only `captures/week26-public-lora/`. It checks all 19 condition counts
(142,039 rows) against the data paper, and keeps coordinates and raw rows there.
The experiment uses 48 three-way run-held-out folds from 16 eligible conditions.
It evaluates causal median windows and pairing delay, then synthetic thinning
and a block-level power-compensation counterexample. It is an independent
reanalysis, not a reproduction of the source paper's algorithm or GhostBuster.
It measures UAV-received 868 MHz LoRa from a buried transmitter, not Remote ID.
The distance label is a flat-terrain slant-range proxy, not precise 3D truth.

```sh
.cache/week26-mac-venv/bin/python experiments/week26-rssi-privacy/recheck_lora.py \
  --download --out week26/results/mac-public-lora-reproduction
.cache/week26-mac-venv/bin/python experiments/week26-rssi-privacy/audit_public_lora.py \
  week26/results/mac-public-lora-reproduction
.cache/week26-mac-venv/bin/python experiments/week26-rssi-privacy/plot_public_lora.py \
  week26/results/mac-public-lora-reproduction
```

Source: https://zenodo.org/records/17339095 (CC BY 4.0).
Report: `week26/13_公開UAV実測データの入手とLoRa再解析.md`.
Other candidates with authentication/download failures are documented in that
report; their public descriptions are not treated as downloaded observations.
