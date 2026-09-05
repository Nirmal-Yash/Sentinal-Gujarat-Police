#!/usr/bin/env python3
"""Seed an isolated, repeatable Sentinel AI Test Mode demonstration scenario."""
from __future__ import annotations
import argparse, json, os, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import psycopg2

ROOT=Path(__file__).resolve().parents[2]
DATA_ROOT=Path("/test-data") if Path("/test-data/test-camera-manifest.json").exists() else ROOT/"test-data"
MANIFEST=DATA_ROOT/"test-camera-manifest.json"
VIDEO_DIR=DATA_ROOT/"videos"
SESSION_NAME="DEMO — Sentinel AI Feature Walkthrough"
DB=os.getenv("DATABASE_URL","postgresql://sentinel:sentinel@localhost:5432/sentinel")

def juid(session,name): return str(uuid.uuid5(uuid.UUID(session),name))

def connect():
    return psycopg2.connect(DB)

def seed(reset=False):
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    missing=sorted({x["video_file"] for x in manifest["test_cameras"] if not (VIDEO_DIR/x["video_file"]).is_file()})
    if missing:
        raise SystemExit("Missing demo videos. Run: python test-data/generate_demo_videos.py\nMissing: "+", ".join(missing))
    conn=connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM test_sessions WHERE name=%s ORDER BY created_at DESC LIMIT 1",(SESSION_NAME,))
            old=cur.fetchone()
            if reset or not old:
                if old: cur.execute("DELETE FROM test_sessions WHERE id=%s",(old[0],))
                cur.execute("INSERT INTO test_sessions(name,created_by,status,loop,started_at) VALUES(%s,%s,'active',TRUE,NOW()) RETURNING id",(SESSION_NAME,"demo-seeder"))
                session=str(cur.fetchone()[0])
            else:
                session=str(old[0])
            cur.execute("DELETE FROM test_session_feeds WHERE session_id=%s::uuid",(session,))
            cur.execute("DELETE FROM test_watchlist WHERE session_id=%s::uuid",(session,))
            cur.execute("DELETE FROM test_alerts WHERE session_id=%s::uuid",(session,))
            cur.execute("DELETE FROM test_detections WHERE session_id=%s::uuid",(session,))
            cur.execute("DELETE FROM test_tracks WHERE session_id=%s::uuid",(session,))
            assets={}
            for cam in manifest["test_cameras"][:8]:
                f=VIDEO_DIR/cam["video_file"]
                cur.execute("""INSERT INTO test_video_assets(storage_key,display_name,source_kind,size_bytes)
                    VALUES(%s,%s,'bundled',%s)
                    ON CONFLICT(storage_key) DO UPDATE SET display_name=EXCLUDED.display_name,size_bytes=EXCLUDED.size_bytes
                    RETURNING id""",(f"/test-data/videos/{f.name}",f.name,f.stat().st_size))
                assets[cam["video_file"]]=str(cur.fetchone()[0])
            for n,cam in enumerate(manifest["test_cameras"],1):
                asset=assets[cam["video_file"]]
                label=cam["display_name"]
                cur.execute("""INSERT INTO test_session_feeds(session_id,asset_id,stream_id,camera_label,rtsp_path,hls_path,loop)
                    VALUES(%s::uuid,%s::uuid,%s,%s,%s,%s,TRUE)""",(session,asset,n,f"rtsp://mediamtx:8554/test/{session}/cam{n}",f"/test-hls/test/{session}/cam{n}/index.m3u8"))
            plates=[
              ("GJ01AB1234","Vehicle Alpha – Test Target","Demonstration: triggers watchlist hit and vehicle journey","HIGH"),
              ("GJ05CD5678","Vehicle Beta – Secondary","Demonstration: secondary plate sighting","MEDIUM"),
              ("GJ07XX9999","Vehicle Gamma – Inactive","Demonstration: non-match scenario","LOW")]
            for plate,name,desc,priority in plates:
                cur.execute("""INSERT INTO test_watchlist(session_id,name,entity_type,description,plate_number,alert_priority)
                  VALUES(%s::uuid,%s,'vehicle',%s,%s,%s)""",(session,name,desc,plate,priority))
            cur.execute("""INSERT INTO test_watchlist(session_id,name,entity_type,description,alert_priority)
              VALUES(%s::uuid,'Person Alpha – Test Subject','person',
              'Demonstration: person watchlist match after supplying an embedding','HIGH')""",(session,))
            base=datetime.now(timezone.utc)
            demo=[
              ("WATCHLIST_HIT","NEW","GJ01AB1234",.94,1,base-timedelta(minutes=3)),
              ("RUNNING_CROWD","NEW",None,.87,3,base-timedelta(minutes=8)),
              ("PLATE_SIGHTING","ACKNOWLEDGED","GJ05CD5678",.76,4,base-timedelta(hours=1)),
              ("CROWD_ANOMALY","ACKNOWLEDGED",None,.62,3,base-timedelta(hours=2)),
              ("WATCHLIST_HIT","INVESTIGATING","GJ01AB1234",.91,2,base-timedelta(hours=3)),
              ("PLATE_SIGHTING","RESOLVED","GJ01AB1234",.83,1,base-timedelta(days=1)),
              ("RUNNING_CROWD","RESOLVED",None,.79,3,base-timedelta(days=2)),
              ("WATCHLIST_HIT","CLOSED","GJ07XX9999",.55,6,base-timedelta(days=7))]
            for idx,(atype,status,plate,score,cam,when) in enumerate(demo,1):
                did=juid(session,f"demo-detection-{idx}")
                aid=juid(session,f"demo-alert-{idx}")
                details={"test":True,"plate_text":plate,"camera_label":manifest["test_cameras"][cam-1]["display_name"],"demo_seed":True,"score":score}
                cur.execute("""INSERT INTO test_detections(id,session_id,camera_label,detection_type,plate_text,confidence,event_at,source_timestamp,stream_id,track_id,bbox,details)
                  VALUES(%s::uuid,%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s,'{}'::jsonb,%s::jsonb)
                  ON CONFLICT(id) DO NOTHING""",
                  (did,session,manifest["test_cameras"][cam-1]["display_name"],"plate" if plate else "crowd",plate,score,when,when,cam,f"demo-track-{cam}",json.dumps(details)))
                cur.execute("""INSERT INTO test_alerts(id,session_id,detection_id,alert_type,priority,event_at,details,status,acknowledged,acknowledged_at)
                  VALUES(%s::uuid,%s::uuid,%s::uuid,%s,%s,%s,%s::jsonb,%s,%s,%s)
                  ON CONFLICT(id) DO NOTHING""",
                  (aid,session,did,atype,"HIGH" if atype in ("WATCHLIST_HIT","RUNNING_CROWD") else "MEDIUM",when,json.dumps(details),status,status!="NEW",when if status!="NEW" else None))
            journeys=[("GJ01AB1234",1,.94,base-timedelta(minutes=25)),("GJ01AB1234",2,.91,base-timedelta(minutes=18)),("GJ01AB1234",1,.89,base-timedelta(hours=2)),("GJ05CD5678",4,.76,base-timedelta(minutes=45)),("GJ05CD5678",4,.72,base-timedelta(days=1)),("GJ01AB1234",7,.68,base-timedelta(hours=6))]
            for idx,(plate,cam,conf,when) in enumerate(journeys,1):
                did=juid(session,f"journey-{idx}")
                cur.execute("""INSERT INTO test_detections(id,session_id,camera_label,detection_type,plate_text,confidence,event_at,source_timestamp,stream_id,track_id,bbox,details)
                  VALUES(%s::uuid,%s::uuid,%s,'plate',%s,%s,%s,%s,%s,%s,'{}'::jsonb,%s::jsonb) ON CONFLICT(id) DO NOTHING""",
                  (did,session,manifest["test_cameras"][cam-1]["display_name"],plate,conf,when,when,cam,f"journey-{plate}-{idx}",json.dumps({"test":True,"journey":True})))
                tid=f"journey:{plate}"
                cur.execute("""INSERT INTO test_tracks(session_id,global_track_id,entity_type,first_camera_label,last_camera_label,first_seen_at,last_seen_at,sightings)
                  VALUES(%s::uuid,%s,'vehicle',%s,%s,%s,%s,jsonb_build_array(jsonb_build_object('camera_label',%s,'timestamp',%s))
                  ) ON CONFLICT(session_id,global_track_id) DO UPDATE SET last_camera_label=EXCLUDED.last_camera_label,last_seen_at=EXCLUDED.last_seen_at,sightings=test_tracks.sightings || EXCLUDED.sightings""",
                  (session,tid,manifest["test_cameras"][cam-1]["display_name"],manifest["test_cameras"][cam-1]["display_name"],when,when,manifest["test_cameras"][cam-1]["display_name"],when.isoformat()))
        conn.commit()
        print(f"Seeded Demo Test session: {session}")
    finally:
        conn.close()

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--reset",action="store_true"); ap.add_argument("--person-image")
    args=ap.parse_args(); seed(args.reset)
