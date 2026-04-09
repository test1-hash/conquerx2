from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from .state import latest_snapshot, player_key, previous_snapshot, snapshot_at_or_before
from .svg import sparkline_svg
from .utils import (
    format_int,
    format_signed,
    format_signed_float,
    hours_between,
    jst_string,
    parse_iso_datetime,
)


DEFAULT_WINDOWS = (1, 6, 24, 168)


@dataclass(slots=True)
class Settings:
    server_label: str
    server_rank_url: str | None
    source_label: str


def _page_context(*, current_page: str, heading: str, kicker: str, summary: str) -> dict[str, str]:
    return {
        "current_page": current_page,
        "page_heading": heading,
        "page_kicker": kicker,
        "page_summary": summary,
    }


def _env(template_dir: Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.globals.update(
        fmt_int=format_int,
        fmt_signed=format_signed,
        fmt_signed_float=format_signed_float,
        empire_key=empire_key,
        jst_string=jst_string,
        windows=DEFAULT_WINDOWS,
    )
    return env


def _rows_by_name(snapshot: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not snapshot:
        return {}
    return {row["player_name"]: row for row in snapshot["rows"]}


def empire_key(empire_name: str) -> str:
    return player_key(f"empire:{empire_name}")


def _aggregate_empire_snapshot(snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not snapshot:
        return []

    grouped: dict[str, dict[str, Any]] = {}
    for source_row in snapshot["rows"]:
        empire_name = (source_row.get("empire_name") or "").strip()
        if not empire_name:
            continue
        row = _normalize_row(source_row)
        bucket = grouped.setdefault(
            empire_name,
            {
                "empire_name": empire_name,
                "member_count": 0,
                "planets": 0,
                "points": 0,
                "fleet_score_total": 0,
                "fleet_observations": 0,
                "top_player_name": None,
                "top_player_points": None,
            },
        )
        bucket["member_count"] += 1
        bucket["planets"] += row["planets"]
        bucket["points"] += row["points"]
        if row.get("fleet_score") is not None:
            bucket["fleet_score_total"] += row["fleet_score"]
            bucket["fleet_observations"] += 1
        if bucket["top_player_points"] is None or row["points"] > bucket["top_player_points"]:
            bucket["top_player_name"] = row["player_name"]
            bucket["top_player_points"] = row["points"]

    board: list[dict[str, Any]] = []
    for bucket in grouped.values():
        member_count = bucket["member_count"]
        fleet_score = bucket["fleet_score_total"] if bucket["fleet_observations"] > 0 else None
        board.append(
            {
                "empire_name": bucket["empire_name"],
                "empire_key": empire_key(bucket["empire_name"]),
                "member_count": member_count,
                "planets": bucket["planets"],
                "points": bucket["points"],
                "fleet_score": fleet_score,
                "points_per_member": bucket["points"] / member_count if member_count > 0 else None,
                "fleet_share": fleet_score / bucket["points"] if fleet_score is not None and bucket["points"] > 0 else None,
                "top_player_name": bucket["top_player_name"],
                "top_player_points": bucket["top_player_points"],
            }
        )

    board.sort(
        key=lambda item: (
            -item["points"],
            -(item["fleet_score"] if item["fleet_score"] is not None else -1),
            -item["member_count"],
            item["empire_name"].casefold(),
        )
    )
    for index, row in enumerate(board, start=1):
        row["rank_position"] = index
    return board


def _empire_rows_by_name(snapshot: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {row["empire_name"]: row for row in _aggregate_empire_snapshot(snapshot)}


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "empire_key": empire_key(row["empire_name"]) if row.get("empire_name") else None,
        "fleet_score": row.get("fleet_score"),
    }


def _has_title(rows: list[dict[str, Any]]) -> bool:
    return any(row.get("title") for row in rows)


def _has_level(rows: list[dict[str, Any]]) -> bool:
    return any(row.get("level") is not None for row in rows)


def _has_fleet(rows: list[dict[str, Any]]) -> bool:
    return any(row.get("fleet_score") is not None for row in rows)


def _fleet_window_availability(rows: list[dict[str, Any]], *, windows: tuple[int, ...] = DEFAULT_WINDOWS) -> dict[int, bool]:
    return {
        hours: any(
            row["comparisons"].get(hours, {}).get("delta_fleet") is not None
            for row in rows
        )
        for hours in windows
    }


def _has_fleet_delta(rows: list[dict[str, Any]], window: int) -> bool:
    return any(
        row["comparisons"].get(window, {}).get("delta_fleet") is not None
        for row in rows
    )


def build_board(state: dict[str, Any], *, windows: tuple[int, ...] = DEFAULT_WINDOWS) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[int, dict[str, Any]]]:
    latest = latest_snapshot(state)
    if latest is None:
        return None, [], {}

    latest_dt = parse_iso_datetime(latest["captured_at_utc"])
    previous = previous_snapshot(state)
    previous_by_name = _rows_by_name(previous)

    comparison_snapshots: dict[int, dict[str, Any]] = {}
    comparison_rows: dict[int, dict[str, dict[str, Any]]] = {}
    for hours in windows:
        snap = snapshot_at_or_before(state, latest_dt - timedelta(hours=hours))
        if snap is not None:
            comparison_snapshots[hours] = snap
        comparison_rows[hours] = _rows_by_name(snap)

    board: list[dict[str, Any]] = []
    for row in latest["rows"]:
        normalized_row = _normalize_row(row)
        player_name = row["player_name"]
        fleet_score = normalized_row["fleet_score"]
        comparisons: dict[int, dict[str, Any]] = {}
        for hours in windows:
            snap = comparison_snapshots.get(hours)
            old_row = comparison_rows.get(hours, {}).get(player_name)
            if snap is None or old_row is None:
                continue
            elapsed_hours = hours_between(latest_dt, parse_iso_datetime(snap["captured_at_utc"]))
            delta_points = row["points"] - old_row["points"]
            delta_rank = old_row["rank_position"] - row["rank_position"]
            delta_level = None
            if row.get("level") is not None and old_row.get("level") is not None:
                delta_level = row["level"] - old_row["level"]
            delta_planets = row["planets"] - old_row["planets"]
            delta_fleet = None
            fleet_per_hour = None
            if fleet_score is not None and old_row.get("fleet_score") is not None:
                delta_fleet = fleet_score - old_row["fleet_score"]
                fleet_per_hour = delta_fleet / elapsed_hours if elapsed_hours > 0 else 0.0
            comparisons[hours] = {
                "snapshot_time_utc": snap["captured_at_utc"],
                "elapsed_hours": elapsed_hours,
                "delta_points": delta_points,
                "delta_rank": delta_rank,
                "delta_level": delta_level,
                "delta_planets": delta_planets,
                "delta_fleet": delta_fleet,
                "fleet_per_hour": fleet_per_hour,
                "points_per_hour": delta_points / elapsed_hours if elapsed_hours > 0 else 0.0,
            }

        board.append(
            {
                **normalized_row,
                "player_key": player_key(player_name),
                "comparisons": comparisons,
                "fleet_share": fleet_score / row["points"] if fleet_score is not None and row["points"] > 0 else None,
                "is_new_since_previous": bool(previous is not None and player_name not in previous_by_name),
            }
        )

    board.sort(key=lambda item: item["rank_position"])
    return latest, board, comparison_snapshots


def build_empire_board(state: dict[str, Any], *, windows: tuple[int, ...] = DEFAULT_WINDOWS) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[int, dict[str, Any]]]:
    latest = latest_snapshot(state)
    if latest is None:
        return None, [], {}

    latest_dt = parse_iso_datetime(latest["captured_at_utc"])
    latest_rows = _aggregate_empire_snapshot(latest)
    previous = previous_snapshot(state)
    previous_by_name = _empire_rows_by_name(previous)

    comparison_snapshots: dict[int, dict[str, Any]] = {}
    comparison_rows: dict[int, dict[str, dict[str, Any]]] = {}
    for hours in windows:
        snap = snapshot_at_or_before(state, latest_dt - timedelta(hours=hours))
        if snap is not None:
            comparison_snapshots[hours] = snap
        comparison_rows[hours] = _empire_rows_by_name(snap)

    board: list[dict[str, Any]] = []
    for row in latest_rows:
        empire_name = row["empire_name"]
        fleet_score = row.get("fleet_score")
        comparisons: dict[int, dict[str, Any]] = {}
        for hours in windows:
            snap = comparison_snapshots.get(hours)
            old_row = comparison_rows.get(hours, {}).get(empire_name)
            if snap is None or old_row is None:
                continue
            elapsed_hours = hours_between(latest_dt, parse_iso_datetime(snap["captured_at_utc"]))
            delta_points = row["points"] - old_row["points"]
            delta_rank = old_row["rank_position"] - row["rank_position"]
            delta_planets = row["planets"] - old_row["planets"]
            delta_members = row["member_count"] - old_row["member_count"]
            delta_fleet = None
            fleet_per_hour = None
            if fleet_score is not None and old_row.get("fleet_score") is not None:
                delta_fleet = fleet_score - old_row["fleet_score"]
                fleet_per_hour = delta_fleet / elapsed_hours if elapsed_hours > 0 else 0.0
            comparisons[hours] = {
                "snapshot_time_utc": snap["captured_at_utc"],
                "elapsed_hours": elapsed_hours,
                "delta_points": delta_points,
                "delta_rank": delta_rank,
                "delta_planets": delta_planets,
                "delta_members": delta_members,
                "delta_fleet": delta_fleet,
                "fleet_per_hour": fleet_per_hour,
                "points_per_hour": delta_points / elapsed_hours if elapsed_hours > 0 else 0.0,
            }

        board.append(
            {
                **row,
                "comparisons": comparisons,
                "is_new_since_previous": bool(previous is not None and empire_name not in previous_by_name),
            }
        )

    board.sort(key=lambda item: item["rank_position"])
    return latest, board, comparison_snapshots


def get_growth_rows(state: dict[str, Any], window_hours: int) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[str, Any] | None]:
    latest, board, comparison_snapshots = build_board(state, windows=(window_hours,))
    comparison = comparison_snapshots.get(window_hours)
    rows = [row for row in board if row["comparisons"].get(window_hours)]
    rows.sort(key=lambda item: (-item["comparisons"][window_hours]["delta_points"], item["rank_position"]))
    return latest, rows, comparison


