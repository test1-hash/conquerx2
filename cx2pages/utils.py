from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


JST = ZoneInfo("Asia/Tokyo")
UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return dt.astimezone(UTC)


def parse_iso_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def truncate_to_hour(dt: datetime) -> datetime:
    dt = to_utc(dt)
    return dt.replace(minute=0, second=0, microsecond=0)


def hours_between(newer: datetime, older: datetime) -> float:
    return (to_utc(newer) - to_utc(older)).total_seconds() / 3600.0


def jst_string(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        value = parse_iso_datetime(value)
    return value.astimezone(JST).strftime("%Y-%m-%d %H:%M JST")


def format_int(value: int | None) -> str:
    if value is None:
        return "-"
    return f"{value:,}"


def format_signed(value: int | None) -> str:
    if value is None:
        return "-"
    if value > 0:
        return f"+{value:,}"
    return f"{value:,}"


def format_signed_float(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "-"
    if value > 0:
        return f"+{value:,.{digits}f}"
    return f"{value:,.{digits}f}"


def cutoff_datetime(days: int) -> datetime:
    return utcnow() - timedelta(days=days)
