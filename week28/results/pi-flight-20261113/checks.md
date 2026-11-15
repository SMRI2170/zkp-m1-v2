# ローカル検証

- `python3 -m unittest discover -s experiments/week28-beacon-observers -p 'test_*.py'`：44件成功。
- `python3 -m unittest discover -s uav -p 'test_*.py'`：88件成功。
- `cd aggregator && go test ./...`：成功。
- `cd contracts && npm test`：48件成功。

実行全文はローカル `.cache/pi-flight-{tests,uav,go,contracts}.log`。公開ログはPi単体テストの集計のみ。CIの件数は公開ブランチの収録テストに従い、ローカル件数とは分ける。
