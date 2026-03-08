from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

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


def _clean_text(value: str) -> str:
    return " ".join(value.split())


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
                empire_name=empires.get(user.empire_index) if user.empire_index > 0 else None,
            )
        )
    return rows


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


def fetch_ranking(server_label: str, url: str, user_agent: str, timeout_seconds: int) -> FetchResult:
    if "/export/" in url:
        return _fetch_export_ranking(url, user_agent, timeout_seconds)

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
