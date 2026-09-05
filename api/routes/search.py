from fastapi import APIRouter, Depends, Query, File, UploadFile, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from auth import require_permission, Principal
from database import get_db
from rate_limit import rate_limit
from plate_normalise import normalize_plate
import os, base64, json, time, uuid, asyncio
from sqlalchemy import text
import numpy as np

router = APIRouter(prefix='/search', tags=['search'], dependencies=[Depends(require_permission('search:read'))])


@router.get('/cameras')
async def search_cameras(q: str = Query(..., min_length=1, max_length=100), limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text('''SELECT id, stream_id, name, location, lat, lng, hls_url, whep_url,
        ('/api/cctv/cam' || LPAD(stream_id::text, 2, '0') || '/index.m3u8') AS stream_url,
        department,owner_organization,camera_type,status,health_status,
        COALESCE(observed_codec,codec) AS effective_codec,COALESCE(observed_width,width) AS effective_width,
        COALESCE(observed_height,height) AS effective_height,COALESCE(observed_source_fps,observed_fps,fps) AS effective_fps
        FROM cameras WHERE status <> 'deleted' AND (name ILIKE :pattern OR location ILIKE :pattern OR department ILIKE :pattern
        OR owner_organization ILIKE :pattern OR camera_type ILIKE :pattern OR status ILIKE :pattern OR health_status ILIKE :pattern OR stream_id::text ILIKE :pattern)
        ORDER BY similarity(name,:needle) DESC,stream_id LIMIT :limit OFFSET :offset'''),
        {'needle': q.strip(), 'pattern': f'%{q.strip()}%', 'limit': limit, 'offset': offset})
    return {'query': q, 'items': [dict(row) for row in result.mappings()], 'limit': limit, 'offset': offset}


@router.get('/plate', dependencies=[Depends(rate_limit('plate-search', int(os.getenv('PLATE_SEARCH_RATE_LIMIT', '60')), int(os.getenv('PLATE_SEARCH_RATE_WINDOW', '60'))))])
async def search_plate(q: str = Query(..., min_length=1, max_length=100), x_test_session_id: str | None = Header(None, alias='X-Test-Session-Id'), limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db)):
    normalized = normalize_plate(q)
    if not normalized or len(normalized) < 3:
        return {'query': q, 'detections': [], 'watchlist_hits': [], 'journeys': [], 'session_id': x_test_session_id}
    if x_test_session_id:
        try:
            session_uuid = str(uuid.UUID(x_test_session_id))
        except ValueError as exc:
            raise HTTPException(400, 'Invalid X-Test-Session-Id') from exc
        if not await db.scalar(text("SELECT 1 FROM test_sessions WHERE id=CAST(:id AS uuid) AND status IN ('starting','active')"), {'id': session_uuid}):
            raise HTTPException(404, 'Test session not active')
        result = await db.execute(text('''SELECT td.id,td.stream_id AS cam_id,td.event_at AS timestamp,td.plate_text,td.confidence,COALESCE(f.camera_label,td.camera_label) AS cam_name,NULL AS location,NULL AS lat,NULL AS lng,td.track_id,NULL AS global_vehicle_id,NULL AS journey_id
            FROM test_detections td LEFT JOIN test_session_feeds f ON f.session_id=td.session_id AND f.stream_id=td.stream_id
            WHERE td.session_id=CAST(:session AS uuid) AND regexp_replace(upper(COALESCE(td.plate_text,'')),'[^A-Z0-9]','','g')=:plate
              AND COALESCE(td.details->>'plate_validated','0') IN ('1','true') AND COALESCE(td.details->>'anpr_consensus','0') IN ('1','true')
            ORDER BY td.event_at DESC LIMIT :limit'''), {'session': session_uuid, 'plate': normalized, 'limit': limit})
        rows = [dict(r) for r in result.mappings().all()]
    else:
        result = await db.execute(text('''SELECT s.id,s.camera_id AS cam_id,s.source_timestamp AS timestamp,s.normalized_plate AS plate_text,s.confidence,c.name AS cam_name,c.location,c.lat,c.lng,s.track_id,s.global_vehicle_id,s.journey_id
            FROM vehicle_sightings s JOIN cameras c ON c.id=s.camera_id WHERE s.normalized_plate=:plate ORDER BY s.source_timestamp DESC LIMIT :limit'''), {'plate': normalized, 'limit': limit})
        rows = [dict(r) for r in result.mappings().all()]
    wl = await db.execute(text("SELECT id,name,description,alert_priority FROM watchlist WHERE regexp_replace(upper(COALESCE(plate_number,'')),'[^A-Z0-9]','','g')=:plate AND is_active=TRUE"), {'plate': normalized})
    journeys = [] if x_test_session_id else [dict(r) for r in (await db.execute(text('SELECT j.id,j.started_at,j.ended_at,j.sighting_count,j.journey_confidence,j.status FROM vehicle_journeys j JOIN vehicle_identities v ON v.id=j.vehicle_identity_id WHERE v.normalized_plate=:plate ORDER BY j.started_at DESC LIMIT 20'), {'plate': normalized})).mappings().all()]
    return {'query': q, 'detections': rows, 'watchlist_hits': [dict(r) for r in wl.mappings().all()], 'journeys': journeys, 'session_id': x_test_session_id}


