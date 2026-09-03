#!/usr/bin/env python3
"""Behavior Worker: adaptive camera-baseline crowd/running/loitering anomaly detection."""
import os, base64, uuid, time, logging
import cv2, numpy as np
import redis
from event_schema import detection_event
from behavior_policy import AdaptiveBaseline

log = logging.getLogger("behavior_worker")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
PREFIX = "test:" if TEST_MODE else ""
GROUP = "test_behavior_workers" if TEST_MODE else "behavior_workers"
IN_STREAM = f"{PREFIX}raw_frames"
OUT_STREAM = f"{PREFIX}detections"
RESET_STREAM = f"{PREFIX}cam_resets"
OUT_MAX = 5000

FLOW_HIGH_THRESH = float(os.getenv("FLOW_HIGH_THRESH", "6.0"))
FLOW_CROWD_THRESH = float(os.getenv("FLOW_CROWD_THRESH", "3.0"))
LOITER_FRAMES = max(20, int(os.getenv("LOITER_FRAMES", "50")))
LOITER_MOT_THRESH = float(os.getenv("LOITER_MOT_THRESH", "0.5"))
BASELINE_ALPHA = max(0.005, min(0.30, float(os.getenv("CROWD_BASELINE_ALPHA", "0.04"))))
BASELINE_SIGMA = max(1.0, float(os.getenv("CROWD_DEVIATION_SIGMA", "2.5")))
MIN_FLOW = max(0.5, float(os.getenv("CROWD_MIN_FLOW", "3.5")))
WARMUP_SECS = max(5.0, float(os.getenv("CROWD_BASELINE_WARMUP_SECS", "30")))
PERSISTENCE_SECS = max(1.0, float(os.getenv("CROWD_PERSISTENCE_SECS", "5")))
COOLDOWN_SECS = max(5.0, float(os.getenv("CROWD_COOLDOWN_SECS", "300")))
RUNNING_DELTA = max(1.0, float(os.getenv("RUNNING_FLOW_DELTA", "6.0")))


def _ensure_group(r, stream, group):
    try:
        r.xgroup_create(stream, group, id="$", mkstream=True)
    except redis.exceptions.ResponseError:
        pass


def _decode(data):
    buf = base64.b64decode(data[b"frame"])
    return cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)


class CameraState:
    def __init__(self):
        self.prev_gray = None
        self.still_count = 0
        self.baseline = AdaptiveBaseline(
            alpha=BASELINE_ALPHA, sigma=BASELINE_SIGMA, minimum_flow=MIN_FLOW,
            warmup_seconds=WARMUP_SECS, persistence_seconds=PERSISTENCE_SECS,
            cooldown_seconds=COOLDOWN_SECS, running_delta=RUNNING_DELTA,
        )

    def reset(self):
        self.prev_gray = None
        self.still_count = 0
        self.baseline.reset()

    def analyse(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (15, 15), 0)
        gray = cv2.resize(gray, (320, 180))
        if self.prev_gray is None:
            self.prev_gray = gray
            return None, 0.0, {}
        flow = cv2.calcOpticalFlowFarneback(self.prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        mean_mag = float(np.mean(mag)); std_mag = float(np.std(mag))
        self.prev_gray = gray
        now = time.monotonic()
        anomaly, score, warmup = self.baseline.update(mean_mag, now)
        if mean_mag < LOITER_MOT_THRESH:
            self.still_count += 1
        else:
            self.still_count = max(0, self.still_count - 1)
        if not warmup and anomaly is None and self.still_count >= LOITER_FRAMES and now >= self.baseline.cooldown_until:
            anomaly = "abandoned_object"
            score = min(1.0, self.still_count / max(LOITER_FRAMES * 2.0, 100.0))
            self.still_count = 0
            self.baseline.cooldown_until = now + COOLDOWN_SECS
        details = {
            "observed_flow": round(mean_mag, 4), "flow_std": round(std_mag, 4),
            "baseline_flow": round(self.baseline.mean or 0.0, 4),
            "baseline_std": round(self.baseline.std, 4), "baseline_warmup": warmup,
        }
        return anomaly, score, details


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [BEHAVIOR][%(levelname)s] %(message)s")
    log.info("Behavior worker starting with adaptive camera baselines")
    r = redis.from_url(REDIS_URL, decode_responses=False)
    _ensure_group(r, IN_STREAM, GROUP)
    _ensure_group(r, RESET_STREAM, "behavior_reset_watchers")
    consumer = f"bhv-{uuid.uuid4().hex[:8]}"
    states = {}
    last_reset_id = "$"
    log.info("Behavior worker ready: baseline_alpha=%s sigma=%s warmup=%ss persistence=%ss", BASELINE_ALPHA, BASELINE_SIGMA, WARMUP_SECS, PERSISTENCE_SECS)
    while True:
        try:
            resets = r.xread({RESET_STREAM: last_reset_id}, count=20, block=1)
            for _, entries in resets or []:
                for reset_id, data in entries:
                    cam_id = data.get(b"cam_id", b"").decode()
                    if cam_id in states:
                        states[cam_id].reset()
                    last_reset_id = reset_id
            msgs = r.xreadgroup(GROUP, consumer, {IN_STREAM: ">"}, count=4, block=200)
        except redis.exceptions.ResponseError as exc:
            if "NOGROUP" in str(exc):
                _ensure_group(r, IN_STREAM, GROUP); continue
            raise
        if not msgs:
            continue
        for _, entries in msgs:
            for msg_id, data in entries:
                try:
                    cam_id = data[b"cam_id"].decode(); frame = _decode(data)
                    if frame is None: continue
                    state = states.setdefault(cam_id, CameraState())
                    anomaly, score, details = state.analyse(frame)
                    if anomaly and score > 0.2:
                        r.xadd(OUT_STREAM, detection_event(data, "anomaly", anomaly_type=anomaly, anomaly_score=score,
                                                           conf=score, **details), maxlen=OUT_MAX, approximate=True)
                        log.info("Anomaly camera=%s type=%s score=%.3f details=%s", cam_id, anomaly, score, details)
                except Exception:
                    log.error("Behavior error", exc_info=True)
                finally:
                    r.xack(IN_STREAM, GROUP, msg_id)
