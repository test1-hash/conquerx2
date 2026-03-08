# CX2 Jupiter-002 Rankwatch

ConquerX2 の **Jupiter-002 公開ランキング** を定期取得し、
GitHub Pages でそのまま公開できる静的サイト一式です。

## できること

- 毎時間の公開ランキング取得
- 最新ランキング表示
- 1h / 6h / 24h / 7d 成長率ページ
- 新規ランクイン / 圏外落ち / 帝国変更
- プレイヤーごとの履歴ページ
- `docs/data/*.json` へのデータ出力

## ローカルで確認

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py import-fixture sample_data/jupiter002_public_ranking_2026-03-08.txt --captured-at 2026-03-08T00:00:00+09:00
python manage.py build
```

`docs/index.html` をブラウザで開けば確認できます。

実データ取得は次です。

```bash
python manage.py update
```

テストは次で実行できます。

```bash
pytest -q
```

## GitHub Pages に載せる手順

1. この一式を **public repository** として GitHub に push する。
2. GitHub の **Settings → Pages** を開く。
3. **Build and deployment** の **Source** を `GitHub Actions` にする。
4. **Actions** を有効にする。
5. `hourly-update` workflow を一度手動実行するか、次の定期実行を待つ。

これで毎時間 `docs/` が再生成され、その成果物が GitHub Pages に直接 deploy されます。

## ファイル構成

- `manage.py` : 取得・再生成コマンド
- `data/state.json` : 取得履歴のテキスト保存先
- `docs/` : 公開される静的サイト
- `.github/workflows/hourly-update.yml` : 毎時更新

## 注意

- GitHub Free では GitHub Pages は **public repository** で使うのが基本です。private repository で使う場合はプラン条件を確認してください。
- 取得対象は公開ランキングページです。
- `data/state.json` は毎時間更新される履歴ファイルなので、長期運用で大きくなります。必要なら `prune_snapshots()` の日数を調整してください。
- GitHub Actions の `GITHUB_TOKEN` で push された commit は Pages の branch build を起こさないため、この repository では branch 公開ではなく Actions deploy を使っています。

## 変更したい設定

環境変数で変更できます。

- `CX2_SERVER_LABEL` (既定: `Jupiter-002`)
- `CX2_SERVER_RANK_URL` (既定: `https://jp.conquerx2.com/page/rank&view=personal&sid=212`)
- `USER_AGENT`
- `HTTP_TIMEOUT_SECONDS`

## コマンド

```bash
python manage.py update
python manage.py build
python manage.py import-fixture <path> --captured-at 2026-03-08T00:00:00+09:00
pytest -q
```
