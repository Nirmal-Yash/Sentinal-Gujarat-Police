from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from sqlalchemy import select, text, or_, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from models import Camera, CameraOut, CameraCreate, CameraPage, CameraSearchResult
from auth import require_authenticated, require_permission, require_role, Principal
from database import get_db
import uuid, os, base64, csv, io, json
from openpyxl import load_workbook
from pydantic import ValidationError
import redis as redis_lib

router = APIRouter(prefix="/cameras", tags=["cameras"], dependencies=[Depends(require_authenticated)])
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


def _validate_coordinates(body: CameraCreate):
    if (body.lat is None) != (body.lng is None):
        raise HTTPException(422, "latitude and longitude must be supplied together")


def _audit_state(camera: Camera | None):
    if camera is None:
        return None
    value = CameraOut.model_validate(camera).model_dump(mode="json")
    for key in ("rtsp_url", "hls_url", "whep_url", "stream_url"):
        value.pop(key, None)
    return value


async def _validate_vendor_model(body: CameraCreate, db: AsyncSession):
    """Prevent a camera from referencing a model owned by another vendor."""
    if body.model_id and not body.vendor_id:
        raise HTTPException(422, "vendor_id is required when model_id is supplied")
    if body.vendor_id and not await db.scalar(text("SELECT 1 FROM vendors WHERE id=CAST(:id AS uuid)"), {"id": str(body.vendor_id)}):
        raise HTTPException(422, "vendor_id is not registered")
    if body.model_id:
        owner = await db.scalar(text("SELECT vendor_id FROM camera_models WHERE id=CAST(:id AS uuid)"), {"id": str(body.model_id)})
        if owner is None or str(owner) != str(body.vendor_id):
            raise HTTPException(422, "model_id does not belong to vendor_id")


CSV_ALIASES = {
    "camera_id": "external_id", "id": "external_id", "camera_name": "name", "camera": "name",
    "latitude": "lat", "longitude": "lng", "lon": "lng", "owner": "owner_organization",
    "ownership": "owner_organization", "rtsp": "rtsp_url", "hls": "hls_url", "source": "source_system", "processing_category": "processing_fps_category", "fps_category": "processing_fps_category",
}

def _coordinate(value: str) -> float:
    """Accept decimal coordinates and common DMS notation from field surveys."""
    raw = value.strip().upper().replace("°", " ").replace("'", " ").replace('"', " ")
    direction = -1 if raw.endswith(("S", "W")) else 1
    raw = raw.rstrip("NSEW ")
    parts = [part for part in raw.replace(",", ".").split() if part]
    numbers = [float(part) for part in parts]
    if not numbers: raise ValueError("empty coordinate")
    result = numbers[0] + (numbers[1] / 60 if len(numbers) > 1 else 0) + (numbers[2] / 3600 if len(numbers) > 2 else 0)
    return result * direction

def _csv_payload(row: dict) -> tuple[dict, dict]:
    """Normalize real-world headers; preserve an explicit mapping for audit."""
    payload, column_map = {}, {}
    for key, value in row.items():
        normalized = (key or "").strip().lower().replace(" ", "_").replace("-", "_")
        target = CSV_ALIASES.get(normalized, normalized)
        if value is not None and value.strip() != "":
            payload[target] = value.strip(); column_map[key] = target
    for key in ("stream_id", "retention_days"):
        if key in payload:
            payload[key] = int(payload[key])
    for key in ("lat", "lng"):
        if key in payload:
            payload[key] = _coordinate(payload[key])
    if "analytics_capabilities" in payload:
        payload["analytics_capabilities"] = [item.strip() for item in payload["analytics_capabilities"].split("|") if item.strip()]
    return payload, column_map


