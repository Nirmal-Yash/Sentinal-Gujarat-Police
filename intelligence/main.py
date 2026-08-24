#!/usr/bin/env python3
"""Intelligence Engine — cross-camera tracking, watchlist matching, alert generation."""
import os, sys, time, logging

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [INTEL][%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DB_URL    = os.getenv("DATABASE_URL", "")


def wait_for_services():
    import redis, psycopg2
    for _ in range(40):
        try:
            redis.from_url(REDIS_URL).ping()
            psycopg2.connect(DB_URL).close()
            return
        except Exception as e:
            log.info(f"Waiting for services … {e}")
            time.sleep(3)
    log.critical("Cannot reach Redis or DB.")
    sys.exit(1)


def main():
    log.info("Intelligence engine starting …")
    wait_for_services()

    from cross_camera    import CrossCameraTracker
    from watchlist_engine import WatchlistEngine
    from alert_engine    import AlertEngine

    tracker   = CrossCameraTracker()
    watchlist = WatchlistEngine()
    alerter   = AlertEngine()

    import redis, base64, json, uuid
    import numpy as np

    r        = redis.from_url(REDIS_URL, decode_responses=False)
    GROUP    = "intelligence"
    STREAM   = "detections"

    try:
        r.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
    except redis.exceptions.ResponseError:
        pass

    consumer = f"intel-{uuid.uuid4().hex[:8]}"
    log.info("Intelligence engine ready — consuming detections …")

    while True:
        msgs = r.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=10, block=500)
        if not msgs:
            continue

        for _, entries in msgs:
            for msg_id, data in entries:
                try:
                    dtype  = data.get(b"detection_type", b"").decode()
                    cam_id = data.get(b"cam_id", b"").decode()
                    ts     = float(data.get(b"timestamp", b"0"))
                    det_id = data.get(b"detection_id", str(uuid.uuid4()).encode()).decode()

                    emb = None
                    if b"embedding" in data:
                        raw = base64.b64decode(data[b"embedding"])
                        emb = np.frombuffer(raw, dtype=np.float32).copy()

                    # ── Watchlist match (face or plate) ─────────────────
                    if dtype in ("face", "plate") and (emb is not None or b"plate_text" in data):
                        plate = data.get(b"plate_text", b"").decode() or None
                        hit   = watchlist.match(emb, plate)
                        if hit:
                            alerter.fire(r, {
                                "detection_id": det_id,
                                "cam_id":       cam_id,
                                "alert_type":   "watchlist_match",
                                "priority":     hit.get("priority", "HIGH"),
                                "confidence":   hit.get("score", 0.9),
                                "entity_type":  dtype,
                                "details": {
                                    "watchlist_name": hit.get("name"),
                                    "match_type":     dtype,
                                    "plate_text":     plate,
                                    "description":    hit.get("description", ""),
                                },
                            })

                    # ── Cross-camera tracking (face embeddings) ──────────
                    if dtype == "face" and emb is not None:
                        global_id = tracker.assign(cam_id, det_id, emb, ts)
                        if tracker.is_new_camera(global_id, cam_id):
                            alerter.fire(r, {
                                "detection_id": det_id,
                                "cam_id":       cam_id,
                                "alert_type":   "cross_camera_sighting",
                                "priority":     "MEDIUM",
                                "confidence":   0.75,
                                "entity_type":  "person",
                                "details": {
                                    "global_track_id": global_id,
                                    "message": f"Entity re-identified on camera {cam_id}",
                                },
                            })

                    # ── Anomaly alerts ───────────────────────────────────
                    if dtype == "anomaly":
                        score = float(data.get(b"anomaly_score", b"0"))
                        atype = data.get(b"anomaly_type", b"unknown").decode()
                        prio  = "HIGH" if score > 0.7 else "MEDIUM"
                        alerter.fire(r, {
                            "detection_id": det_id,
                            "cam_id":       cam_id,
                            "alert_type":   f"anomaly_{atype}",
                            "priority":     prio,
                            "confidence":   score,
                            "entity_type":  "unknown",
                            "details":      {"anomaly_type": atype, "score": score},
                        })

                except Exception as e:
                    log.error(f"Intelligence error: {e}", exc_info=True)
                finally:
                    r.xack(STREAM, GROUP, msg_id)


if __name__ == "__main__":
    main()
