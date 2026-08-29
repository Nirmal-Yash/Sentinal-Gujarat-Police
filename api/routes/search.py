from fastapi import APIRouter, Depends, Query, File, UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from auth import require_permission, Principal
from database import get_db
from rate_limit import rate_limit
import re, os, base64, json, time, uuid, asyncio
from sqlalchemy import text
import numpy as np

router = APIRouter(prefix='/search', tags=['search'], dependencies=[Depends(require_permission('search:read'))])

@router.get('/cameras')
async def search_cameras(q: str = Query(..., min_length=1, max_length=100), limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: AsyncSession = Depends(get_db)):
    result = await db.execute(text('''
        SELECT id, stream_id, name, location, lat, lng, hls_url, whep_url,
               ('https://live.corp8.cloud/stream/' || stream_id::text) AS stream_url,
               department, owner_organization, camera_type, status, health_status,
               COALESCE(observed_codec, codec) AS effective_codec,
               COALESCE(observed_width, width) AS effective_width,
               COALESCE(observed_height, height) AS effective_height,
               COALESCE(observed_source_fps, observed_fps, fps) AS effective_fps
        FROM cameras
        WHERE status <> 'deleted' AND (
          name ILIKE :pattern OR location ILIKE :pattern OR department ILIKE :pattern
          OR owner_organization ILIKE :pattern OR camera_type ILIKE :pattern
          OR status ILIKE :pattern OR health_status ILIKE :pattern OR stream_id::text ILIKE :pattern
        )
        ORDER BY similarity(name, :needle) DESC, stream_id
        LIMIT :limit OFFSET :offset'''), {'needle': q.strip(), 'pattern': f'%{q.strip()}%', 'limit': limit, 'offset': offset})
    return {'query': q, 'items': [dict(row) for row in result.mappings()], 'limit': limit, 'offset': offset}

@router.get('/plate', dependencies=[Depends(rate_limit('plate-search', int(os.getenv('PLATE_SEARCH_RATE_LIMIT','60')), int(os.getenv('PLATE_SEARCH_RATE_WINDOW','60'))))])
async def search_plate(q: str = Query(..., min_length=1, max_length=100), limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db)):
    normalized = re.sub(r'[^A-Z0-9]', '', q.upper())
    if len(normalized) < 3: return {'query': q, 'detections': [], 'watchlist_hits': [], 'journeys': []}
    result = await db.execute(text('''SELECT s.id,s.camera_id AS cam_id,s.source_timestamp AS timestamp,s.normalized_plate AS plate_text,s.confidence,c.name AS cam_name,c.location,c.lat,c.lng,s.track_id,s.global_vehicle_id,s.journey_id
        FROM vehicle_sightings s JOIN cameras c ON c.id=s.camera_id WHERE s.normalized_plate ILIKE :pat ORDER BY s.source_timestamp DESC LIMIT :limit'''), {'pat': f'%{normalized}%', 'limit': limit})
    rows=[dict(r) for r in result.mappings().all()]
    wl=await db.execute(text('SELECT id,name,description,alert_priority FROM watchlist WHERE plate_number ILIKE :pat AND is_active=TRUE'), {'pat':f'%{normalized}%'})
    journeys=await db.execute(text('SELECT j.id,j.started_at,j.ended_at,j.sighting_count,j.journey_confidence,j.status FROM vehicle_journeys j JOIN vehicle_identities v ON v.id=j.vehicle_identity_id WHERE v.normalized_plate=:plate ORDER BY j.started_at DESC LIMIT 20'), {'plate':normalized})
    return {'query':q,'detections':rows,'watchlist_hits':[dict(r) for r in wl.mappings().all()],'journeys':[dict(r) for r in journeys.mappings().all()]}

@router.get('/plate/{plate}/journey')
async def search_plate_journey(plate: str, db: AsyncSession = Depends(get_db)):
    normalized=re.sub(r'[^A-Z0-9]','',plate.upper())
    if len(normalized)<3:return {'plate':plate,'journeys':[]}
    result=await db.execute(text('''SELECT j.id AS journey_id,j.started_at,j.ended_at,j.sighting_count,j.journey_confidence,j.status,js.sequence_no,s.id AS sighting_id,s.source_timestamp AS timestamp,s.camera_id AS cam_id,c.name AS cam_name,c.location,c.lat,c.lng,s.normalized_plate AS plate_text,s.confidence,s.track_id
        FROM vehicle_journeys j JOIN vehicle_identities v ON v.id=j.vehicle_identity_id JOIN vehicle_journey_sightings js ON js.journey_id=j.id JOIN vehicle_sightings s ON s.id=js.sighting_id LEFT JOIN cameras c ON c.id=s.camera_id WHERE v.normalized_plate=:plate ORDER BY j.started_at DESC,js.sequence_no ASC'''), {'plate':normalized})
    return {'plate':normalized,'journeys':[dict(r) for r in result.mappings().all()]}

@router.get('/track/{global_track_id}')
async def search_by_track(global_track_id: str, db: AsyncSession = Depends(get_db)):
    result=await db.execute(text('''SELECT s.id,s.camera_id AS cam_id,s.source_timestamp AS timestamp,s.vehicle_type AS detection_type,s.confidence,s.global_vehicle_id AS global_track_id,c.name AS cam_name,c.lat,c.lng FROM vehicle_sightings s JOIN cameras c ON c.id=s.camera_id WHERE s.global_vehicle_id=:tid OR s.track_id=:tid ORDER BY s.source_timestamp ASC'''), {'tid':global_track_id})
    rows=[dict(r) for r in result.mappings().all()]
    if not rows:
        result=await db.execute(text('''SELECT d.id,d.cam_id,d.timestamp,d.detection_type,d.confidence,d.global_track_id,c.name AS cam_name,c.lat,c.lng FROM detections d JOIN cameras c ON c.id=d.cam_id WHERE d.global_track_id=:tid ORDER BY d.timestamp ASC'''), {'tid':global_track_id});rows=[dict(r) for r in result.mappings().all()]
    return {'global_track_id':global_track_id,'sightings':rows}