@router.get("/search", response_model=list[CameraSearchResult])
async def search_cameras(
    q: str = Query(..., min_length=1, max_length=100),
    department: str | None = None,
    location: str | None = None,
    status: str | None = None,
    health_status: str | None = None,
    zone: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Database-scale trigram ranked camera search for 80,000+ camera catalogs."""
    clean_q = q.strip()
    like_term = f"%{clean_q}%"
    prefix_term = f"{clean_q}%"

    num_match = 0
    has_num = False
    if clean_q.isdigit():
        num_match = int(clean_q)
        has_num = True
    elif clean_q.lower().startswith("cam") and clean_q[3:].isdigit():
        num_match = int(clean_q[3:])
        has_num = True

    params: dict[str, Any] = {
        "clean_q": clean_q,
        "like_term": like_term,
        "prefix_term": prefix_term,
        "num_match": num_match,
        "has_num": has_num,
        "limit": limit,
    }

    extra_filters = []
    if department:
        extra_filters.append("c.department ILIKE :department")
        params["department"] = department
    if location:
        extra_filters.append("c.location ILIKE :location")
        params["location"] = f"%{location}%"
    if status:
        extra_filters.append("c.status ILIKE :status")
        params["status"] = status
    if health_status:
        extra_filters.append("c.health_status ILIKE :health_status")
        params["health_status"] = health_status
    if zone:
        extra_filters.append("c.zone ILIKE :zone")
        params["zone"] = zone

    filter_sql = (" AND " + " AND ".join(extra_filters)) if extra_filters else ""

    sql = f"""
        WITH ranked AS (
            SELECT 
                c.*,
                CASE 
                    WHEN :has_num = TRUE AND c.stream_id = :num_match THEN 100.0
                    WHEN lower(COALESCE(c.external_id,'')) = lower(:clean_q) THEN 100.0
                    WHEN lower(c.name) = lower(:clean_q) OR lower(c.location) = lower(:clean_q) THEN 95.0
                    WHEN lower(c.name) LIKE lower(:prefix_term) OR lower(c.location) LIKE lower(:prefix_term) THEN 80.0
                    WHEN lower(COALESCE(c.external_id,'')) LIKE lower(:prefix_term) THEN 75.0
                    WHEN lower(COALESCE(c.police_station,'')) LIKE lower(:prefix_term) THEN 70.0
                    ELSE 50.0 + (GREATEST(
                        similarity(c.name, :clean_q), 
                        similarity(c.location, :clean_q), 
                        similarity(COALESCE(c.police_station,''), :clean_q),
                        similarity(COALESCE(c.zone,''), :clean_q)
                    ) * 40.0)
                END as rank_score,
                CASE 
                    WHEN :has_num = TRUE AND c.stream_id = :num_match THEN 'exact_id'
                    WHEN lower(COALESCE(c.external_id,'')) = lower(:clean_q) THEN 'exact_id'
                    WHEN lower(c.name) = lower(:clean_q) OR lower(c.location) = lower(:clean_q) THEN 'exact_name'
                    WHEN lower(c.name) LIKE lower(:prefix_term) OR lower(c.location) LIKE lower(:prefix_term) THEN 'prefix'
                    ELSE 'trigram'
                END as match_type
            FROM cameras c
            WHERE c.status <> 'deleted'
              AND (
                  ( :has_num = TRUE AND c.stream_id = :num_match )
                  OR c.name ILIKE :like_term
                  OR c.location ILIKE :like_term
                  OR c.external_id ILIKE :like_term
                  OR c.department ILIKE :like_term
                  OR c.zone ILIKE :like_term
                  OR c.police_station ILIKE :like_term
                  OR similarity(c.name, :clean_q) > 0.18
                  OR similarity(c.location, :clean_q) > 0.18
              )
              {filter_sql}
        )
        SELECT * FROM ranked ORDER BY rank_score DESC, stream_id ASC LIMIT :limit
    """
    result = await db.execute(text(sql), params)
    rows = result.mappings().all()
    out = []
    for row in rows:
        cam_dict = dict(row)
        rank_score = float(cam_dict.pop("rank_score", 0.0))
        match_type = str(cam_dict.pop("match_type", "trigram"))
        cam = CameraOut.model_validate(cam_dict)
        out.append(CameraSearchResult(camera=cam, rank_score=rank_score, match_type=match_type))
    return out


@router.get("/paged", response_model=CameraPage)
async def paged_cameras(
    page: int = Query(1, ge=1),
    limit: int = Query(9, ge=1, le=100),
    q: str | None = Query(None, min_length=1, max_length=100),
    department: str | None = None,
    location: str | None = None,
    status: str | None = None,
    health_status: str | None = None,
    zone: str | None = None,
    sort: str = Query("grid", pattern="^(grid|priority|status|name|stream_id)$"),
    group_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Server-side paginated camera query with operational summary for 80,000+ camera catalogs."""
    offset = (page - 1) * limit
    where_clauses = ["c.status <> 'deleted'"]
    params = {"limit": limit, "offset": offset}

    if q:
        clean = q.strip()
        num_q = int(clean) if clean.isdigit() else (int(clean[3:]) if clean.lower().startswith("cam") and clean[3:].isdigit() else None)
        params["q_num"] = num_q
        params["q_like"] = f"%{clean}%"
        params["q_clean"] = clean
        where_clauses.append("""(
            (:q_num IS NOT NULL AND c.stream_id = :q_num)
            OR c.name ILIKE :q_like
            OR c.location ILIKE :q_like
            OR c.external_id ILIKE :q_like
            OR c.department ILIKE :q_like
            OR c.police_station ILIKE :q_like
            OR similarity(c.name, :q_clean) > 0.2
        )""")

    if department:
        where_clauses.append("c.department ILIKE :department")
        params["department"] = department
    if location:
        where_clauses.append("c.location ILIKE :location")
        params["location"] = f"%{location}%"
    if status:
        where_clauses.append("c.status ILIKE :status")
        params["status"] = status
    if health_status:
        where_clauses.append("c.health_status ILIKE :health_status")
        params["health_status"] = health_status
    if zone:
        where_clauses.append("c.zone ILIKE :zone")
        params["zone"] = zone
    if group_id:
        where_clauses.append("c.group_id = CAST(:group_id AS uuid)")
        params["group_id"] = str(group_id)

    where_sql = " AND ".join(where_clauses)

    order_sql = "c.stream_id ASC"
    if sort == "priority":
        order_sql = "CASE WHEN c.health_status IN ('offline', 'error') THEN 1 WHEN c.health_status IN ('degraded', 'warning') THEN 2 ELSE 3 END, c.stream_id ASC"
    elif sort == "status":
        order_sql = "c.health_status ASC, c.status ASC, c.stream_id ASC"
    elif sort == "name":
        order_sql = "c.name ASC"

    # Count and summary
    count_sql = f"""
        SELECT 
            COUNT(*) as total_count,
            COUNT(*) FILTER (WHERE c.health_status IN ('healthy', 'online') OR c.status = 'active') as online_count,
            COUNT(*) FILTER (WHERE c.health_status IN ('degraded', 'warning') OR c.status = 'reconnecting') as degraded_count,
            COUNT(*) FILTER (WHERE c.health_status IN ('offline', 'error') OR c.status = 'offline') as offline_count
        FROM cameras c
        WHERE {where_sql}
    """
    count_res = (await db.execute(text(count_sql), params)).mappings().first()
    total_count = int(count_res["total_count"] or 0)
    online_count = int(count_res["online_count"] or 0)
    degraded_count = int(count_res["degraded_count"] or 0)
    offline_count = int(count_res["offline_count"] or 0)

    # Active alerts count
    alerts_sql = f"""
        SELECT COUNT(*) as alert_count
        FROM alerts a
        JOIN cameras c ON c.id = a.cam_id
        WHERE {where_sql} AND a.status = 'NEW' AND a.acknowledged = FALSE
    """
    alerts_count = int(await db.scalar(text(alerts_sql), params) or 0)

    # Items query
    items_sql = f"""
        SELECT c.*
        FROM cameras c
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT :limit OFFSET :offset
    """
    rows = (await db.execute(text(items_sql), params)).mappings().all()
    items = [CameraOut.model_validate(dict(r)) for r in rows]
    total_pages = max(1, (total_count + limit - 1) // limit) if total_count else 1

    return CameraPage(
        items=items,
        total_count=total_count,
        page=page,
        page_size=limit,
        total_pages=total_pages,
        next_cursor=str(page + 1) if page < total_pages else None,
        prev_cursor=str(page - 1) if page > 1 else None,
        summary={
            "total": total_count,
            "online": online_count,
            "degraded": degraded_count,
            "offline": offline_count,
            "active_alerts": alerts_count,
        },
    )


@router.get("/map/clusters")
async def get_map_clusters(
    min_lng: float = Query(-180.0, ge=-180, le=180),
    min_lat: float = Query(-90.0, ge=-90, le=90),
    max_lng: float = Query(180.0, ge=-180, le=180),
    max_lat: float = Query(90.0, ge=-90, le=90),
    zoom: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Spatial clustering for GIS map to handle 80,000 cameras without DOM overload."""
    bbox_where = "lat BETWEEN :min_lat AND :max_lat AND lng BETWEEN :min_lng AND :max_lng AND status <> 'deleted'"
    params = {"min_lat": min_lat, "max_lat": max_lat, "min_lng": min_lng, "max_lng": max_lng}

    if zoom <= 11:
        # Cluster dynamically by district / geographic grid cell
        cluster_sql = f"""
            SELECT 
                COALESCE(district, 'Gujarat') as cluster_name,
                AVG(lat) as lat,
                AVG(lng) as lng,
                COUNT(*) as count,
                COUNT(*) FILTER (WHERE health_status IN ('healthy', 'online') OR status = 'active') as online_count,
                COUNT(*) FILTER (WHERE health_status IN ('degraded', 'warning') OR status = 'reconnecting') as degraded_count,
                COUNT(*) FILTER (WHERE health_status IN ('offline', 'error') OR status = 'offline') as offline_count
            FROM cameras
            WHERE {bbox_where} AND lat IS NOT NULL AND lng IS NOT NULL
            GROUP BY COALESCE(district, 'Gujarat')
        """
        rows = (await db.execute(text(cluster_sql), params)).mappings().all()
        return {
            "type": "clusters",
            "zoom": zoom,
            "clusters": [
                {
                    "name": r["cluster_name"],
                    "lat": float(r["lat"]),
                    "lng": float(r["lng"]),
                    "count": int(r["count"]),
                    "online": int(r["online_count"]),
                    "degraded": int(r["degraded_count"]),
                    "offline": int(r["offline_count"]),
                }
                for r in rows
            ],
        }
    else:
        # High zoom: return visible camera pins directly (capped at 250)
        pins_sql = f"""
            SELECT id, stream_id, name, location, lat, lng, health_status, status, zone, police_station
            FROM cameras
            WHERE {bbox_where} AND lat IS NOT NULL AND lng IS NOT NULL
            ORDER BY stream_id ASC
            LIMIT 250
        """
        rows = (await db.execute(text(pins_sql), params)).mappings().all()
        return {
            "type": "cameras",
            "zoom": zoom,
            "cameras": [
                {
                    "id": str(r["id"]),
                    "stream_id": r["stream_id"],
                    "camera_id": f"cam{int(r['stream_id']):02d}" if r["stream_id"] else "cam00",
                    "name": r["name"],
                    "location": r["location"],
                    "lat": float(r["lat"]),
                    "lng": float(r["lng"]),
                    "health_status": r["health_status"],
                    "status": r["status"],
                    "zone": r["zone"],
                    "police_station": r["police_station"],
                }
                for r in rows
            ],
        }


@router.get("", response_model=list[CameraOut])
@router.get("/", response_model=list[CameraOut])
async def list_cameras(
    q: str | None = Query(None, min_length=1, max_length=100),
    department: str | None = None, status: str | None = None,
    health_status: str | None = None, camera_type: str | None = None,
    zone: str | None = None,
    vendor_id: uuid.UUID | None = None, model_id: uuid.UUID | None = None,
    limit: int = Query(250, ge=1, le=500), offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Registry read model. It is the only camera metadata source for UI/GIS."""
    stmt = select(Camera).where(Camera.status != 'deleted')
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(Camera.name.ilike(term), Camera.location.ilike(term),
                              Camera.department.ilike(term), Camera.owner_organization.ilike(term),
                              Camera.status.ilike(term), Camera.health_status.ilike(term),
                              Camera.camera_type.ilike(term), Camera.zone.ilike(term),
                              Camera.stream_id.cast(String).ilike(term)))
    for column, value in ((Camera.department, department), (Camera.status, status),
                          (Camera.health_status, health_status), (Camera.camera_type, camera_type),
                          (Camera.zone, zone)):
        if value:
            stmt = stmt.where(column.ilike(value))
    if vendor_id: stmt = stmt.where(Camera.vendor_id == vendor_id)
    if model_id: stmt = stmt.where(Camera.model_id == model_id)
    result = await db.execute(stmt.order_by(Camera.stream_id).limit(limit).offset(offset))
    return result.scalars().all()


@router.post("", response_model=CameraOut, status_code=201)
@router.post("/", response_model=CameraOut, status_code=201)
@router.post("/onboard", response_model=CameraOut, status_code=201)
async def onboard_camera(body: CameraCreate, principal: Principal = Depends(require_permission("camera:write")), db: AsyncSession = Depends(get_db)):
    """Manual/API Model-1 onboarding; catalogue sync remains the same owner for external sources."""
    _validate_coordinates(body)
    await _validate_vendor_model(body, db)
    if body.stream_id is not None and await db.scalar(select(Camera.id).where(Camera.stream_id == body.stream_id)):
        raise HTTPException(409, "stream_id is already registered")
    if body.rtsp_url and await db.scalar(select(Camera.id).where(Camera.rtsp_url == body.rtsp_url)):
        raise HTTPException(409, "RTSP source is already registered")
    camera = Camera(**body.model_dump())
    db.add(camera)
    await db.flush()
    if body.lat is not None:
        await db.execute(text("UPDATE cameras SET geom=ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), updated_at=NOW() WHERE id=:id"),
                         {"id": str(camera.id), "lat": body.lat, "lng": body.lng})
    await db.refresh(camera)
    await db.execute(text("""INSERT INTO camera_audit_log(camera_id, actor, action, before_value, after_value, correlation_id)
        VALUES (CAST(:id AS uuid), :actor, 'create', NULL, CAST(:value AS jsonb), CAST(:correlation AS uuid))"""),
        {"id": str(camera.id), "actor": principal.username, "value": json.dumps(_audit_state(camera)), "correlation": str(uuid.uuid4())})
    await db.commit()
    await db.refresh(camera)
    return camera


@router.post("/imports/csv", status_code=201)
async def import_cameras_csv(
    file: UploadFile = File(...), principal: Principal = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Controlled Model-1 bulk onboarding; invalid rows are reported, never dropped."""
    suffix = os.path.splitext(file.filename or "")[1].lower()
    if suffix not in {".csv", ".xlsx"}:
        raise HTTPException(415, "Upload a CSV or XLSX registry file")
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, "Registry import exceeds the 5 MiB PoC limit")
    try:
        if suffix == ".csv":
            rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        else:
            sheet = load_workbook(io.BytesIO(raw), read_only=True, data_only=True).active
            values = sheet.iter_rows(values_only=True)
            headers = next(values, None)
            if not headers:
                rows = []
            else:
                header_names = [str(value).strip() if value is not None else "" for value in headers]
                rows = [{header_names[index]: value for index, value in enumerate(row) if index < len(header_names) and header_names[index]}
                        for row in values if any(value is not None and str(value).strip() for value in row)]
    except (UnicodeDecodeError, ValueError, OSError) as exc:
        raise HTTPException(422, "Registry file could not be parsed; CSV must be UTF-8 and XLSX must have a header row") from exc
    if not rows:
        raise HTTPException(422, "CSV contains no data rows")

    import_id = uuid.uuid4()
    await db.execute(text("""INSERT INTO camera_imports(id, filename, actor, total_rows)
        VALUES (CAST(:id AS uuid), :filename, :actor, :total)"""),
        {"id": str(import_id), "filename": file.filename or "camera-import.csv", "actor": principal.username, "total": len(rows)})
    accepted, errors, import_column_map = 0, [], {}
    for row_number, row in enumerate(rows, start=2):
        try:
            payload, mapping = _csv_payload(row)
            import_column_map.update(mapping)
            source_supplied = "source_system" in payload
            payload.setdefault("source_system", "csv")
            if "lat" in payload and "lng" in payload:
                payload.setdefault("coord_source", "csv")
                payload.setdefault("coord_confidence", 0.7)
            body = CameraCreate.model_validate(payload)
            _validate_coordinates(body)
            await _validate_vendor_model(body, db)
            # Government files are often incomplete.  Prefer a stable source
            # key, then an RTSP URL; a row with neither is still imported as a
            # clearly auditable new asset rather than silently discarded.
            existing = None
            if body.stream_id is not None:
                existing = await db.scalar(select(Camera).where(Camera.stream_id == body.stream_id))
            elif body.external_id:
                existing = await db.scalar(select(Camera).where(Camera.source_system == body.source_system, Camera.external_id == body.external_id))
            elif body.rtsp_url:
                existing = await db.scalar(select(Camera).where(Camera.rtsp_url == body.rtsp_url))
            # Sparse government files must not overwrite registry fields with
            # Pydantic defaults such as an empty location.
            values = body.model_dump(exclude_none=True, exclude_unset=True)
            if existing and not source_supplied:
                values.pop("source_system", None)
            before_value = _audit_state(existing)
            async with db.begin_nested():
                if existing:
                    # Imported coordinates never replace a manually verified point.
                    if existing.coord_source == "manual" and (existing.coord_confidence or 0) >= 0.9:
                        values.pop("lat", None); values.pop("lng", None); values.pop("coord_source", None); values.pop("coord_confidence", None)
                    for key, value in values.items():
                        setattr(existing, key, value)
                    camera, action = existing, "bulk_update"
                else:
                    camera, action = Camera(**values), "bulk_create"
                    db.add(camera)
                await db.flush()
                await db.refresh(camera)
                await db.execute(text("""INSERT INTO camera_audit_log(camera_id, actor, action, before_value, after_value, correlation_id)
                    VALUES (CAST(:id AS uuid), :actor, :action, CAST(:before AS jsonb), CAST(:after AS jsonb), CAST(:correlation AS uuid))"""),
                    {"id": str(camera.id), "actor": principal.username, "action": action,
                     "before": json.dumps(before_value), "after": json.dumps({**_audit_state(camera), "import_id": str(import_id), "column_map": mapping}),
                     "correlation": str(import_id)})
            accepted += 1
        except (ValidationError, ValueError, TypeError, IntegrityError) as exc:
            errors.append({"row": row_number, "error": str(exc)})
    await db.execute(text("""UPDATE camera_imports SET accepted_rows=:accepted, rejected_rows=:rejected,
        errors=CAST(:errors AS jsonb), column_map=CAST(:column_map AS jsonb), status='completed', completed_at=NOW() WHERE id=CAST(:id AS uuid)"""),
        {"id": str(import_id), "accepted": accepted, "rejected": len(rows) - accepted, "errors": json.dumps(errors[:100]), "column_map": json.dumps(import_column_map)})
    await db.commit()
    return {"import_id": str(import_id), "total_rows": len(rows), "accepted_rows": accepted,
            "rejected_rows": len(rows) - accepted, "errors": errors[:100]}


@router.get("/imports")
async def list_camera_imports(limit: int = Query(20, ge=1, le=100), _: Principal = Depends(require_permission("registry:admin")), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT * FROM camera_imports ORDER BY created_at DESC LIMIT :limit"), {"limit": limit})
    return [dict(row) for row in result.mappings()]


@router.get("/export")
async def export_cameras(profile: str = Query("registry", pattern="^(registry|health|audit)$"), _: Principal = Depends(require_permission("camera:read")), db: AsyncSession = Depends(get_db)):
    """Export public registry metadata only; URLs/credentials are never exported."""
    result = await db.execute(select(Camera).where(Camera.status != 'deleted').order_by(Camera.stream_id))
    if profile == "audit":
        result = await db.execute(text("SELECT camera_id,actor,action,before_value,after_value,correlation_id,created_at FROM camera_audit_log ORDER BY created_at DESC"))
        headers, values_rows = "camera_id,actor,action,before_value,after_value,correlation_id,created_at\n", result.mappings().all()
        rows = [headers] + [",".join('"' + str(value or '').replace('"', '""') + '"' for value in row.values()) + "\n" for row in values_rows]
        return Response("".join(rows), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=camera-audit.csv"})
    headers = ("id,stream_id,name,location,latitude,longitude,coord_source,coord_confidence,department,owner,camera_type,status,health_status,maintenance_status,retention_days,analytics_capabilities,vendor_id,model_id,processing_fps_category\n"
               if profile == "registry" else "id,stream_id,name,status,health_status,connectivity_status,last_frame_at,observed_at,source_fps,decode_fps,published_fps,reconnect_count,decode_failure_count\n")
    rows = [headers]
    for c in result.scalars():
        values = ([c.id, c.stream_id, c.name, c.location, c.lat, c.lng, c.coord_source, c.coord_confidence, c.department,
                   c.owner_organization, c.camera_type, c.status, c.health_status, c.maintenance_status, c.retention_days,
                   c.analytics_capabilities, c.vendor_id, c.model_id, c.processing_fps_category] if profile == "registry" else
                  [c.id, c.stream_id, c.name, c.status, c.health_status, c.connectivity_status, c.last_frame_at, c.observed_at,
                   c.observed_source_fps, c.observed_decode_fps, c.observed_published_fps, c.reconnect_count, c.decode_failure_count])
        rows.append(",".join('"' + str(v or '').replace('"', '""') + '"' for v in values) + "\n")
    return Response("".join(rows), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=camera-registry.csv"})


@router.get("/geojson")
async def cameras_geojson(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""SELECT id, stream_id, name, department, camera_type, status, health_status,
        coord_source, coord_confidence, ST_AsGeoJSON(geom)::json AS geometry
        FROM cameras WHERE status <> 'deleted' AND geom IS NOT NULL ORDER BY stream_id"""))
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": str(c["id"]), "geometry": json.loads(c["geometry"]) if isinstance(c["geometry"], str) else c["geometry"],
         "properties": {key: c[key] for key in ("id", "name", "stream_id", "department", "camera_type", "status", "health_status", "coord_source", "coord_confidence")}}
        for c in result.mappings()
    ]}


