#!/usr/bin/env python3
"""Intelligence Engine — cross-camera tracking, watchlist matching, alert generation."""
import os, sys, time, logging

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [INTEL][%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DB_URL    = os.getenv("DATABASE_URL", "")
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"


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

    if TEST_MODE:
        return test_main()

    from cross_camera    import CrossCameraTracker
    from watchlist_engine import WatchlistEngine
    from alert_engine    import AlertEngine
    from sighting_store  import persist, persist_person_track, normalize_plate

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
                    det_id = data.get(b"detection_id", str(uuid.uuid4()).encode()).decode()
                    # Persist first: search, journeys and alerts must be based
                    # on durable evidence rather than a transient stream item.
                    persisted = persist(data)
                    if persisted is None:
                        raise ValueError("detection missing a stable event id")
                    ts = persisted["timestamp"].timestamp()

                    emb = None
                    if b"embedding" in data:
                        raw = base64.b64decode(data[b"embedding"])
                        emb = np.frombuffer(raw, dtype=np.float32).copy()

                    # ── Watchlist match (face or plate) ─────────────────
                    if dtype in ("face", "plate") and (emb is not None or b"plate_text" in data):
                        plate = normalize_plate(data.get(b"plate_text", b"").decode() or None)
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
                        persist_person_track(det_id, global_id, cam_id, persisted["timestamp"],
                                             float(data.get(b"conf", b"0") or 0), emb)
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


def test_main():
    """Consume only test:detections and persist only test tables/streams."""
    from test_sighting_store import persist
    import redis, json, uuid
    r = redis.from_url(REDIS_URL, decode_responses=False); stream, group = "test:detections", "test_intelligence"
    try: r.xgroup_create(stream, group, id="$", mkstream=True)
    except redis.exceptions.ResponseError: pass
    consumer = f"test-intel-{uuid.uuid4().hex[:8]}"; log.info("Test intelligence ready — isolated streams only")
    while True:
        messages = r.xreadgroup(group, consumer, {stream: ">"}, count=20, block=500)
        for _, entries in messages:
            for message_id, data in entries:
                try:
                    outcome = persist(data)
                    if outcome["alert_id"]:
                        r.xadd("test:alerts", {b"alert_id": outcome["alert_id"].encode(), b"session_id": outcome["session_id"].encode(), b"detection_id": outcome["detection_id"].encode(), b"camera_label": outcome["camera_label"].encode(), b"priority": b"LOW", b"alert_type": b"test_plate_detected", b"test": b"true"}, maxlen=5000, approximate=True)
                except Exception as exc: log.error("Test intelligence error: %s", exc, exc_info=True)
                finally: r.xack(stream, group, message_id)


if __name__ == "__main__":
    main()
