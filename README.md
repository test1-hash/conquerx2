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
3. **Build and deployment** を `Deploy from a branch` にする。
4. Branch を `main`、Folder を `/docs` にする。
5. **Actions** を有効にする。
6. `hourly-update` workflow を一度手動実行するか、次の定期実行を待つ。

これで `docs/` 以下が毎時間更新され、GitHub Pages で公開されます。

## ファイル構成

- `manage.py` : 取得・再生成コマンド
- `data/state.json` : 取得履歴のテキスト保存先
- `docs/` : 公開される静的サイト
- `.github/workflows/hourly-update.yml` : 毎時更新

## 注意

- GitHub Pages で無料公開する場合、個人アカウントでは通常 **public repository** が必要です。
- 取得対象は公開ランキングページです。
- `data/state.json` は毎時間更新される履歴ファイルなので、長期運用で大きくなります。必要なら `prune_snapshots()` の日数を調整してください。

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
