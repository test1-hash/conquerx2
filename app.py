from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, abort, jsonify, send_from_directory

from cx2pages.state import latest_snapshot, load_state
from cx2pages.utils import JST, parse_iso_datetime
from manage import DOCS_DIR, PROJECT_ROOT, STATE_PATH, command_build, command_update


LOG = logging.getLogger("cx2pages.railway")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

BUNDLED_STATE_PATH = PROJECT_ROOT / "data" / "state.json"
BUNDLED_DOCS_DIR = PROJECT_ROOT / "docs"

_SCHEDULER_LOCK = threading.Lock()
_SCHEDULER_STARTED = False


def _is_enabled(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _ensure_seed_data() -> None:
    if not STATE_PATH.exists() and BUNDLED_STATE_PATH.exists():
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BUNDLED_STATE_PATH, STATE_PATH)
    if not DOCS_DIR.exists() and BUNDLED_DOCS_DIR.exists():
        shutil.copytree(BUNDLED_DOCS_DIR, DOCS_DIR, dirs_exist_ok=True)


def _latest_snapshot_dt_jst() -> datetime | None:
    state = load_state(STATE_PATH)
    latest = latest_snapshot(state)
    if latest is None:
        return None
    return parse_iso_datetime(latest["captured_at_utc"]).astimezone(JST)


def _current_hour_already_fetched(now: datetime) -> bool:
    latest_dt = _latest_snapshot_dt_jst()
    if latest_dt is None:
        return False
    return (
        latest_dt.year == now.year
        and latest_dt.month == now.month
        and latest_dt.day == now.day
        and latest_dt.hour == now.hour
    )


def _run_update_if_needed() -> None:
    now = datetime.now(tz=JST)
    if now.minute < 5:
        LOG.info("Skipping update before :05 JST (%s)", now.isoformat())
        return
    if _current_hour_already_fetched(now):
        LOG.info("Skipping update; already fetched current JST hour (%s)", now.isoformat())
        return
    LOG.info("Running hourly update at %s", now.isoformat())
    command_update()


def _next_run_at(now: datetime) -> datetime:
    target = now.replace(minute=5, second=0, microsecond=0)
    if now >= target:
        target = (now + timedelta(hours=1)).replace(minute=5, second=0, microsecond=0)
    return target


def _sleep_until(target: datetime) -> None:
    while True:
        remaining = (target - datetime.now(tz=JST)).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 60))


def _scheduler_loop() -> None:
    _ensure_seed_data()
    _run_update_if_needed()
    while True:
        now = datetime.now(tz=JST)
        target = _next_run_at(now)
        LOG.info("Next scheduled fetch at %s", target.isoformat())
        _sleep_until(target)
        try:
            _run_update_if_needed()
        except Exception:
            LOG.exception("Background update failed")


def _start_scheduler_once() -> None:
    global _SCHEDULER_STARTED
    if not _is_enabled("CX2_BACKGROUND_UPDATER", True):
        return
    with _SCHEDULER_LOCK:
        if _SCHEDULER_STARTED:
            return
        thread = threading.Thread(target=_scheduler_loop, name="cx2-updater", daemon=True)
        thread.start()
        _SCHEDULER_STARTED = True


def create_app() -> Flask:
    _ensure_seed_data()
    command_build()
    _start_scheduler_once()

    app = Flask(__name__, static_folder=None)

    @app.get("/healthz")
    def healthz():
        latest_dt = _latest_snapshot_dt_jst()
        return jsonify(
            {
                "ok": True,
                "latest_snapshot_jst": latest_dt.isoformat() if latest_dt else None,
                "docs_dir": str(DOCS_DIR),
                "state_path": str(STATE_PATH),
            }
        )

    @app.route("/", defaults={"req_path": "index.html"})
    @app.route("/<path:req_path>")
    def serve(req_path: str):
        candidate = DOCS_DIR / req_path
        if candidate.is_dir():
            req_path = f"{req_path.rstrip('/')}/index.html"
            candidate = DOCS_DIR / req_path
        elif not candidate.exists() and "." not in Path(req_path).name:
            fallback = DOCS_DIR / req_path / "index.html"
            if fallback.exists():
                req_path = f"{req_path.rstrip('/')}/index.html"
                candidate = fallback
        if not candidate.exists():
            abort(404)
        return send_from_directory(DOCS_DIR, req_path)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
