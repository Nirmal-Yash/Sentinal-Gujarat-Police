"""Shared alert list filter helpers for production and test routes."""

from __future__ import annotations

from typing import Any


ALERT_TYPE_FILTER_TOKENS: dict[str, list[str]] = {
    "WATCHLIST_HIT": ["watchlist", "WATCHLIST_HIT"],
    "PLATE_SIGHTING": ["plate", "PLATE_SIGHTING", "anpr"],
    "PERSON_MATCH": ["person", "face", "PERSON_MATCH", "cross_camera"],
    "CROWD_ANOMALY": ["crowd", "CROWD_ANOMALY"],
    "RUNNING_CROWD": ["running", "RUNNING_CROWD"],
}


def normalize_alert_type_filter(alert_type: str | None) -> str | None:
    if not alert_type:
        return None
    cleaned = str(alert_type).strip()
    if not cleaned or cleaned.upper() == "ALL":
        return None
    return cleaned


def alert_type_filter_clause(alert_type: str | None) -> tuple[str | None, dict[str, Any]]:
    """Return a SQL boolean fragment and bind params for alert_type filtering."""
    normalized = normalize_alert_type_filter(alert_type)
    if not normalized:
        return None, {}

    tokens = ALERT_TYPE_FILTER_TOKENS.get(normalized.upper())
    if not tokens:
        return "a.alert_type ILIKE '%' || :alert_type || '%'", {"alert_type": normalized}

    parts: list[str] = []
    params: dict[str, Any] = {}
    for index, token in enumerate(tokens):
        key = f"alert_type_{index}"
        parts.append(f"a.alert_type ILIKE '%' || :{key} || '%'")
        params[key] = token
    return f"({' OR '.join(parts)})", params


def alert_sort_expression(test_mode: bool = False) -> str:
    if test_mode:
        return "COALESCE(a.event_at, a.created_at) DESC"
    return "a.created_at DESC"
