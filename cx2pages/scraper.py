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


def fetch_ranking(server_label: str, url: str, user_agent: str, timeout_seconds: int) -> FetchResult:
    response = requests.get(
        url,
        headers={"User-Agent": user_agent},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    response.encoding = response.encoding or "utf-8"
    rows = parse_rank_rows_from_text(response.text, server_label)
    content_sha256 = hashlib.sha256(response.text.encode("utf-8")).hexdigest()
    return FetchResult(
        url=response.url,
        http_status=response.status_code,
        raw_text=response.text,
        rows=rows,
        content_sha256=content_sha256,
    )