@router.get('/alerts/recent')
async def recent_alerts(minutes:int=Query(60,ge=1,le=1440),priority:str|None=None,db:AsyncSession=Depends(get_db)):
    q='''SELECT a.id,a.alert_type,a.priority,a.confidence,a.entity_type,a.details,a.created_at,a.status,c.name AS cam_name,c.lat,c.lng FROM alerts a LEFT JOIN cameras c ON c.id=a.cam_id WHERE a.created_at > NOW() - (:minutes || ' minutes')::INTERVAL''';params={'minutes':minutes}
    if priority:q+=' AND a.priority=:priority';params['priority']=priority.upper()
    q+=' ORDER BY a.created_at DESC LIMIT 200';result=await db.execute(text(q),params);return [dict(r) for r in result.mappings().all()]

@router.post('/person/validate',dependencies=[Depends(rate_limit('person-investigation',int(os.getenv('PERSON_SEARCH_RATE_LIMIT','20')),int(os.getenv('PERSON_SEARCH_RATE_WINDOW','60'))))])
async def validate_person_photo(file: UploadFile = File(...), db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_permission('search:read'))):
    if not file.content_type or not file.content_type.startswith('image/'):raise HTTPException(415,'Upload an image file')
    payload=await file.read()
    if not payload or len(payload)>10*1024*1024:raise HTTPException(413,'Image must be between 1 byte and 10 MB')
    try:
        import cv2
        image=cv2.imdecode(np.frombuffer(payload,dtype=np.uint8),cv2.IMREAD_COLOR)
        if image is None:raise HTTPException(422,'Image could not be decoded')
        gray=cv2.equalizeHist(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY));cascade=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml');faces=cascade.detectMultiScale(gray,scaleFactor=1.08,minNeighbors=5,minSize=(48,48)) if not cascade.empty() else ()
        return {'valid':bool(len(faces)),'face_count':int(len(faces)),'faces':[{'x':int(x),'y':int(y),'width':int(w),'height':int(h)} for x,y,w,h in faces],'message':'Face detected' if len(faces) else 'No visible face detected'}
    except HTTPException:raise
    except Exception as exc:raise HTTPException(422,'Unable to validate image') from exc

@router.post('/person/investigate',dependencies=[Depends(rate_limit('person-investigation-run',int(os.getenv('PERSON_SEARCH_RUN_RATE_LIMIT','10')),int(os.getenv('PERSON_SEARCH_RUN_RATE_WINDOW','300'))))])
async def investigate_person(files:list[UploadFile]=File(...),db:AsyncSession=Depends(get_db)):
    if not files:raise HTTPException(400,'Upload at least one reference image')
    r=__import__('redis.asyncio',fromlist=['from_url']).from_url(os.getenv('REDIS_URL','redis://localhost:6379'),decode_responses=False)
    all_embeddings=[]
    try:
        for file in files[:10]:
            if not file.content_type or not file.content_type.startswith('image/'):continue
            payload=await file.read()
            if not payload or len(payload)>10*1024*1024:continue
            job_id=uuid.uuid4().hex; image_key=f'person:image:{job_id}';result_key=f'person:result:{job_id}'
            await r.set(image_key,payload,ex=30);await r.xadd('person:investigations',{'request_id':job_id,'image_key':image_key,'result_key':result_key},maxlen=1000,approximate=True)
            deadline=time.monotonic()+float(os.getenv('PERSON_INVESTIGATION_TIMEOUT','20'));result=None
            while time.monotonic()<deadline:
                raw=await r.get(result_key)
                if raw:result=json.loads(raw);break
                await asyncio.sleep(0.15)
            if result and result.get('status')=='ok':all_embeddings.extend(result.get('embeddings',[]))
        if not all_embeddings:return {'status':'no_match','matches':[],'message':'No usable face embedding was produced'}
        matches=[]
        for encoded in all_embeddings:
            vector=np.frombuffer(base64.b64decode(encoded),dtype=np.float32).tolist();literal='['+','.join(str(float(v)) for v in vector)+']'
            result=await db.execute(text('''SELECT gt.id,gt.entity_type,gt.first_seen_cam,gt.last_seen_cam,gt.first_seen_at,gt.last_seen_at,gt.cam_history,gt.plate_text,1-(gt.embedding <=> CAST(:vector AS vector)) AS similarity FROM global_tracks gt WHERE gt.entity_type='person' AND gt.embedding IS NOT NULL ORDER BY gt.embedding <=> CAST(:vector AS vector) LIMIT 20'''),{'vector':literal});matches.extend(dict(row) for row in result.mappings())
        grouped={}
        for m in matches:
            key=str(m['id']);grouped[key]=m if key not in grouped else (m if float(m['similarity'] or 0)>float(grouped[key]['similarity'] or 0) else grouped[key])
        threshold=float(os.getenv('FACE_INVESTIGATION_THRESHOLD','0.65'));ranked=sorted(grouped.values(),key=lambda x:float(x['similarity'] or 0),reverse=True);ranked=[m for m in ranked if float(m['similarity'] or 0)>=threshold][:20]
        return {'status':'matches' if ranked else 'no_match','matches':ranked,'threshold':threshold}
    finally:
        try:await r.aclose()
        except Exception:pass
