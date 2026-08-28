#!/usr/bin/env python3
"""Adaptive ANPR: consume DeepSORT tracks and OCR only quality-worthy keyframes."""
import os,time,base64,uuid,logging
import cv2,numpy as np,redis,easyocr
from event_schema import detection_event
from anpr_policy import TrackANPRState,PlateObservation,normalize_indian_plate,plate_is_valid,quality_score,should_run_ocr

log=logging.getLogger("anpr_worker")
REDIS_URL=os.getenv("REDIS_URL","redis://localhost:6379")
TEST_MODE=os.getenv("TEST_MODE","false").lower()=="true"; PREFIX="test:" if TEST_MODE else ""
GROUP="test_anpr_workers" if TEST_MODE else "anpr_workers"
IN_STREAM=f"{PREFIX}raw_frames"; OUT_STREAM=f"{PREFIX}detections"; RESET_STREAM=f"{PREFIX}cam_resets"; TRACK_HASH_PREFIX=f"{PREFIX}vehicle_tracks:"
OUT_MAX=5000; TRACK_EXPIRY=float(os.getenv("ANPR_TRACK_EXPIRY_SECS","30")); OCR_INTERVAL=float(os.getenv("ANPR_OCR_INTERVAL_SECS","0.8"))
MIN_W=int(os.getenv("ANPR_MIN_VEHICLE_W","80")); MIN_H=int(os.getenv("ANPR_MIN_VEHICLE_H","60")); OCR_CONF=float(os.getenv("ANPR_OCR_MIN_CONF","0.35")); MIN_OBS=int(os.getenv("ANPR_CONFIRM_OBSERVATIONS","2")); MAX_TRACKS=int(os.getenv("ANPR_MAX_CONCURRENT_TRACKS","128"))
MIN_PLATE_W=int(os.getenv("ANPR_MIN_PLATE_WIDTH","45")); MIN_PLATE_H=int(os.getenv("ANPR_MIN_PLATE_HEIGHT","15"))


def _ensure_group(r):
    try:r.xgroup_create(IN_STREAM,GROUP,id="$",mkstream=True)
    except redis.exceptions.ResponseError:pass


def _decode(data):
    try:return cv2.imdecode(np.frombuffer(base64.b64decode(data[b"frame"]),np.uint8),cv2.IMREAD_COLOR)
    except Exception:return None


def _tracks_for_pts(r,cam,target):
    result={}
    try:items=r.hgetall(f"{TRACK_HASH_PREFIX}{cam}")
    except Exception:return []
    for key,value in items.items():
        try:
            k=key.decode() if isinstance(key,bytes) else str(key); raw=value.decode() if isinstance(value,bytes) else str(value); p=raw.split(":")
            if len(p)<9:continue
            tid=k
            if k.startswith("pts:"):
                _,stored_pts,tid=k.split(":",2)
            else:stored_pts=p[6]
            if abs(int(stored_pts)-target)>1800:continue
            x1,y1,x2,y2,_,_,pts,conf,etype=p[:9]
            if etype not in ("car","motorcycle","bus","truck"):continue
            item=(tid,int(x1),int(y1),int(x2),int(y2),float(conf),int(pts)); old=result.get(tid)
            if old is None or abs(item[-1]-target)<abs(old[-1]-target):result[tid]=item
        except (ValueError,IndexError):continue
    return list(result.values())


def _candidates(frame,x1,y1,x2,y2):
    bw,bh=x2-x1,y2-y1; H,W=frame.shape[:2]
    boxes=[(x1+int(bw*.12),y1+int(bh*.58),x2-int(bw*.12),y2),(x1,y1+int(bh*.72),x2,y2),(x1+int(bw*.08),y1+int(bh*.40),x2-int(bw*.08),y1+int(bh*.75))]
    out=[]
    for a,b,c,d in boxes:
        a=max(0,min(W-1,a));c=max(a+1,min(W,c));b=max(0,min(H-1,b));d=max(b+1,min(H,d));crop=frame[b:d,a:c]
        if crop.size and crop.shape[1]>=MIN_PLATE_W and crop.shape[0]>=MIN_PLATE_H:out.append((crop,(a,b,c,d)))
    return out


def _quality(crop):
    gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY); blur=min(1.0,float(cv2.Laplacian(gray,cv2.CV_64F).var())/500.0); return quality_score(crop.shape[1],crop.shape[0],blur,float(gray.mean())/255.0)