def get_fleet_rows(state: dict[str, Any], *, windows: tuple[int, ...] = DEFAULT_WINDOWS) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[int, dict[str, Any]]]:
    latest, board, comparison_snapshots = build_board(state, windows=windows)
    fleet_rows = [row for row in board if row.get("fleet_score") is not None]
    fleet_rows.sort(
        key=lambda item: (-item["fleet_score"], item["rank_position"], item["player_name"].casefold())
    )
    ranked_rows = [
        {
            **row,
            "fleet_rank_position": index,
        }
        for index, row in enumerate(fleet_rows, start=1)
    ]
    return latest, ranked_rows, comparison_snapshots


def get_recent_changes(state: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, list[dict[str, Any]]]]:
    latest = latest_snapshot(state)
    previous = previous_snapshot(state)
    changes = {"entered": [], "dropped": [], "empire_changed": []}
    if latest is None or previous is None:
        return latest, previous, changes

    latest_by_name = _rows_by_name(latest)
    previous_by_name = _rows_by_name(previous)

    for name, row in latest_by_name.items():
        if name not in previous_by_name:
            changes["entered"].append({**_normalize_row(row), "player_key": player_key(name)})
    for name, row in previous_by_name.items():
        if name not in latest_by_name:
            changes["dropped"].append({**_normalize_row(row), "player_key": player_key(name)})
    for name, row in latest_by_name.items():
        if name in previous_by_name:
            old_row = previous_by_name[name]
            if (row.get("empire_name") or "") != (old_row.get("empire_name") or ""):
                changes["empire_changed"].append(
                    {
                        "player_name": name,
                        "player_key": player_key(name),
                        "rank_position": row["rank_position"],
                        "old_empire": old_row.get("empire_name"),
                        "old_empire_key": empire_key(old_row["empire_name"]) if old_row.get("empire_name") else None,
                        "new_empire": row.get("empire_name"),
                        "new_empire_key": empire_key(row["empire_name"]) if row.get("empire_name") else None,
                    }
                )

    changes["entered"].sort(key=lambda item: item["rank_position"])
    changes["dropped"].sort(key=lambda item: item["rank_position"])
    changes["empire_changed"].sort(key=lambda item: item["rank_position"])
    return latest, previous, changes


