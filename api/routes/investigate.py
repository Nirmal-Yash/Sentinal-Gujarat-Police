from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from auth import require_authenticated, Principal
from database import get_db
from models import PlateInvestigateRequest
from plate_normalise import normalize_plate
from validators import require_valid_plate
from test_geo import test_geo_for_stream
import json, uuid

router = APIRouter(prefix="/investigate", tags=["investigate"], dependencies=[Depends(require_authenticated)])


def _parse_evidence(details: dict | None) -> dict:
    """Extract evidence payload from a details JSONB dict."""
    ev = (details or {}).get("evidence") or {}
    if ev.get("available"):
        return ev
    return {"available": False}


def _enrich_test_rows(rows: list[dict]) -> list[dict]:
    """Parse detection scores and evidence from test_detections.details."""
    out = []
    for r in rows:
        d = r.get("details") if isinstance(r.get("details"), dict) else {}
        try:
            if isinstance(r.get("details"), str):
                d = json.loads(r["details"])
        except Exception:
            pass
        r["evidence"] = _parse_evidence(d)
        r["anpr_consensus"] = d.get("anpr_consensus") or ""
        r["raw_ocr"] = d.get("raw_ocr") or ""
        r["detector_confidence"] = d.get("detector_confidence") or str(r.get("confidence") or "")
        # bbox from separate column or inside details
        raw_bbox = r.get("bbox")
        if isinstance(raw_bbox, str):
            try: raw_bbox = json.loads(raw_bbox)
            except Exception: raw_bbox = {}
        r["bbox"] = raw_bbox or {}
        stream_id = r.get("stream_id") or r.get("cam_id")
        if stream_id is not None:
            geo = test_geo_for_stream(int(stream_id))
            r["stream_id"] = int(stream_id)
            r["location"] = geo.get("location")
            r["lat"] = geo.get("lat")
            r["lng"] = geo.get("lng")
        out.append(r)
    return out


def _enrich_prod_rows(rows: list[dict]) -> list[dict]:
    """Attach evidence and metadata from production evidence join."""
    out = []
    for r in rows:
        ev_id = r.get("evidence_id")
        if ev_id:
            r["evidence"] = {
                "available": True, "evidence_id": str(ev_id),
                "frame_url": f"/api/evidence/{ev_id}/content",
                "thumbnail_url": f"/api/evidence/{ev_id}/thumbnail",
                "sha256": r.pop("evidence_sha256", None) or "",
            }
        else:
            r["evidence"] = {"available": False}
        d = r.get("sighting_metadata") if isinstance(r.get("sighting_metadata"), dict) else {}
        try:
            if isinstance(r.get("sighting_metadata"), str):
                d = json.loads(r["sighting_metadata"])
        except Exception:
            pass
        r.pop("sighting_metadata", None)
        r["anpr_consensus"] = d.get("anpr_consensus") or ""
        r["raw_ocr"] = d.get("raw_ocr") or ""
        r["detector_confidence"] = d.get("detector_confidence") or str(r.get("confidence") or "")
        raw_bbox = r.get("bbox")
        if isinstance(raw_bbox, str):
            try: raw_bbox = json.loads(raw_bbox)
            except Exception: raw_bbox = {}
        r["bbox"] = raw_bbox or {}
        out.append(r)
    return out


@router.post("/plate")
async def investigate_plate(
    body: PlateInvestigateRequest,
    x_test_session_id: str | None = Header(None, alias="X-Test-Session-Id"),
    db: AsyncSession = Depends(get_db),
):
    try:
        normalized = require_valid_plate(body.plate, required=True)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    if x_test_session_id:
        try:
            session_uuid = str(uuid.UUID(x_test_session_id))
        except ValueError as exc:
            raise HTTPException(400, "Invalid X-Test-Session-Id") from exc

        result = await db.execute(
            text("""
                SELECT td.id, td.session_id, td.stream_id, td.event_at AS timestamp, td.plate_text,
                       td.confidence, COALESCE(f.camera_label, td.camera_label) AS cam_name,
                       NULL AS location, NULL AS lat, NULL AS lng,
                       td.track_id, NULL AS global_vehicle_id, NULL AS journey_id,
                       td.bbox, td.details
                FROM test_detections td
                LEFT JOIN test_session_feeds f ON f.session_id=td.session_id AND f.stream_id=td.stream_id
                WHERE td.session_id=CAST(:session AS uuid)
                  AND regexp_replace(upper(COALESCE(td.plate_text,'')), '[^A-Z0-9]', '', 'g') = :plate
                ORDER BY td.event_at DESC LIMIT 50
            """),
            {"session": session_uuid, "plate": normalized},
        )
        rows = _enrich_test_rows([dict(r) for r in result.mappings().all()])
        wl = await db.execute(
            text("""
                SELECT id, name, description, alert_priority
                FROM test_watchlists
                WHERE session_id=CAST(:session AS uuid)
                  AND regexp_replace(upper(COALESCE(plate_number,'')), '[^A-Z0-9]', '', 'g') = :plate
                  AND is_active=TRUE
            """),
            {"session": session_uuid, "plate": normalized},
        )
        journeys = []
    else:
        result = await db.execute(
            text("""
                SELECT s.id, s.camera_id AS cam_id, s.source_timestamp AS timestamp,
                       s.normalized_plate AS plate_text, s.confidence, c.name AS cam_name,
                       c.location, c.lat, c.lng, s.track_id, s.global_vehicle_id, s.journey_id,
                       s.evidence_id,
                       e.sha256 AS evidence_sha256,
                       d.bbox,
                       d.metadata AS sighting_metadata
                FROM vehicle_sightings s
                JOIN cameras c ON c.id=s.camera_id
                LEFT JOIN evidence e ON e.id::text=s.evidence_id
                LEFT JOIN detections d ON d.id=s.detection_id
                WHERE s.normalized_plate = :plate OR s.plate_text = :plate
                ORDER BY s.source_timestamp DESC LIMIT 50
            """),
            {"plate": normalized},
        )
        rows = _enrich_prod_rows([dict(r) for r in result.mappings().all()])
        wl = await db.execute(
            text("""
                SELECT id, name, description, alert_priority
                FROM watchlist
                WHERE regexp_replace(upper(COALESCE(plate_number,'')), '[^A-Z0-9]', '', 'g') = :plate
                  AND is_active=TRUE
            """),
            {"plate": normalized},
        )
        journeys = [
            dict(r)
            for r in (
                await db.execute(
                    text("""
                        SELECT j.id, j.started_at, j.ended_at, j.sighting_count, j.journey_confidence, j.status
                        FROM vehicle_journeys j
                        JOIN vehicle_identities v ON v.id=j.vehicle_identity_id
                        WHERE v.normalized_plate=:plate
                        ORDER BY j.started_at DESC LIMIT 20
                    """),
                    {"plate": normalized},
                )
            ).mappings().all()
        ]

    return {
        "plate": normalized,
        "query": body.plate,
        "detections": rows,
        "watchlist_hits": [dict(r) for r in wl.mappings().all()],
        "journeys": journeys,
        "session_id": x_test_session_id,
    }
