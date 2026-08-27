#!/usr/bin/env python3
"""Behavior Worker: optical flow + crowd/running/loitering anomaly detection."""
import os, base64, uuid, time, logging, collections
import cv2, numpy as np
import redis
from event_schema import detection_event

log = logging.getLogger("behavior_worker")

REDIS_URL  = os.getenv("REDIS_URL", "redis://localhost:6379")
TEST_MODE  = os.getenv("TEST_MODE", "false").lower() == "true"
PREFIX     = "test:" if TEST_MODE else ""
GROUP      = "test_behavior_workers" if TEST_MODE else "behavior_workers"
IN_STREAM  = f"{PREFIX}raw_frames"
OUT_STREAM = f"{PREFIX}detections"
OUT_MAX    = 5000

# Thresholds
FLOW_HIGH_THRESH    = 6.0   # mean magnitude → fast movement / running
FLOW_CROWD_THRESH   = 3.0   # elevated flow spread → crowd
LOITER_FRAMES       = 50    # frames of low motion before loitering alert
LOITER_MOT_THRESH   = 0.5   # below this → object/person not moving


def _ensure_group(r):
    try:
        r.xgroup_create(IN_STREAM, GROUP, id="$", mkstream=True)
    except redis.exceptions.ResponseError:
        pass


def _decode(data):
    buf = base64.b64decode(data[b"frame"])
    arr = np.frombuffer(buf, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


class CameraState:
    def __init__(self):
        self.prev_gray    = None
        self.still_count  = 0   # consecutive frames with low motion
        self.alert_cooldown = 0  # frames before next alert

    def analyse(self, frame):
        """Return (anomaly_type, score) or (None, 0)."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (15, 15), 0)
        gray = cv2.resize(gray, (320, 180))   # downscale for speed

        if self.prev_gray is None:
            self.prev_gray = gray
            return None, 0.0

        flow = cv2.calcOpticalFlowFarneback(
            self.prev_gray, gray, None,
            pyr_scale=0.5, levels=3, winsize=15,
            iterations=3, poly_n=5, poly_sigma=1.2, flags=0
        )
        mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        mean_mag = float(np.mean(mag))
        std_mag  = float(np.std(mag))
        self.prev_gray = gray

        anomaly, score = None, 0.0

        if self.alert_cooldown > 0:
            self.alert_cooldown -= 1
            return None, 0.0

        if mean_mag > FLOW_HIGH_THRESH:
            anomaly = "running_crowd"
            score   = min(1.0, mean_mag / 12.0)
            self.alert_cooldown = 30
        elif mean_mag > FLOW_CROWD_THRESH and std_mag > 2.0:
            anomaly = "crowd_formation"
            score   = min(1.0, (mean_mag - FLOW_CROWD_THRESH) / 5.0)
            self.alert_cooldown = 30
        elif mean_mag < LOITER_MOT_THRESH:
            self.still_count += 1
            if self.still_count >= LOITER_FRAMES:
                anomaly = "abandoned_object"
                score   = min(1.0, self.still_count / 100.0)
                self.still_count    = 0
                self.alert_cooldown = 60
        else:
            self.still_count = max(0, self.still_count - 1)

        return anomaly, score


def run():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [BEHAVIOR][%(levelname)s] %(message)s")
    log.info("Behavior worker starting …")
    r        = redis.from_url(REDIS_URL, decode_responses=False)
    _ensure_group(r)
    consumer = f"bhv-{uuid.uuid4().hex[:8]}"
    states   = {}   # cam_id → CameraState
    log.info("Behavior worker ready.")

    while True:
        msgs = r.xreadgroup(GROUP, consumer, {IN_STREAM: ">"}, count=4, block=200)
        if not msgs:
            continue

        for _, entries in msgs:
            for msg_id, data in entries:
                try:
                    cam_id    = data[b"cam_id"].decode()
                    frame     = _decode(data)
                    if frame is None:
                        continue

                    if cam_id not in states:
                        states[cam_id] = CameraState()

                    anomaly, score = states[cam_id].analyse(frame)

                    if anomaly and score > 0.2:
                        r.xadd(OUT_STREAM, detection_event(
                            data, "anomaly", anomaly_type=anomaly,
                            anomaly_score=score, conf=score), maxlen=OUT_MAX, approximate=True)

                except Exception as e:
                    log.error(f"Behavior error: {e}")
                finally:
                    r.xack(IN_STREAM, GROUP, msg_id)
