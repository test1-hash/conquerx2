# 無料運用の候補メモ

## 1. GitHub Pages + GitHub Actions

採用した構成です。

- 公開リポジトリなら GitHub Pages を無料で使いやすい
- 公開リポジトリの標準 GitHub-hosted runner は無料
- `schedule` で毎時間の更新が可能
- 動的サーバー不要で、今回の用途と相性が良い

## 2. Cloudflare Workers / Pages + D1 + Cron Triggers

将来的な別案です。

- Workers Free / Pages Free / D1 Free がある
- Cron Triggers で定期実行できる
- ただし今回の Flask/SQLite 構成からの載せ替えは GitHub Pages 版より少し重い

## 3. Koyeb などの無料インスタンス系

今回は見送り。

- Web Service は無料インスタンスがある
- ただし無料枠は小さく、永続ボリューム周りも強い本番向けとは言いづらい
- この用途なら静的サイト化のほうが安定しやすい
