from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from cx2pages.models import FetchRun, Snapshot
from cx2pages.scraper import fetch_ranking, parse_rank_rows_from_text
from cx2pages.site import Settings as SiteSettings, render_site
from cx2pages.state import add_fetch_run, add_or_replace_snapshot, load_state, prune_snapshots, save_state
from cx2pages.utils import JST, to_utc, utcnow


def _env_or_none(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _env_int(name: str, default: int) -> int:
    value = _env_or_none(name)
    if value is None:
        return default
    return int(value)


DEFAULT_SERVER_LABEL = os.getenv("CX2_SERVER_LABEL", "Jupiter-002")
DEFAULT_GAME_COOKIE = _env_or_none("CX2_GAME_COOKIE")
DEFAULT_GAME_USERID = _env_or_none("CX2_GAME_USERID")
DEFAULT_GAME_PASSWORD = _env_or_none("CX2_GAME_PASSWORD")
DEFAULT_GAME_SERVER_ID = _env_int("CX2_GAME_SERVER_ID", 212)
DEFAULT_GAME_NICKNAME = _env_or_none("CX2_GAME_NICKNAME")
DEFAULT_GAME_DIRECTION = _env_int("CX2_GAME_DIRECTION", 0)
DEFAULT_GAME_PREFER_BRANCH = os.getenv("CX2_GAME_PREFER_BRANCH", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
DEFAULT_GAME_SOURCE_URL = _env_or_none("CX2_GAME_SOURCE_URL") or (
    "https://game-jp-02.conquerx2.com/?mid=game&act=dispGameRank&rankview=user&ranktype=0"
)
DEFAULT_EXPORT_BASE_URL = os.getenv(
    "CX2_EXPORT_BASE_URL",
    "https://jp.conquerx2.com/export/game-jp-02.conquerx2.com",
)
DEFAULT_SOURCE_URL = _env_or_none("CX2_SOURCE_URL") or (
    DEFAULT_GAME_SOURCE_URL
    if DEFAULT_GAME_COOKIE or (DEFAULT_GAME_USERID and DEFAULT_GAME_PASSWORD)
    else DEFAULT_EXPORT_BASE_URL
)
DEFAULT_SITE_LINK_URL = _env_or_none("CX2_SERVER_RANK_URL") or (
    None if "act=dispGameRank" in DEFAULT_SOURCE_URL else f"{DEFAULT_EXPORT_BASE_URL.rstrip('/')}/users.txt"
)
DEFAULT_USER_AGENT = os.getenv(
    "USER_AGENT",
    "cx2-rankwatch-pages/1.0 (+https://github.com/; public ranking collector)",
)
DEFAULT_TIMEOUT = _env_int("HTTP_TIMEOUT_SECONDS", 30)
PROJECT_ROOT = Path(__file__).resolve().parent
STATE_PATH = PROJECT_ROOT / "data" / "state.json"
DOCS_DIR = PROJECT_ROOT / "docs"


def _source_label() -> str:
    if "act=dispGameRank" in DEFAULT_SOURCE_URL:
        if DEFAULT_GAME_USERID and DEFAULT_GAME_PASSWORD:
            return "game rank (auto-login)"
        return "game rank (authenticated)"
    return "export users.txt"


def _site_settings() -> SiteSettings:
    return SiteSettings(
        server_label=DEFAULT_SERVER_LABEL,
        server_rank_url=DEFAULT_SITE_LINK_URL,
        source_label=_source_label(),
    )


def command_build() -> int:
    state = load_state(STATE_PATH)
    render_site(PROJECT_ROOT, DOCS_DIR, _site_settings(), state)
    save_state(STATE_PATH, state)
    print(f"Built static site into {DOCS_DIR}")
    return 0


def command_import_fixture(path: str, captured_at: str) -> int:
    state = load_state(STATE_PATH)
    text = Path(path).read_text(encoding="utf-8")
    rows = parse_rank_rows_from_text(text, DEFAULT_SERVER_LABEL)
    parsed_dt = datetime.fromisoformat(captured_at)
    if parsed_dt.tzinfo is None:
        parsed_dt = parsed_dt.replace(tzinfo=JST)
    captured_at_utc = to_utc(parsed_dt)

    snapshot = Snapshot(
        captured_at_utc=captured_at_utc,
        rows=rows,
        source_url=DEFAULT_SITE_LINK_URL,
        http_status=200,
        content_sha256=None,
    )
    add_or_replace_snapshot(state, snapshot)
    add_fetch_run(
        state,
        FetchRun(
            started_at_utc=utcnow(),
            status="ok",
            row_count=len(rows),
            http_status=200,
            message="fixture import",
            url=DEFAULT_SITE_LINK_URL,
        ),
    )
    prune_snapshots(state)
    save_state(STATE_PATH, state)
    render_site(PROJECT_ROOT, DOCS_DIR, _site_settings(), state)
    print(f"Imported fixture and rebuilt site: {path}")
    return 0


def command_update() -> int:
    state = load_state(STATE_PATH)
    started_at = utcnow()
    try:
        result = fetch_ranking(
            server_label=DEFAULT_SERVER_LABEL,
            url=DEFAULT_SOURCE_URL,
            user_agent=DEFAULT_USER_AGENT,
            timeout_seconds=DEFAULT_TIMEOUT,
            cookie_header=DEFAULT_GAME_COOKIE,
            game_userid=DEFAULT_GAME_USERID,
            game_password=DEFAULT_GAME_PASSWORD,
            game_server_id=DEFAULT_GAME_SERVER_ID,
            game_nickname=DEFAULT_GAME_NICKNAME,
            game_direction=DEFAULT_GAME_DIRECTION,
            game_prefer_branch=DEFAULT_GAME_PREFER_BRANCH,
        )
        snapshot = Snapshot(
            captured_at_utc=started_at,
            rows=result.rows,
            source_url=result.url,
            http_status=result.http_status,
            content_sha256=result.content_sha256,
        )
        add_or_replace_snapshot(state, snapshot)
        add_fetch_run(
            state,
            FetchRun(
                started_at_utc=started_at,
                status="ok",
                row_count=len(result.rows),
                http_status=result.http_status,
                message=None,
                url=result.url,
            ),
        )
        prune_snapshots(state)
        save_state(STATE_PATH, state)
        render_site(PROJECT_ROOT, DOCS_DIR, _site_settings(), state)
        print(f"Fetched {len(result.rows)} rows and rebuilt site")
        return 0
    except Exception as exc:
        add_fetch_run(
            state,
            FetchRun(
                started_at_utc=started_at,
                status="error",
                row_count=None,
                http_status=None,
                message=str(exc),
                url=DEFAULT_SOURCE_URL,
            ),
        )
        save_state(STATE_PATH, state)
        render_site(PROJECT_ROOT, DOCS_DIR, _site_settings(), state)
        print(f"Fetch failed, site rebuilt with previous data: {exc}", file=sys.stderr)
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CX2 Jupiter-002 static GitHub Pages site")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build", help="Build static site from current state.json")
    subparsers.add_parser("update", help="Fetch ranking, update state.json, rebuild docs/")
    import_parser = subparsers.add_parser("import-fixture", help="Import a local ranking file for testing")
    import_parser.add_argument("path")
    import_parser.add_argument("--captured-at", default="2026-03-08T00:00:00+09:00")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "build":
        return command_build()
    if args.command == "update":
        return command_update()
    if args.command == "import-fixture":
        return command_import_fixture(args.path, args.captured_at)
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