@router.get('/plate/{plate}/journey')
async def search_plate_journey(plate: str, db: AsyncSession = Depends(get_db)):
    normalized = normalize_plate(plate)
    if not normalized or len(normalized) < 3:
        return {'plate': plate, 'journeys': []}
    result = await db.execute(text('''SELECT j.id AS journey_id,j.started_at,j.ended_at,j.sighting_count,j.journey_confidence,j.status,js.sequence_no,s.id AS sighting_id,s.source_timestamp AS timestamp,s.camera_id AS cam_id,c.name AS cam_name,c.location,c.lat,c.lng,s.normalized_plate AS plate_text,s.confidence,s.track_id
        FROM vehicle_journeys j JOIN vehicle_identities v ON v.id=j.vehicle_identity_id JOIN vehicle_journey_sightings js ON js.journey_id=j.id JOIN vehicle_sightings s ON s.id=js.sighting_id LEFT JOIN cameras c ON c.id=s.camera_id WHERE v.normalized_plate=:plate ORDER BY j.started_at DESC,js.sequence_no ASC'''), {'plate': normalized})
    return {'plate': normalized, 'journeys': [dict(r) for r in result.mappings().all()]}


@router.get('/track/{global_track_id}')
async def search_by_track(global_track_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(text('''SELECT s.id,s.camera_id AS cam_id,s.source_timestamp AS timestamp,s.vehicle_type AS detection_type,s.confidence,s.global_vehicle_id AS global_track_id,c.name AS cam_name,c.lat,c.lng FROM vehicle_sightings s JOIN cameras c ON c.id=s.camera_id WHERE s.global_vehicle_id=:tid OR s.track_id=:tid ORDER BY s.source_timestamp ASC'''), {'tid': global_track_id})
    rows = [dict(r) for r in result.mappings().all()]
    if not rows:
        result = await db.execute(text('''SELECT d.id,d.cam_id,d.timestamp,d.detection_type,d.confidence,d.global_track_id,c.name AS cam_name,c.lat,c.lng FROM detections d JOIN cameras c ON c.id=d.cam_id WHERE d.global_track_id=:tid ORDER BY d.timestamp ASC'''), {'tid': global_track_id})
        rows = [dict(r) for r in result.mappings().all()]
    return {'global_track_id': global_track_id, 'sightings': rows}


@router.get('/alerts/recent')
async def recent_alerts(minutes: int = Query(60, ge=1, le=1440), priority: str | None = None, db: AsyncSession = Depends(get_db)):
    q = '''SELECT a.id,a.alert_type,a.priority,a.confidence,a.entity_type,a.details,a.created_at,a.status,c.name AS cam_name,c.lat,c.lng FROM alerts a LEFT JOIN cameras c ON c.id=a.cam_id WHERE a.created_at > NOW() - (:minutes || ' minutes')::INTERVAL'''
    params = {'minutes': minutes}
    if priority:
        q += ' AND a.priority=:priority'; params['priority'] = priority.upper()
    q += ' ORDER BY a.created_at DESC LIMIT 200'
    result = await db.execute(text(q), params)
    return [dict(r) for r in result.mappings()]


def _prepare_face_image(payload: bytes) -> bytes:
    from PIL import Image, ImageOps
    from io import BytesIO
    with Image.open(BytesIO(payload)) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode != 'RGB': image = image.convert('RGB')
        width, height = image.size; scale = max(1.0, 160.0 / max(1, min(width, height)))
        if scale > 1.0: image = image.resize((max(160, int(width * scale)), max(160, int(height * scale))), Image.Resampling.LANCZOS)
        max_dim = 1280
        if max(image.size) > max_dim:
            scale = max_dim / max(image.size)
            image = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
        output = BytesIO(); image.save(output, format='JPEG', quality=95, optimize=True); return output.getvalue()


async def _run_person_analysis(payload: bytes, timeout: float, operation: str, test_mode: bool = False):
    import redis.asyncio as redis_async
    r = redis_async.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379'), decode_responses=False)
    job_id = uuid.uuid4().hex
    prefix = 'test:' if test_mode else ''
    image_key = f'{prefix}person:image:{job_id}'
    result_key = f'{prefix}person:result:{job_id}'
    stream = f'{prefix}person:investigations'
    try:
        await r.set(image_key, payload, ex=max(30, int(timeout) + 10))
        await r.xadd(stream, {'request_id': job_id, 'image_key': image_key, 'result_key': result_key, 'operation': operation}, maxlen=1000, approximate=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = await r.get(result_key)
            if raw: return json.loads(raw)
            await asyncio.sleep(.15)
        raise TimeoutError('Person analysis worker timeout')
    finally:
        try: await r.delete(image_key); await r.delete(result_key); await r.aclose()
        except Exception: pass


@router.post('/person/validate', dependencies=[Depends(rate_limit('person-investigation', int(os.getenv('PERSON_SEARCH_RATE_LIMIT', '20')), int(os.getenv('PERSON_SEARCH_RATE_WINDOW', '60'))))])
async def validate_person_photo(file: UploadFile = File(...), x_test_session_id: str | None = Header(None, alias='X-Test-Session-Id'), principal: Principal = Depends(require_permission('search:read')), db: AsyncSession = Depends(get_db)):
    if not file.content_type or not file.content_type.startswith('image/'): raise HTTPException(415, 'Upload an image file')
    payload = await file.read()
    if not payload or len(payload) > 10 * 1024 * 1024: raise HTTPException(413, 'Image must be between 1 byte and 10 MB')
    session_uuid = None
    if x_test_session_id:
        try: session_uuid = str(uuid.UUID(x_test_session_id))
        except ValueError as exc: raise HTTPException(400, 'Invalid X-Test-Session-Id') from exc
        if not await db.scalar(text("SELECT 1 FROM test_sessions WHERE id=CAST(:id AS uuid) AND status IN ('starting','active')"), {'id': session_uuid}):
            raise HTTPException(404, 'Test session not active')
    try:
        result = await _run_person_analysis(_prepare_face_image(payload), float(os.getenv('PERSON_VALIDATE_TIMEOUT', os.getenv('PERSON_INVESTIGATION_TIMEOUT', '20'))), 'validate', session_uuid is not None)
        if result.get('status') == 'error': raise HTTPException(503, 'Person analysis service unavailable')
        faces = result.get('faces') or []
        return {'valid': bool(faces), 'face_count': int(result.get('face_count', len(faces))), 'faces': faces, 'message': 'Face detected' if faces else 'No visible face detected', 'session_id': session_uuid}
    except HTTPException: raise
    except TimeoutError as exc: raise HTTPException(503, 'Person analysis service unavailable') from exc
    except Exception as exc: raise HTTPException(422, 'Unable to validate image') from exc


@router.post('/person/investigate', dependencies=[Depends(rate_limit('person-investigation-run', int(os.getenv('PERSON_SEARCH_RUN_RATE_LIMIT', '10')), int(os.getenv('PERSON_SEARCH_RUN_RATE_WINDOW', '300'))))])
async def investigate_person(files: list[UploadFile] = File(...), x_test_session_id: str | None = Header(None, alias='X-Test-Session-Id'), db: AsyncSession = Depends(get_db)):
    session_uuid = None
    if x_test_session_id:
        try: session_uuid = str(uuid.UUID(x_test_session_id))
        except ValueError as exc: raise HTTPException(400, 'Invalid X-Test-Session-Id') from exc
        if not await db.scalar(text("SELECT 1 FROM test_sessions WHERE id=CAST(:id AS uuid) AND status IN ('starting','active')"), {'id': session_uuid}):
            raise HTTPException(404, 'Test session not active')
    if not files: raise HTTPException(400, 'Upload at least one reference image')
    all_embeddings = []; timeout = float(os.getenv('PERSON_INVESTIGATION_TIMEOUT', '20'))
    for file in files[:10]:
        if not file.content_type or not file.content_type.startswith('image/'): continue
        payload = await file.read()
        if not payload or len(payload) > 10 * 1024 * 1024: continue
        try: result = await _run_person_analysis(_prepare_face_image(payload), timeout, 'investigate', session_uuid is not None)
        except TimeoutError: continue
        if result.get('status') == 'ok': all_embeddings.extend(result.get('embeddings', []))
    if not all_embeddings: return {'status':'no_match','matches':[],'message':'No usable face embedding was produced','session_id':session_uuid}
    matches=[]
    for encoded in all_embeddings:
        vector=np.frombuffer(base64.b64decode(encoded),dtype=np.float32).tolist();literal='['+','.join(str(float(v)) for v in vector)+']'
        if session_uuid:
            result=await db.execute(text('''SELECT tt.id,tt.entity_type,tt.first_camera_label,tt.last_camera_label,tt.first_seen_at,tt.last_seen_at,tt.sightings,
                1-(tt.embedding <=> CAST(:vector AS vector)) AS similarity
                FROM test_tracks tt WHERE tt.session_id=CAST(:session AS uuid) AND tt.entity_type='face' AND tt.embedding IS NOT NULL
                ORDER BY tt.embedding <=> CAST(:vector AS vector) LIMIT 20'''), {'vector':literal,'session':session_uuid})
        else:
            result=await db.execute(text('''SELECT gt.id,gt.entity_type,gt.first_seen_cam,gt.last_seen_cam,gt.first_seen_at,gt.last_seen_at,gt.cam_history,gt.plate_text,
                1-(gt.embedding <=> CAST(:vector AS vector)) AS similarity
                FROM global_tracks gt WHERE gt.entity_type='person' AND gt.embedding IS NOT NULL
                ORDER BY gt.embedding <=> CAST(:vector AS vector) LIMIT 20'''), {'vector':literal})
        matches.extend(dict(row) for row in result.mappings())
    grouped={}
    for match in matches:
        key=str(match['id']); grouped[key]=match if key not in grouped or float(match['similarity'] or 0)>float(grouped[key]['similarity'] or 0) else grouped[key]
    threshold=float(os.getenv('FACE_INVESTIGATION_THRESHOLD','0.65'))
    ranked=sorted(grouped.values(),key=lambda x:float(x['similarity'] or 0),reverse=True)
    ranked=[m for m in ranked if float(m['similarity'] or 0)>=threshold][:20]
    return {'status':'matches' if ranked else 'no_match','matches':ranked,'threshold':threshold,'session_id':session_uuid}