def _ocr(reader,crop):
    h,w=crop.shape[:2]; scale=max(2.0,min(4.0,240.0/max(1,w))); variants=[crop]
    variants.append(cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC))
    gray=cv2.cvtColor(variants[-1],cv2.COLOR_BGR2GRAY); variants.append(cv2.createCLAHE(clipLimit=2.5,tileGridSize=(4,4)).apply(gray))
    best=None
    for image in variants:
        try:rows=reader.readtext(image,detail=1,paragraph=False)
        except Exception:log.error("OCR provider error",exc_info=True);continue
        for row in rows or []:
            if not isinstance(row,(list,tuple)) or len(row)<3:continue
            text=normalize_indian_plate(str(row[1])); conf=float(row[2])
            if text and (best is None or conf>best[1]):best=(text,conf)
    return best


def run():
    logging.basicConfig(level=logging.INFO,format="%(asctime)s [ANPR][%(levelname)s] %(message)s")
    reader=easyocr.Reader(["en"],gpu=os.getenv("ANPR_OCR_GPU","false").lower()=="true",verbose=False)
    r=redis.from_url(REDIS_URL,decode_responses=False);_ensure_group(r);consumer=f"anpr-{uuid.uuid4().hex[:8]}";states={};last_reset=b"0";last_cleanup=time.monotonic()
    log.info("ANPR ready: track-driven adaptive OCR interval=%ss",OCR_INTERVAL)
    while True:
        now=time.monotonic()
        if now-last_cleanup>=5:
            for k in [k for k,s in states.items() if now-s.last_seen_at>TRACK_EXPIRY]:states.pop(k,None)
            if len(states)>MAX_TRACKS:
                old=sorted(states,key=lambda k:states[k].last_seen_at)[:len(states)-MAX_TRACKS]
                for k in old:states.pop(k,None)
            last_cleanup=now
        try:
            resets=r.xread({RESET_STREAM:last_reset},count=20,block=1)
            for _,entries in resets or []:
                for rid,data in entries:
                    cam=data.get(b"cam_id",b"").decode()
                    for k in [x for x in states if x.startswith(cam+":")]:states.pop(k,None)
                    last_reset=rid
            msgs=r.xreadgroup(GROUP,consumer,{IN_STREAM:">"},count=2,block=500)
        except redis.exceptions.ResponseError as exc:
            if "NOGROUP" in str(exc):_ensure_group(r);continue
            raise
        if not msgs:continue
        for _,entries in msgs:
            for msg_id,data in entries:
                try:
                    cam=data.get(b"cam_id",b"").decode();pts=int(data.get(b"pts_ms",b"0"));frame=_decode(data)
                    if frame is None:continue
                    for tid,x1,y1,x2,y2,track_conf,_ in _tracks_for_pts(r,cam,pts):
                        if x2-x1<MIN_W or y2-y1<MIN_H:continue
                        key=f"{cam}:{tid}";state=states.setdefault(key,TrackANPRState());state.last_seen_at=now
                        if not should_run_ocr(state,now,OCR_INTERVAL):continue
                        best=None
                        for crop,bbox in _candidates(frame,max(0,x1),max(0,y1),min(frame.shape[1],x2),min(frame.shape[0],y2)):
                            q=_quality(crop)
                            if q<0.20:continue
                            found=_ocr(reader,crop)
                            if found and (best is None or found[1]>best[1]):best=(found[0],found[1],q,bbox)
                        state.last_ocr_at=now
                        if not best:continue
                        text,ocr_conf,q,bbox=best;validated=plate_is_valid(text)
                        if not validated or ocr_conf<OCR_CONF:continue
                        state.add(PlateObservation(text,ocr_conf,track_conf,q,True,now));state.status="CONFIRMING"
                        plate,consensus=state.consensus(MIN_OBS)
                        if not plate or state.confirmed_plate:continue
                        state.confirmed_plate=plate;state.confirmed_at=now;state.status="CONFIRMED";px1,py1,px2,py2=bbox
                        combined=round(max(0,min(1,track_conf))*max(0,min(1,ocr_conf))*max(0,min(1,q)),4)
                        event=detection_event(data,"plate",raw_ocr=text,plate_text=plate,ocr_conf=ocr_conf,detector_conf=track_conf,conf=combined,vehicle_type="vehicle",track_id=tid,x1=px1,y1=py1,x2=px2,y2=py2,plate_validated=1,anpr_consensus=round(consensus,4))
                        event[b"event_type"]=b"vehicle_sighting";r.xadd(OUT_STREAM,event,maxlen=OUT_MAX,approximate=True)
                        log.info("Confirmed %s camera=%s track=%s conf=%.3f",plate,cam,tid,combined)
                except Exception:log.error("ANPR error",exc_info=True)
                finally:r.xack(IN_STREAM,GROUP,msg_id)

if __name__=="__main__":run()