@router.get("/stats/summary")
async def camera_stats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("""
        SELECT c.id, c.name, c.stream_id, c.status, c.codec,
               c.width, c.height, c.hls_url,
               COUNT(a.id) FILTER (WHERE a.created_at > NOW() - INTERVAL '1 hour') AS alerts_1h,
               COUNT(a.id) FILTER (WHERE a.acknowledged = FALSE)                   AS unacked
        FROM cameras c
        LEFT JOIN alerts a ON a.cam_id = c.id
        WHERE c.status != 'deleted'
        GROUP BY c.id, c.name, c.stream_id, c.status, c.codec, c.width, c.height, c.hls_url
        ORDER BY c.stream_id
    """))
    return [dict(r) for r in result.mappings().all()]


@router.get("/analytics/recent")
async def recent_camera_analytics(
    seconds: int = Query(90, ge=10, le=3600),
    db: AsyncSession = Depends(get_db),
):
    """Latest persisted analytics per camera for live UI overlays.

    This deliberately reads durable detections instead of a transient Redis
    consumer stream, so a rendered plate is auditable and searchable later.
    """
    result = await db.execute(text("""
        SELECT DISTINCT ON (cam_id)
               id, cam_id, detection_type, plate_text, confidence, timestamp,
               global_track_id, track_id
        FROM detections
        WHERE cam_id IS NOT NULL
          AND timestamp >= NOW() - (CAST(:seconds AS integer) * INTERVAL '1 second')
          AND plate_text IS NOT NULL AND plate_text <> ''
        ORDER BY cam_id, timestamp DESC
    """), {"seconds": seconds})
    return [dict(row) for row in result.mappings().all()]


@router.get("/{cam_id}", response_model=CameraOut)
async def get_camera(cam_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    cam = await db.get(Camera, cam_id)
    if not cam:
        raise HTTPException(404, "Camera not found")
    return cam


@router.get("/{cam_id}/snapshot")
async def snapshot(cam_id: uuid.UUID):
    """Return latest JPEG frame cached by ingestion worker (10 s TTL)."""
    r    = redis_lib.from_url(REDIS_URL, decode_responses=False)
    data = r.get(f"snapshot:{cam_id}")
    if not data:
        raise HTTPException(404, "No snapshot available yet — stream may still be connecting")
    return Response(content=base64.b64decode(data), media_type="image/jpeg")


@router.get("/pipeline/stats")
async def pipeline_stats():
    """Return Redis stream lengths — proves pipeline is alive without DB queries."""
    import redis as redis_lib
    try:
        r = redis_lib.from_url(REDIS_URL, decode_responses=True)
        return {
            "raw_frames":  r.xlen("raw_frames"),
            "detections":  r.xlen("detections"),
            "alerts":      r.xlen("alerts"),
            "cam_resets":  r.xlen("cam_resets") if r.exists("cam_resets") else 0,
        }
    except Exception as e:
        return {"error": str(e)}
