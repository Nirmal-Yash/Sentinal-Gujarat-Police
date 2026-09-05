from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from models import WatchlistOut, WatchlistCreate
from auth import Principal, require_role
from database import get_db
from plate_normalise import normalize_plate
import asyncio, base64, json, os, time, uuid
import numpy as np
router=APIRouter(prefix="/test/sessions/{session_id}/watchlist",tags=["test-watchlist"])

async def valid_session(session_id:uuid.UUID,db:AsyncSession):
    row=await db.execute(text("SELECT id FROM test_sessions WHERE id=CAST(:id AS uuid) AND status IN ('starting','active')"),{"id":str(session_id)})
    if not row.first(): raise HTTPException(404,"Test session not active")

async def person_embedding(payload:bytes):
    import redis.asyncio as redis_async
    r=redis_async.from_url(os.getenv("REDIS_URL","redis://localhost:6379"),decode_responses=False)
    job=uuid.uuid4().hex; image_key=f"test:person:image:{job}"; result_key=f"test:person:result:{job}"
    try:
        await r.set(image_key,payload,ex=45)
        await r.xadd("test:person:investigations",{"request_id":job,"image_key":image_key,"result_key":result_key,"operation":"investigate"},maxlen=1000,approximate=True)
        deadline=time.monotonic()+float(os.getenv("PERSON_INVESTIGATION_TIMEOUT","20"))
        while time.monotonic()<deadline:
            raw=await r.get(result_key)
            if raw:return json.loads(raw)
            await asyncio.sleep(.15)
        raise HTTPException(503,"Person analysis service unavailable")
    finally:
        try: await r.delete(image_key,result_key); await r.aclose()
        except Exception: pass

@router.get("/",response_model=list[WatchlistOut])
async def list_test_watchlist(session_id:uuid.UUID,active_only:bool=True,db:AsyncSession=Depends(get_db),_:Principal=Depends(require_role("ADMIN"))):
    await valid_session(session_id,db)
    rows=await db.execute(text("SELECT id,name,entity_type,description,plate_number,alert_priority,is_active,created_at FROM test_watchlist WHERE session_id=CAST(:id AS uuid) AND (:all OR is_active=TRUE) ORDER BY created_at DESC"),{"id":str(session_id),"all":not active_only})
    return [dict(r) for r in rows.mappings().all()]

@router.post("/",response_model=WatchlistOut,status_code=201)
async def add_test_watchlist(session_id:uuid.UUID,body:WatchlistCreate,db:AsyncSession=Depends(get_db),_:Principal=Depends(require_role("ADMIN"))):
    await valid_session(session_id,db)
    plate=normalize_plate(body.plate_number)
    row=(await db.execute(text("INSERT INTO test_watchlist(session_id,name,entity_type,description,plate_number,alert_priority) VALUES(CAST(:session AS uuid),:name,:type,:description,:plate,:priority) RETURNING id,name,entity_type,description,plate_number,alert_priority,is_active,created_at"),{"session":str(session_id),"name":body.name.strip(),"type":body.entity_type,"description":body.description.strip(),"plate":plate,"priority":body.alert_priority.upper()})).mappings().one()
    await db.commit(); return dict(row)

@router.post("/person-photo",response_model=WatchlistOut,status_code=201)
async def add_test_person_photo(session_id:uuid.UUID,name:str=Form(...),description:str=Form(""),alert_priority:str=Form("HIGH"),file:UploadFile=File(...),db:AsyncSession=Depends(get_db),_:Principal=Depends(require_role("ADMIN"))):
    await valid_session(session_id,db)
    if not file.content_type or not file.content_type.startswith("image/"): raise HTTPException(415,"Upload an image file")
    payload=await file.read()
    if not payload or len(payload)>10*1024*1024: raise HTTPException(413,"Image must be between 1 byte and 10 MB")
    result=await person_embedding(payload); embeddings=result.get("embeddings") or []
    if result.get("status")!="ok" or len(embeddings)!=1: raise HTTPException(422,"Exactly one visible face is required for a person watchlist entry")
    embedding=np.frombuffer(base64.b64decode(embeddings[0]),dtype=np.float32).copy(); embedding/=np.linalg.norm(embedding)+1e-9
    literal="["+ ",".join(str(float(x)) for x in embedding.tolist()) +"]"
    row=(await db.execute(text("INSERT INTO test_watchlist(session_id,name,entity_type,description,alert_priority,embedding) VALUES(CAST(:session AS uuid),:name,'person',:description,:priority,CAST(:embedding AS vector)) RETURNING id,name,entity_type,description,plate_number,alert_priority,is_active,created_at"),{"session":str(session_id),"name":name.strip(),"description":description.strip(),"priority":alert_priority.upper(),"embedding":literal})).mappings().one()
    await db.commit(); return dict(row)

@router.delete("/{entry_id}")
async def deactivate_test_watchlist(session_id:uuid.UUID,entry_id:uuid.UUID,db:AsyncSession=Depends(get_db),_:Principal=Depends(require_role("ADMIN"))):
    await valid_session(session_id,db)
    result=await db.execute(text("UPDATE test_watchlist SET is_active=FALSE,updated_at=NOW() WHERE id=CAST(:entry AS uuid) AND session_id=CAST(:session AS uuid) AND is_active=TRUE RETURNING id"),{"entry":str(entry_id),"session":str(session_id)})
    if not result.first(): raise HTTPException(404,"Test watchlist entry not found")
    await db.commit(); return {"status":"deactivated","id":str(entry_id),"test":True}