def get_player_history(state: dict[str, Any], player_name: str) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for snapshot in state.get("snapshots", []):
        for row in snapshot["rows"]:
            if row["player_name"] == player_name:
                history.append({
                    **_normalize_row(row),
                    "captured_at_utc": snapshot["captured_at_utc"],
                })
    history.sort(key=lambda item: item["captured_at_utc"])
    return history


def get_empire_history(state: dict[str, Any], empire_name: str) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for snapshot in state.get("snapshots", []):
        row = _empire_rows_by_name(snapshot).get(empire_name)
        if row is None:
            continue
        history.append(
            {
                **row,
                "captured_at_utc": snapshot["captured_at_utc"],
            }
        )
    history.sort(key=lambda item: item["captured_at_utc"])
    return history


def _history_with_previous_deltas(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points_with_deltas: list[dict[str, Any]] = []
    previous_point: dict[str, Any] | None = None
    for point in history:
        delta_points = None
        delta_fleet = None
        if previous_point is not None:
            delta_points = point["points"] - previous_point["points"]
            if (
                point.get("fleet_score") is not None
                and previous_point.get("fleet_score") is not None
            ):
                delta_fleet = point["fleet_score"] - previous_point["fleet_score"]
        points_with_deltas.append(
            {
                **point,
                "delta_points_from_previous": delta_points,
                "delta_fleet_from_previous": delta_fleet,
            }
        )
        previous_point = point
    return points_with_deltas


def export_data_json(out_dir: Path, settings: Settings, state: dict[str, Any]) -> None:
    data_dir = out_dir / "data"
    empires_dir = data_dir / "empires"
    players_dir = data_dir / "players"
    data_dir.mkdir(parents=True, exist_ok=True)
    empires_dir.mkdir(parents=True, exist_ok=True)
    players_dir.mkdir(parents=True, exist_ok=True)

    latest, board, comparison_snapshots = build_board(state)
    latest_payload = {
        "server_label": settings.server_label,
        "server_rank_url": settings.server_rank_url,
        "latest": latest,
        "comparison_snapshots": comparison_snapshots,
        "rows": board,
    }
    (data_dir / "latest.json").write_text(json.dumps(latest_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    latest_fleet, fleet_rows, fleet_comparison_snapshots = get_fleet_rows(state)
    fleet_payload = {
        "server_label": settings.server_label,
        "server_rank_url": settings.server_rank_url,
        "latest": latest_fleet,
        "comparison_snapshots": fleet_comparison_snapshots,
        "rows": fleet_rows,
    }
    (data_dir / "fleet.json").write_text(json.dumps(fleet_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    latest_empires, empire_board, empire_comparison_snapshots = build_empire_board(state)
    empire_payload = {
        "server_label": settings.server_label,
        "server_rank_url": settings.server_rank_url,
        "latest": latest_empires,
        "comparison_snapshots": empire_comparison_snapshots,
        "rows": empire_board,
    }
    (data_dir / "empires.json").write_text(json.dumps(empire_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    fetch_runs = state.get("fetch_runs", [])[:50]
    (data_dir / "fetch_runs.json").write_text(json.dumps(fetch_runs, ensure_ascii=False, indent=2), encoding="utf-8")

    latest2, previous2, changes = get_recent_changes(state)
    changes_payload = {"latest": latest2, "previous": previous2, "changes": changes}
    (data_dir / "changes.json").write_text(json.dumps(changes_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    growth_manifest: dict[str, Any] = {}
    for window in DEFAULT_WINDOWS:
        latest_g, rows, comparison = get_growth_rows(state, window)
        payload = {"latest": latest_g, "comparison": comparison, "rows": rows}
        growth_manifest[str(window)] = {
            "latest": latest_g,
            "comparison": comparison,
            "count": len(rows),
        }
        (data_dir / f"growth-{window}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (data_dir / "growth-index.json").write_text(json.dumps(growth_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    player_index: list[dict[str, Any]] = []
    player_names = sorted({row["player_name"] for snap in state.get("snapshots", []) for row in snap["rows"]}, key=str.casefold)
    for player_name in player_names:
        history = get_player_history(state, player_name)
        key = player_key(player_name)
        payload = {
            "player_name": player_name,
            "player_key": key,
            "history": history,
        }
        player_index.append({"player_name": player_name, "player_key": key, "observations": len(history)})
        (players_dir / f"{key}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (data_dir / "players.json").write_text(json.dumps(player_index, ensure_ascii=False, indent=2), encoding="utf-8")

    empire_index: list[dict[str, Any]] = []
    empire_names = sorted(
        {
            row["empire_name"]
            for snap in state.get("snapshots", [])
            for row in _aggregate_empire_snapshot(snap)
        },
        key=str.casefold,
    )
    for empire_name in empire_names:
        history = get_empire_history(state, empire_name)
        key = empire_key(empire_name)
        payload = {
            "empire_name": empire_name,
            "empire_key": key,
            "history": history,
        }
        empire_index.append({"empire_name": empire_name, "empire_key": key, "observations": len(history)})
        (empires_dir / f"{key}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (data_dir / "empires-index.json").write_text(json.dumps(empire_index, ensure_ascii=False, indent=2), encoding="utf-8")


def render_site(project_root: Path, out_dir: Path, settings: Settings, state: dict[str, Any]) -> None:
    template_dir = project_root / "templates"
    assets_dir = project_root / "site_assets"
    env = _env(template_dir)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    shutil.copytree(assets_dir, out_dir / "static")

    latest, board, comparison_snapshots = build_board(state)
    latest_empires, empire_board, empire_comparison_snapshots = build_empire_board(state)
    latest_fleet, fleet_rows, fleet_comparison_snapshots = get_fleet_rows(state)
    fetch_runs = state.get("fetch_runs", [])[:50]

    context_base = {
        "server_label": settings.server_label,
        "server_rank_url": settings.server_rank_url,
        "source_label": settings.source_label,
    }

    index_html = env.get_template("index.html").render(
        **context_base,
        **_page_context(
            current_page="index",
            heading=f"{settings.server_label} Rankwatch",
            kicker="Live Command View",
            summary="総合順位、戦力、帝国、毎時差分を一画面で追えるライブボードです。",
        ),
        page_title=f"{settings.server_label} Rankwatch",
        latest=latest,
        board=board,
        show_title=_has_title(board),
        show_level=_has_level(board),
        show_fleet=_has_fleet(board),
        comparison_snapshots=comparison_snapshots,
        fetch_runs=fetch_runs,
    )
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")

    empires_html = env.get_template("empires.html").render(
        **context_base,
        **_page_context(
            current_page="empires",
            heading="Empire Overview",
            kicker="Coalition Control",
            summary="帝国単位の勢力図を、人数、惑星、戦力、伸び幅までまとめて比較できます。",
        ),
        page_title=f"{settings.server_label} Empires",
        latest=latest_empires,
        board=empire_board,
        show_fleet=_has_fleet(empire_board),
        comparison_snapshots=empire_comparison_snapshots,
    )
    (out_dir / "empires.html").write_text(empires_html, encoding="utf-8")

    fleet_html = env.get_template("fleet.html").render(
        **context_base,
        **_page_context(
            current_page="fleet",
            heading="Fleet Pressure",
            kicker="Military Index",
            summary="戦力値そのものと増減速度に寄せて、艦隊規模の変化を追跡します。",
        ),
        page_title=f"{settings.server_label} Fleet",
        latest=latest_fleet,
        rows=fleet_rows,
        top_row=fleet_rows[0] if fleet_rows else None,
        fleet_available_windows=_fleet_window_availability(fleet_rows),
    )
    (out_dir / "fleet.html").write_text(fleet_html, encoding="utf-8")

    for window in DEFAULT_WINDOWS:
        latest_g, rows, comparison = get_growth_rows(state, window)
        growth_html = env.get_template("growth.html").render(
            **context_base,
            **_page_context(
                current_page="growth",
                heading=f"{window}h Growth Ranking",
                kicker="Velocity Board",
                summary=f"{window}時間でどれだけ伸びたかを、ポイント速度と順位変化で比較します。",
            ),
            page_title=f"{settings.server_label} Growth {window}h",
            latest=latest_g,
            rows=rows,
            show_fleet=_has_fleet(rows),
            show_fleet_delta=_has_fleet_delta(rows, window),
            show_level=any(
                row["comparisons"][window].get("delta_level") is not None
                for row in rows
                if row["comparisons"].get(window)
            ),
            window=window,
            comparison_snapshot=comparison,
        )
        (out_dir / f"growth-{window}h.html").write_text(growth_html, encoding="utf-8")

    latest_c, previous_c, changes = get_recent_changes(state)
    changes_html = env.get_template("changes.html").render(
        **context_base,
        **_page_context(
            current_page="changes",
            heading="Roster Changes",
            kicker="Delta Monitor",
            summary="前回取得からの新規ランクイン、圏外、帝国移籍を即座に確認できます。",
        ),
        page_title=f"{settings.server_label} Changes",
        latest=latest_c,
        previous=previous_c,
        changeset=changes,
    )
    (out_dir / "changes.html").write_text(changes_html, encoding="utf-8")

    players_dir = out_dir / "players"
    players_dir.mkdir(parents=True, exist_ok=True)
    player_names = sorted({row["player_name"] for snap in state.get("snapshots", []) for row in snap["rows"]}, key=str.casefold)
    for player_name in player_names:
        history = get_player_history(state, player_name)
        history_with_deltas = _history_with_previous_deltas(history)
        latest_point = history[-1] if history else None
        total_gain = history[-1]["points"] - history[0]["points"] if len(history) >= 2 else None
        best_rank = min((point["rank_position"] for point in history), default=None)
        max_points = max((point["points"] for point in history), default=None)
        max_fleet = max((point["fleet_score"] for point in history if point.get("fleet_score") is not None), default=None)
        fleet_history = [point["fleet_score"] for point in history if point.get("fleet_score") is not None]
        player_html = env.get_template("player.html").render(
            **context_base,
            **_page_context(
                current_page="player",
                heading=player_name,
                kicker="Player History",
                summary="ポイント、順位、戦力の時系列をプレイヤー単位で確認できます。",
            ),
            page_title=f"{player_name} | {settings.server_label}",
            player={
                "player_name": player_name,
                "player_key": player_key(player_name),
                "first_seen_at_utc": parse_iso_datetime(history[0]["captured_at_utc"]) if history else None,
                "last_seen_at_utc": parse_iso_datetime(history[-1]["captured_at_utc"]) if history else None,
            },
            show_title=_has_title(history),
            show_level=_has_level(history),
            show_fleet=_has_fleet(history),
            history=[
                {**point, "captured_at_utc": parse_iso_datetime(point["captured_at_utc"])}
                for point in history_with_deltas
            ],
            latest_point=latest_point,
            total_gain=total_gain,
            best_rank=best_rank,
            max_points=max_points,
            max_fleet=max_fleet,
            points_chart=sparkline_svg([point["points"] for point in history], title="Points history"),
            rank_chart=sparkline_svg([point["rank_position"] for point in history], invert=True, title="Rank history"),
            fleet_chart=sparkline_svg(fleet_history, title="Fleet history") if fleet_history else None,
        )
        (players_dir / f"{player_key(player_name)}.html").write_text(player_html, encoding="utf-8")

    empires_dir = out_dir / "empires"
    empires_dir.mkdir(parents=True, exist_ok=True)
    empire_names = sorted(
        {
            row["empire_name"]
            for snap in state.get("snapshots", [])
            for row in _aggregate_empire_snapshot(snap)
        },
        key=str.casefold,
    )
    for empire_name in empire_names:
        history = get_empire_history(state, empire_name)
        history_with_deltas = _history_with_previous_deltas(history)
        latest_point = history[-1] if history else None
        total_gain = history[-1]["points"] - history[0]["points"] if len(history) >= 2 else None
        best_rank = min((point["rank_position"] for point in history), default=None)
        max_points = max((point["points"] for point in history), default=None)
        max_fleet = max((point["fleet_score"] for point in history if point.get("fleet_score") is not None), default=None)
        max_members = max((point["member_count"] for point in history), default=None)
        max_planets = max((point["planets"] for point in history), default=None)
        fleet_history = [point["fleet_score"] for point in history if point.get("fleet_score") is not None]
        empire_html = env.get_template("empire.html").render(
            **context_base,
            **_page_context(
                current_page="empire",
                heading=empire_name,
                kicker="Empire History",
                summary="帝国単位のポイント、順位、人数、戦力の推移をまとめて追跡できます。",
            ),
            page_title=f"{empire_name} | {settings.server_label}",
            empire={
                "empire_name": empire_name,
                "empire_key": empire_key(empire_name),
                "first_seen_at_utc": parse_iso_datetime(history[0]["captured_at_utc"]) if history else None,
                "last_seen_at_utc": parse_iso_datetime(history[-1]["captured_at_utc"]) if history else None,
            },
            history=[
                {**point, "captured_at_utc": parse_iso_datetime(point["captured_at_utc"])}
                for point in history_with_deltas
            ],
            latest_point=latest_point,
            total_gain=total_gain,
            best_rank=best_rank,
            max_points=max_points,
            max_fleet=max_fleet,
            max_members=max_members,
            max_planets=max_planets,
            points_chart=sparkline_svg([point["points"] for point in history], title="Empire points history"),
            rank_chart=sparkline_svg([point["rank_position"] for point in history], invert=True, title="Empire rank history"),
            members_chart=sparkline_svg([point["member_count"] for point in history], title="Empire members history"),
            fleet_chart=sparkline_svg(fleet_history, title="Empire fleet history") if fleet_history else None,
        )
        (empires_dir / f"{empire_key(empire_name)}.html").write_text(empire_html, encoding="utf-8")

    export_data_json(out_dir, settings, state)
