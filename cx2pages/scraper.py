from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from .models import RankRow


_NUMERIC_TOKEN_RE = re.compile(r"^\d{1,3}(?:,\d{3})*$|^\d+$")


class ParseError(RuntimeError):
    pass


@dataclass(slots=True)
class FetchResult:
    url: str
    http_status: int
    raw_text: str
    rows: list[RankRow]
    content_sha256: str


@dataclass(slots=True)
class ExportUserRow:
    user_index: int
    empire_index: int
    score: int
    fleet_score: int
    player_name: str
    started_at_unix: int


@dataclass(slots=True)
class GamePlayerDetail:
    player_name: str
    fleet_score: int | None
    title: str | None
    level: int | None
    planets: int | None
    points: int | None
    empire_name: str | None


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _clean_cookie_value(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _parse_cookie_header(cookie_header: str | None) -> dict[str, str]:
    if not cookie_header:
        return {}
    cookies: dict[str, str] = {}
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = _clean_cookie_value(value)
        if not name or not value:
            continue
        cookies[name] = value
    return cookies


def _game_headers(user_agent: str) -> dict[str, str]:
    return {
        "Accept": "text/html, */*; q=0.01",
        "Referer": "https://game-jp-02.conquerx2.com/",
        "User-Agent": user_agent,
        "X-Requested-With": "XMLHttpRequest",
    }


def _normalize_lines(text: str) -> list[str]:
    soup = BeautifulSoup(text, "html.parser")
    visible = soup.get_text("\n")
    lines: list[str] = []
    for raw_line in visible.splitlines():
        line = _clean_text(raw_line)
        if line:
            lines.append(line)
    return lines


def _is_numeric_token(token: str) -> bool:
    return bool(_NUMERIC_TOKEN_RE.fullmatch(token))


def _parse_numeric(value: str | None) -> int | None:
    if value is None:
        return None
    cleaned = value.replace(",", "").strip()
    if not cleaned:
        return None
    if cleaned.isdigit():
        return int(cleaned)
    return None


def _parse_row_line(line: str) -> RankRow | None:
    tokens = line.split()
    if len(tokens) < 6:
        return None
    if not tokens[0].isdigit():
        return None

    rank_position = int(tokens[0].replace(",", ""))
    title = tokens[1]

    numeric_start = None
    for index in range(2, len(tokens) - 3):
        window = tokens[index : index + 4]
        if all(_is_numeric_token(token) for token in window):
            numeric_start = index
            break

    if numeric_start is None:
        return None

    player_name_tokens = tokens[2:numeric_start]
    if not player_name_tokens:
        return None

    level_token, planets_token, points_token, avg_points_token = tokens[
        numeric_start : numeric_start + 4
    ]
    empire_tokens = tokens[numeric_start + 4 :]

    return RankRow(
        rank_position=rank_position,
        title=title,
        player_name=" ".join(player_name_tokens),
        level=int(level_token.replace(",", "")),
        planets=int(planets_token.replace(",", "")),
        points=int(points_token.replace(",", "")),
        avg_points=int(avg_points_token.replace(",", "")),
        fleet_score=None,
        empire_name=" ".join(empire_tokens) if empire_tokens else None,
    )


def _table_near_server_label(soup: BeautifulSoup, server_label: str):
    header_line = f"{server_label} サーバー"
    for node in soup.find_all(string=lambda value: value and header_line in _clean_text(value)):
        current = node.parent
        while current is not None:
            table = current.find("table", class_="rank")
            if table is not None:
                return table
            current = current.parent
    return None


def _parse_rank_rows_from_html(text: str, server_label: str) -> list[RankRow]:
    soup = BeautifulSoup(text, "html.parser")
    table = _table_near_server_label(soup, server_label)
    if table is None:
        return []

    rows: list[RankRow] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 7:
            continue

        values = [_clean_text(cell.get_text(" ", strip=True)) for cell in cells]
        if not values or not values[0].isdigit():
            continue

        empire_name = values[7] if len(values) >= 8 and values[7] else None
        rows.append(
            RankRow(
                rank_position=int(values[0].replace(",", "")),
                title=values[1],
                player_name=values[2],
                level=int(values[3].replace(",", "")),
                planets=int(values[4].replace(",", "")),
                points=int(values[5].replace(",", "")),
                avg_points=int(values[6].replace(",", "")),
                fleet_score=None,
                empire_name=empire_name,
            )
        )
    return rows


def _parse_export_users(text: str) -> list[ExportUserRow]:
    rows: list[ExportUserRow] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("["):
            continue
        parts = [part.strip() for part in line.split(",", 5)]
        if len(parts) != 6:
            continue
        user_index, empire_index, score, fleet_score, player_name, started_at_unix = parts
        rows.append(
            ExportUserRow(
                user_index=int(user_index),
                empire_index=int(empire_index),
                score=int(score),
                fleet_score=int(fleet_score),
                player_name=player_name,
                started_at_unix=int(started_at_unix),
            )
        )
    if not rows:
        raise ParseError("no export user rows found")
    return rows


def _parse_export_planet_counts(text: str) -> dict[int, int]:
    counts: dict[int, int] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("["):
            continue
        parts = [part.strip() for part in line.split(",", 5)]
        if len(parts) != 6:
            continue
        user_index = int(parts[3])
        if user_index <= 0:
            continue
        counts[user_index] = counts.get(user_index, 0) + 1
    return counts


def _parse_export_empires(text: str) -> dict[int, str]:
    empires: dict[int, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("["):
            continue
        parts = [part.strip() for part in line.split(",", 2)]
        if len(parts) != 3:
            continue
        empire_index, _score, name = parts
        empires[int(empire_index)] = name
    return empires


def parse_rank_rows_from_export(users_text: str, planets_text: str, empires_text: str) -> list[RankRow]:
    users = _parse_export_users(users_text)
    planet_counts = _parse_export_planet_counts(planets_text)
    empires = _parse_export_empires(empires_text)

    ordered = sorted(users, key=lambda row: (-row.score, row.user_index))
    rows: list[RankRow] = []
    for rank_position, user in enumerate(ordered, start=1):
        planets = planet_counts.get(user.user_index, 0)
        rows.append(
            RankRow(
                rank_position=rank_position,
                title=None,
                player_name=user.player_name,
                level=None,
                planets=planets,
                points=user.score,
                avg_points=user.score // planets if planets > 0 else user.score,
                fleet_score=user.fleet_score,
                empire_name=empires.get(user.empire_index) if user.empire_index > 0 else None,
            )
        )
    return rows


def parse_rank_rows_from_game_html(text: str) -> list[RankRow]:
    soup = BeautifulSoup(text, "html.parser")
    table = soup.find("table", class_="list")
    if table is None:
        raise ParseError("game rank table not found")

    rows: list[RankRow] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 8:
            continue

        rank_position = _parse_numeric(_clean_text(cells[0].get_text(" ", strip=True)))
        if rank_position is None:
            continue

        title_icon = cells[1].find(class_=re.compile(r"usertitleicon20x"))
        title = None
        if title_icon is not None and title_icon.get("title"):
            title = _clean_text(unescape(str(title_icon.get("title"))).split("<br>", 1)[0])

        player_name = _clean_text(cells[2].get_text(" ", strip=True))
        level = _parse_numeric(_clean_text(cells[3].get_text(" ", strip=True)))
        planets = _parse_numeric(_clean_text(cells[4].get_text(" ", strip=True)))
        points = _parse_numeric(_clean_text(cells[5].get_text(" ", strip=True)))
        avg_points = _parse_numeric(_clean_text(cells[6].get_text(" ", strip=True)))
        empire_name = _clean_text(cells[7].get_text(" ", strip=True)) or None

        if not player_name or level is None or planets is None or points is None or avg_points is None:
            continue

        rows.append(
            RankRow(
                rank_position=rank_position,
                title=title,
                player_name=player_name,
                level=level,
                planets=planets,
                points=points,
                avg_points=avg_points,
                fleet_score=None,
                empire_name=empire_name,
            )
        )

    if not rows:
        raise ParseError("no rows found in game rank table")
    return rows


def parse_game_player_detail(text: str) -> GamePlayerDetail:
    payload = json.loads(text)
    player = payload.get("player")
    if not isinstance(player, dict):
        raise ParseError("game player detail missing player payload")

    usertitle = player.get("usertitle") or {}
    title = usertitle.get("titlename") if isinstance(usertitle, dict) else None
    player_name = player.get("usernick")
    if not player_name:
        raise ParseError("game player detail missing usernick")

    return GamePlayerDetail(
        player_name=player_name,
        fleet_score=_parse_numeric(str(player.get("score_ship", "") or "")),
        title=title,
        level=_parse_numeric(str(player.get("userlevel", "") or "")),
        planets=_parse_numeric(str(player.get("owned_planet_count", "") or "")),
        points=_parse_numeric(str(player.get("score", "") or "")),
        empire_name=player.get("empirename"),
    )


def _parse_rank_rows_from_text_lines(text: str, server_label: str) -> list[RankRow]:
    lines = _normalize_lines(text)
    header_line = f"{server_label} サーバー"

    try:
        start_index = lines.index(header_line)
    except ValueError as exc:
        raise ParseError(f"server header not found: {header_line}") from exc

    rows: list[RankRow] = []
    for line in lines[start_index + 1 :]:
        if line.endswith("サーバー"):
            break
        if line.startswith("ホームページでは"):
            break
        if line.startswith("個人情報処理方針"):
            break
        if line.startswith("ランク プレーヤー"):
            continue
        parsed = _parse_row_line(line)
        if parsed is not None:
            rows.append(parsed)
    return rows


def parse_rank_rows_from_text(text: str, server_label: str) -> list[RankRow]:
    rows = _parse_rank_rows_from_html(text, server_label)
    if not rows:
        rows = _parse_rank_rows_from_text_lines(text, server_label)

    if not rows:
        raise ParseError(f"no ranking rows found for server {server_label}")
    return rows


def _fetch_text_response(session: requests.Session, url: str, user_agent: str, timeout_seconds: int) -> requests.Response:
    response = session.get(
        url,
        headers={"User-Agent": user_agent},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    response.encoding = "utf-8"
    return response


def _fetch_export_ranking(url: str, user_agent: str, timeout_seconds: int) -> FetchResult:
    base_url = url.rstrip("/")
    with requests.Session() as session:
        users_response = _fetch_text_response(session, f"{base_url}/users.txt", user_agent, timeout_seconds)
        planets_response = _fetch_text_response(session, f"{base_url}/planets.txt", user_agent, timeout_seconds)
        empires_response = _fetch_text_response(session, f"{base_url}/empires.txt", user_agent, timeout_seconds)

    rows = parse_rank_rows_from_export(users_response.text, planets_response.text, empires_response.text)
    raw_text = "\n".join(
        [
            "[users.txt]",
            users_response.text,
            "[planets.txt]",
            planets_response.text,
            "[empires.txt]",
            empires_response.text,
        ]
    )
    content_sha256 = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    return FetchResult(
        url=base_url,
        http_status=users_response.status_code,
        raw_text=raw_text,
        rows=rows,
        content_sha256=content_sha256,
    )


def _with_query_params(url: str, **updates: int | str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({key: str(value) for key, value in updates.items()})
    return urlunparse(parsed._replace(query=urlencode(query)))


def _fetch_game_rank_page(
    session: requests.Session,
    url: str,
    user_agent: str,
    timeout_seconds: int,
) -> requests.Response:
    response = session.get(
        url,
        headers=_game_headers(user_agent),
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    response.encoding = "utf-8"
    return response


def _fetch_game_player_detail(
    session: requests.Session,
    player_name: str,
    user_agent: str,
    timeout_seconds: int,
) -> tuple[GamePlayerDetail, str]:
    headers = {
        **_game_headers(user_agent),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/json",
        "Origin": "https://game-jp-02.conquerx2.com",
    }
    body = (
        f"usernick={player_name}&module=game&module_type=controller&act=loadTargetPlayerData"
    ).encode("utf-8")
    response = session.post(
        "https://game-jp-02.conquerx2.com/",
        headers=headers,
        data=body,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    response.encoding = "utf-8"
    return parse_game_player_detail(response.text), response.text


def _merge_game_rows_with_details(
    rows: list[RankRow],
    details_by_name: dict[str, GamePlayerDetail],
) -> list[RankRow]:
    merged: list[RankRow] = []
    for row in rows:
        detail = details_by_name.get(row.player_name)
        merged.append(
            RankRow(
                rank_position=row.rank_position,
                title=(detail.title if detail and detail.title else row.title),
                player_name=row.player_name,
                level=detail.level if detail and detail.level is not None else row.level,
                planets=detail.planets if detail and detail.planets is not None else row.planets,
                points=detail.points if detail and detail.points is not None else row.points,
                avg_points=(
                    (detail.points // detail.planets)
                    if detail and detail.points is not None and detail.planets not in (None, 0)
                    else row.avg_points
                ),
                fleet_score=detail.fleet_score if detail else None,
                empire_name=detail.empire_name if detail and detail.empire_name is not None else row.empire_name,
            )
        )
    return merged


def _fetch_game_ranking(
    url: str,
    user_agent: str,
    timeout_seconds: int,
    cookie_header: str,
) -> FetchResult:
    cookies = _parse_cookie_header(cookie_header)
    if "PHPSESSID" not in cookies or "CONQUERX2" not in cookies:
        raise ParseError("CX2_GAME_COOKIE must include PHPSESSID and CONQUERX2")

    base_url = _with_query_params(url, ranktype=0, offset=0)
    page_rows: list[RankRow] = []
    raw_parts: list[str] = []
    seen_pages: set[tuple[int, str]] = set()

    with requests.Session() as session:
        session.cookies.update(cookies)

        offset = 0
        while True:
            page_url = _with_query_params(base_url, offset=offset)
            response = _fetch_game_rank_page(session, page_url, user_agent, timeout_seconds)
            rows = parse_rank_rows_from_game_html(response.text)
            page_key = (rows[0].rank_position, rows[0].player_name)
            if page_key in seen_pages:
                break
            seen_pages.add(page_key)
            page_rows.extend(rows)
            raw_parts.append(f"[rank offset={offset}]")
            raw_parts.append(response.text)
            offset += len(rows)
            if len(rows) < 10:
                break

        unique_rows: list[RankRow] = []
        seen_players: set[str] = set()
        for row in page_rows:
            if row.player_name in seen_players:
                continue
            seen_players.add(row.player_name)
            unique_rows.append(row)

        details_by_name: dict[str, GamePlayerDetail] = {}
        for row in unique_rows:
            detail, raw_text = _fetch_game_player_detail(session, row.player_name, user_agent, timeout_seconds)
            details_by_name[row.player_name] = detail
            raw_parts.append(f"[detail {row.player_name}]")
            raw_parts.append(raw_text)

    merged_rows = _merge_game_rows_with_details(unique_rows, details_by_name)
    raw_text = "\n".join(raw_parts)
    content_sha256 = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    return FetchResult(
        url=base_url,
        http_status=200,
        raw_text=raw_text,
        rows=merged_rows,
        content_sha256=content_sha256,
    )


def fetch_ranking(
    server_label: str,
    url: str,
    user_agent: str,
    timeout_seconds: int,
    cookie_header: str | None = None,
) -> FetchResult:
    if "/export/" in url:
        return _fetch_export_ranking(url, user_agent, timeout_seconds)
    if "act=dispGameRank" in url:
        if not cookie_header:
            raise ParseError("game rank source requires CX2_GAME_COOKIE")
        return _fetch_game_ranking(url, user_agent, timeout_seconds, cookie_header)

    response = requests.get(
        url,
        headers={"User-Agent": user_agent},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    response.encoding = "utf-8"
    rows = parse_rank_rows_from_text(response.text, server_label)
    content_sha256 = hashlib.sha256(response.text.encode("utf-8")).hexdigest()
    return FetchResult(
        url=response.url,
        http_status=response.status_code,
        raw_text=response.text,
        rows=rows,
        content_sha256=content_sha256,
    )
