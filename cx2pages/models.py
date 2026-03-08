from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(slots=True)
class RankRow:
    rank_position: int
    title: str
    player_name: str
    level: int
    planets: int
    points: int
    avg_points: int
    empire_name: Optional[str] = None


@dataclass(slots=True)
class Snapshot:
    captured_at_utc: datetime
    rows: list[RankRow]
    source_url: str
    http_status: int | None = None
    content_sha256: str | None = None


@dataclass(slots=True)
class FetchRun:
    started_at_utc: datetime
    status: str
    row_count: int | None
    http_status: int | None
    message: str | None
    url: str | None
