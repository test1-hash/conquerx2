# CX2 Jupiter-002 Rankwatch

ConquerX2 の **Jupiter-002 ランキング** を定期取得し、
GitHub Pages でそのまま公開できる静的サイト一式です。

既定では公開 export を使いますが、`CX2_GAME_USERID` / `CX2_GAME_PASSWORD`
または `CX2_GAME_COOKIE` を設定すると
**ゲーム内ランキング + プレイヤー詳細 API** を優先して取得します。

## できること

- 毎時05分ごろのランキング取得
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

これで 毎時05分ごろに `docs/` が再生成され、その成果物が GitHub Pages に直接 deploy されます。

ゲーム内の hourly ランキングを使いたい場合は、あわせて repository secrets を追加します。

- 推奨: `CX2_GAME_USERID`
- 推奨: `CX2_GAME_PASSWORD`
- 任意: `CX2_GAME_SERVER_ID`
  - 既定: `212`
- 任意: `CX2_GAME_NICKNAME`
  - 専用アカウントがまだサーバー未登録なら初回だけ使います
- 任意: `CX2_GAME_DIRECTION`
  - 既定: `0`
- 任意: `CX2_GAME_PREFER_BRANCH`
  - 既定: `1`
- 旧方式: `CX2_GAME_COOKIE`
  - 例: `PHPSESSID=...; CONQUERX2=...`
- 任意: `CX2_GAME_SOURCE_URL`
  - 既定: `https://game-jp-02.conquerx2.com/?mid=game&act=dispGameRank&rankview=user&ranktype=0`
- 任意: `CX2_SERVER_RANK_URL`
  - サイトに表示するデータ元 URL を上書きしたい時だけ使います

## ファイル構成

- `manage.py` : 取得・再生成コマンド
- `data/state.json` : 取得履歴のテキスト保存先
- `docs/` : 公開される静的サイト
- `.github/workflows/hourly-update.yml` : 毎時05分ごろ更新

## 注意

- GitHub Free では GitHub Pages は **public repository** で使うのが基本です。private repository で使う場合はプラン条件を確認してください。
- `CX2_GAME_USERID` / `CX2_GAME_PASSWORD` も `CX2_GAME_COOKIE` も無い場合、取得対象は `users.txt / planets.txt / empires.txt / conquest.txt` を含む export データです。
- `CX2_GAME_USERID` / `CX2_GAME_PASSWORD` を使う場合、毎回ログインして session を作り直します。
- `CX2_GAME_COOKIE` だけを使う場合、cookie の期限切れで取得が止まります。長期運用では login secrets を推奨します。
- `data/state.json` は毎時間更新される履歴ファイルなので、長期運用で大きくなります。必要なら `prune_snapshots()` の日数を調整してください。
- GitHub Actions の `GITHUB_TOKEN` で push された commit は Pages の branch build を起こさないため、この repository では branch 公開ではなく Actions deploy を使っています。

## 変更したい設定

環境変数で変更できます。

- `CX2_SERVER_LABEL` (既定: `Jupiter-002`)
- `CX2_GAME_USERID`
- `CX2_GAME_PASSWORD`
- `CX2_GAME_SERVER_ID` (既定: `212`)
- `CX2_GAME_NICKNAME` (未登録アカウントを初回作成する時だけ)
- `CX2_GAME_DIRECTION` (既定: `0`)
- `CX2_GAME_PREFER_BRANCH` (既定: `1`)
- `CX2_GAME_COOKIE`
- `CX2_GAME_SOURCE_URL` (既定: `https://game-jp-02.conquerx2.com/?mid=game&act=dispGameRank&rankview=user&ranktype=0`)
- `CX2_SOURCE_URL` (既定: login secrets か `CX2_GAME_COOKIE` があれば game source、無ければ export base)
- `CX2_EXPORT_BASE_URL` (既定: `https://jp.conquerx2.com/export/game-jp-02.conquerx2.com`)
- `CX2_SERVER_RANK_URL` (既定: game source または `<export base>/users.txt`)
- `USER_AGENT`
- `HTTP_TIMEOUT_SECONDS`

## コマンド

```bash
python manage.py update
python manage.py build
python manage.py import-fixture <path> --captured-at 2026-03-08T00:00:00+09:00
pytest -q
```
