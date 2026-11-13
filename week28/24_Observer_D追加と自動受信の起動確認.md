# Observer D追加と自動受信の起動確認

## 導入

Dへ指定された認証情報でSSH接続し、Raspberry Pi 4 Model B Rev 1.5／Python 3.13.5／iw導入済みを確認した。実IP・MAC・ホスト鍵・boot ID・接続情報はprivate capturesにだけ保持する。

A/B/Cと同じ `boot-4ddc0bfb0bf2` を転送し、全ソースファイルのSHA-256を照合。既存アプリの保存先がないことを確認して新規ディレクトリへ配置し、observer-dとしてインストールした。既存のWi-Fi・SSH・パスワード・sudoersは変更していない。送信・hostapd・monitorの自動設定も行っていない。

受信workerのcheckとWi-Fi合成テスト21件を実行し成功した。その後 `zkp-rid-observer.service` をenable --nowし、DのOSを再起動してログイン操作なしの自動起動を確認した。enabled・active/running・NRestarts=0、60秒区間1回完了・メタデータ生成を確認。保存先の権限違反は0件、対象電波未送信で受信行0件。結果は[集計JSON](results/pi-d-boot-20261113/validation.json)に記録する。

## 使い方

電源投入→設定済みWi-Fiに接続→wlan0のupを確認→60秒単位の受信・保存。未接続時は待機する構成で、アクセスポイントなしの独立運用は今回評価していない。

```sh
systemctl status zkp-rid-observer.service
cat ~/zkp-beacon-observer/current/captures/boot-status.json
# 一時停止。次のOS起動では再開する。
sudo systemctl stop zkp-rid-observer.service
# 自動起動も停止する。
sudo systemctl disable --now zkp-rid-observer.service
```

保存先は `~/zkp-beacon-observer/current/captures/observer-d/<日時>/`。RSSI・観測時刻・生Vendor内容をobservations.jsonlとobservations.txt、メタデータをevents.jsonl／summary.jsonへ保存。ディレクトリ0700／ファイル0600。収録対象の電波がなくても空のファイルと収録メタデータが作られる。

メモリ・ディスクの保護、保存予算、再起動回数制限はA/B/Cと同じ。[自動起動設計・制限](23_Pi受信プログラムの電源投入時自動起動.md)を参照。古い収録を自動で消さず、上限時は停止する。

## 評価の範囲

この作業は機種確認・環境導入・合成テスト・OS再起動・自動受信開始・保存先権限の確認。M350やPi試験送信機は起動していない。空の収録やservice activeを、実電波の受信成功とは数えない。機体／センサー／観測ハードの認証、同一送信の多局対応、方向精度を保証しない研究PoC。

初回の情報取得と最終集計の読取り専用コマンドで括弧の誤記により失敗し、訂正後に情報を取得した。配置・データへの変更は生じていない。物理的な電源抜差し、長期負荷、実機OOM・容量満杯・ネットワーク切断注入は未実行。認証情報と生データはGitへ含めない。
