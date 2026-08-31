"""Deterministic, explainable intelligence layer for camera registry imports.

The importer remains schema-first: required identity/stream data must be usable.
Optional metadata can degrade to warnings and be omitted rather than preventing
otherwise useful camera records from being registered.
"""
from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlparse

CSV_ALIASES = {
    "camera_id": "external_id",
    "id": "external_id",
    "camera_name": "name",
    "camera": "name",
    "latitude": "lat",
    "longitude": "lng",
    "lon": "lng",
    "owner": "owner_organization",
    "ownership": "owner_organization",
    "rtsp": "rtsp_url",
    "hls": "hls_url",
    "source": "source_system",
}

CORE_FIELDS = {"name"}
STREAM_FIELDS = {"stream_id", "rtsp_url", "hls_url", "external_id"}
OPTIONAL_FIELDS = {
    "location", "department", "owner_organization", "lat", "lng", "source_system",
    "storage_type", "retention_days", "analytics_capabilities", "installation_date",
    "ptz_capable", "night_vision_capable", "coord_source", "coord_confidence",
    "camera_type", "protocol", "vendor_id", "model_id",
}
REQUIRED_COLUMNS = {"name"}


def normalize_header(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def normalize_headers(headers: list[Any]) -> tuple[dict[str, str], list[dict[str, str]]]:
    mapping: dict[str, str] = {}
    notices: list[dict[str, str]] = []
    for raw in headers:
        normalized = normalize_header(raw)
        target = CSV_ALIASES.get(normalized, normalized)
        if not normalized:
            continue
        mapping[str(raw)] = target
        if target != normalized:
            notices.append({
                "code": "HEADER_ALIAS",
                "severity": "warning",
                "column": str(raw),
                "message": f"Column '{raw}' is recognized as '{target}'.",
            })
    return mapping, notices


def parse_bool(value: Any) -> bool:
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False
    raise ValueError("expected true/false")


def parse_coordinate(value: Any) -> float:
    text = str(value).strip().upper().replace("°", " ").replace("'", " ").replace('"', " ")
    direction = -1 if text.endswith(("S", "W")) else 1
    text = text.rstrip("NSEW ")
    parts = [part for part in text.replace(",", " ").split() if part]
    nums = [float(part) for part in parts]
    if not nums:
        raise ValueError("empty coordinate")
    result = nums[0] + (nums[1] / 60 if len(nums) > 1 else 0) + (nums[2] / 3600 if len(nums) > 2 else 0)
    return result * direction


def is_url(value: Any, schemes: set[str] | None = None) -> bool:
    try:
        parsed = urlparse(str(value).strip())
        allowed = schemes or {"rtsp", "rtsps", "http", "https"}
        return parsed.scheme.lower() in allowed and bool(parsed.netloc)
    except Exception:
        return False


def _issue(code: str, severity: str, field: str, message: str, row: int) -> dict[str, Any]:
    return {"code": code, "severity": severity, "field": field, "message": message, "row": row}


def analyze_row(row: dict[str, Any], row_number: int, header_mapping: dict[str, str]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    source_fields: dict[str, str] = {}
    for raw_key, value in row.items():
        target = header_mapping.get(str(raw_key), normalize_header(raw_key))
        normalized[target] = value
        source_fields[target] = str(raw_key)

    issues: list[dict[str, Any]] = []
    clean: dict[str, Any] = {}

    name = str(normalized.get("name") or "").strip()
    if not name:
        issues.append(_issue("MISSING_NAME", "error", "name", "Camera name is required.", row_number))
    else:
        clean["name"] = name

    stream_present = False
    for field in ("rtsp_url", "hls_url"):
        value = str(normalized.get(field) or "").strip()
        if value:
            stream_present = True
            schemes = {"rtsp", "rtsps"} if field == "rtsp_url" else {"http", "https"}
            if not is_url(value, schemes):
                issues.append(_issue("INVALID_STREAM_URL", "error", field, f"{field} contains an invalid {field.replace('_url', '').upper()} URL.", row_number))
            else:
                clean[field] = value

    raw_stream_id = normalized.get("stream_id")
    if raw_stream_id not in (None, ""):
        stream_present = True
        try:
            stream_id = int(str(raw_stream_id).strip())
            if stream_id < 0:
                raise ValueError
            clean["stream_id"] = stream_id
        except (TypeError, ValueError):
            issues.append(_issue("INVALID_STREAM_ID", "error", "stream_id", "Stream ID must be a non-negative integer.", row_number))

    external_id = str(normalized.get("external_id") or "").strip()
    if external_id:
        stream_present = True
        clean["external_id"] = external_id

    if not stream_present:
        issues.append(_issue("MISSING_STREAM_IDENTITY", "error", "stream_id/rtsp_url/hls_url/external_id", "At least one stream identity is required: stream_id, RTSP URL, HLS URL, or external ID.", row_number))

    # Optional fields are intentionally tolerant. Invalid values become explicit warnings
    # and are omitted so a usable camera record can still be imported.
    text_fields = ["location", "department", "owner_organization", "source_system", "storage_type", "camera_type", "protocol", "coord_source"]
    for field in text_fields:
        value = str(normalized.get(field) or "").strip()
        if value:
            clean[field] = value

    coordinate_values: dict[str, float] = {}
    for field in ("lat", "lng"):
        value = str(normalized.get(field) or "").strip()
        if not value:
            continue
        try:
            parsed = parse_coordinate(value)
            bounds = (-90, 90) if field == "lat" else (-180, 180)
            if not bounds[0] <= parsed <= bounds[1]:
                raise ValueError("out of bounds")
            coordinate_values[field] = parsed
        except (TypeError, ValueError):
            issues.append(_issue("INVALID_COORDINATE", "warning", field, f"{field.upper()} is not a valid coordinate and will be ignored.", row_number))
    if set(coordinate_values) == {"lat", "lng"}:
        clean.update(coordinate_values)
    elif coordinate_values:
        issues.append(_issue("INCOMPLETE_COORDINATES", "warning", "lat/lng", "Latitude and longitude must be supplied together; incomplete coordinates will be ignored.", row_number))

    for field in ("retention_days",):
        value = str(normalized.get(field) or "").strip()
        if not value:
            continue
        try:
            parsed = int(value)
            if parsed < 0:
                raise ValueError
            clean[field] = parsed
        except (TypeError, ValueError):
            issues.append(_issue("INVALID_INTEGER", "warning", field, f"{field} must be a non-negative integer and will be ignored.", row_number))

    value = str(normalized.get("installation_date") or "").strip()
    if value:
        try:
            clean["installation_date"] = date.fromisoformat(value).isoformat()
        except ValueError:
            issues.append(_issue("INVALID_DATE", "warning", "installation_date", "Installation date must be YYYY-MM-DD and will be ignored.", row_number))

    for field in ("ptz_capable", "night_vision_capable"):
        value = str(normalized.get(field) or "").strip()
        if not value:
            continue
        try:
            clean[field] = parse_bool(value)
        except ValueError:
            issues.append(_issue("INVALID_BOOLEAN", "warning", field, f"{field} must be true/false and will use the system default.", row_number))

    capabilities = str(normalized.get("analytics_capabilities") or "").strip()
    if capabilities:
        items = [item.strip() for item in capabilities.split("|") if item.strip()]
        if items:
            clean["analytics_capabilities"] = items
        else:
            issues.append(_issue("EMPTY_ANALYTICS", "warning", "analytics_capabilities", "Analytics capabilities were provided but no usable values were found.", row_number))

    status = "ready" if not [i for i in issues if i["severity"] == "error"] and not issues else "warning" if not [i for i in issues if i["severity"] == "error"] else "blocked"
    exact = status == "ready" and all(
        (target not in normalized or str(normalized.get(target) or "").strip() == "" or target in clean)
        for target in normalized
    ) and not any(i["code"] == "HEADER_ALIAS" for i in [])

    return {
        "row": row_number,
        "status": status,
        "exact": exact,
        "issues": issues,
        "normalized": clean,
        "source_fields": source_fields,
    }


def summarize(rows: list[dict[str, Any]], header_issues: list[dict[str, Any]], expected_fields: set[str] | None = None) -> dict[str, Any]:
    errors = sum(len([i for i in r["issues"] if i["severity"] == "error"]) for r in rows)
    warnings = len(header_issues) + sum(len([i for i in r["issues"] if i["severity"] == "warning"]) for r in rows)
    blocked_rows = sum(1 for r in rows if r["status"] == "blocked")
    ready_rows = sum(1 for r in rows if r["status"] == "ready")
    warning_rows = sum(1 for r in rows if r["status"] == "warning")
    exact_rows = sum(1 for r in rows if r["exact"])
    return {
        "status": "blocked" if errors else "warning" if warnings else "ready",
        "allow_upload": errors == 0 and bool(rows),
        "requires_warning_ack": warnings > 0,
        "total_rows": len(rows),
        "ready_rows": ready_rows,
        "warning_rows": warning_rows,
        "blocked_rows": blocked_rows,
        "exact_rows": exact_rows,
        "warning_count": warnings,
        "error_count": errors,
        "header_warnings": header_issues,
        "expected_fields": sorted(expected_fields or (CORE_FIELDS | STREAM_FIELDS | OPTIONAL_FIELDS)),
    }
