from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import Any

from .models import FetchRun, RankRow, Snapshot
from .utils import cutoff_datetime, parse_iso_datetime, truncate_to_hour, utcnow


DEFAULT_STATE = {
    "version": 1,
    "generated_at_utc": None,
    "snapshots": [],
    "fetch_runs": [],
}


def player_key(player_name: str) -> str:
    return sha1(player_name.encode("utf-8")).hexdigest()[:12]


def rankrow_to_dict(row: RankRow) -> dict[str, Any]:
    return {
        "rank_position": row.rank_position,
        "title": row.title,
        "player_name": row.player_name,
        "level": row.level,
        "planets": row.planets,
        "points": row.points,
        "avg_points": row.avg_points,
        "fleet_score": row.fleet_score,
        "empire_name": row.empire_name,
    }


def snapshot_to_dict(snapshot: Snapshot) -> dict[str, Any]:
    return {
        "captured_at_utc": snapshot.captured_at_utc.isoformat(),
        "captured_hour_utc": truncate_to_hour(snapshot.captured_at_utc).isoformat(),
        "source_url": snapshot.source_url,
        "http_status": snapshot.http_status,
        "content_sha256": snapshot.content_sha256,
        "row_count": len(snapshot.rows),
        "rows": [rankrow_to_dict(row) for row in snapshot.rows],
    }


def fetch_run_to_dict(run: FetchRun) -> dict[str, Any]:
    return {
        "started_at_utc": run.started_at_utc.isoformat(),
        "status": run.status,
        "row_count": run.row_count,
        "http_status": run.http_status,
        "message": run.message,
        "url": run.url,
    }


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "generated_at_utc": None, "snapshots": [], "fetch_runs": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if "snapshots" not in data:
        data["snapshots"] = []
    if "fetch_runs" not in data:
        data["fetch_runs"] = []
    return data


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state = dict(state)
    state["generated_at_utc"] = utcnow().isoformat()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def add_or_replace_snapshot(state: dict[str, Any], snapshot: Snapshot) -> None:
    snapshot_dict = snapshot_to_dict(snapshot)
    captured_hour = snapshot_dict["captured_hour_utc"]
    snapshots = state.setdefault("snapshots", [])
    replaced = False
    for index, existing in enumerate(snapshots):
        if existing["captured_hour_utc"] == captured_hour:
            snapshots[index] = snapshot_dict
            replaced = True
            break
    if not replaced:
        snapshots.append(snapshot_dict)
    snapshots.sort(key=lambda item: item["captured_at_utc"])


def add_fetch_run(state: dict[str, Any], run: FetchRun, limit: int = 200) -> None:
    fetch_runs = state.setdefault("fetch_runs", [])
    fetch_runs.append(fetch_run_to_dict(run))
    fetch_runs.sort(key=lambda item: item["started_at_utc"], reverse=True)
    del fetch_runs[limit:]


def prune_snapshots(state: dict[str, Any], days: int = 400) -> None:
    cutoff = cutoff_datetime(days)
    kept = [
        snapshot
        for snapshot in state.get("snapshots", [])
        if parse_iso_datetime(snapshot["captured_at_utc"]) >= cutoff
    ]
    state["snapshots"] = kept


def latest_snapshot(state: dict[str, Any]) -> dict[str, Any] | None:
    snapshots = state.get("snapshots", [])
    return snapshots[-1] if snapshots else None


def previous_snapshot(state: dict[str, Any]) -> dict[str, Any] | None:
    snapshots = state.get("snapshots", [])
    return snapshots[-2] if len(snapshots) >= 2 else None


def snapshot_at_or_before(state: dict[str, Any], target: datetime) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for snapshot in state.get("snapshots", []):
        dt = parse_iso_datetime(snapshot["captured_at_utc"])
        if dt <= target:
            best = snapshot
        else:
            break
    return best
