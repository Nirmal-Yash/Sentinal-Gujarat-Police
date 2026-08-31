#!/usr/bin/env python3
"""AI Engine supervisor for YOLO, ANPR, face and behavior workers."""
import os
import time
import logging
from multiprocessing import Process

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [AI-ENGINE][%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

YOLO_WORKERS = max(1, int(os.getenv("YOLO_WORKERS", "4")))
ANPR_ENABLED = os.getenv("ANPR_ENABLED", "true").lower() == "true"
FACE_ENABLED = os.getenv("FACE_ENABLED", "true").lower() == "true"
BEHAVIOR_ENABLED = os.getenv("BEHAVIOR_ENABLED", "true").lower() == "true"
SUPERVISOR_INTERVAL = max(5, int(os.getenv("AI_SUPERVISOR_INTERVAL_SECS", "10")))
RESTART_BASE_DELAY = max(1, float(os.getenv("AI_RESTART_BASE_DELAY_SECS", "2")))
RESTART_MAX_DELAY = max(RESTART_BASE_DELAY, float(os.getenv("AI_RESTART_MAX_DELAY_SECS", "60")))

try:
    from process_health import heartbeat, publish
except ImportError:
    def publish(*args, **kwargs):
        return None
    def heartbeat(*args, **kwargs):
        return None


def spawn(target, name):
    p = Process(target=target, name=name, daemon=True)
    started = time.time()
    p.start()
    log.info("Spawned %s (pid %s)", name, p.pid)
    return p, started


def main():
    log.info("AI Engine starting …")
    time.sleep(6)

    from yolo_worker import run as run_yolo
    from anpr_worker import run as run_anpr
    from face_worker import run as run_face
    from behavior_worker import run as run_behavior

    procs = {}

    for i in range(YOLO_WORKERS):
        name = f"YOLOv8+DeepSORT-{i+1}"
        p, started = spawn(run_yolo, name)
        procs[name] = {"fn": run_yolo, "proc": p, "started": started, "restarts": 0, "next_restart": 0.0}

    if ANPR_ENABLED:
        p, started = spawn(run_anpr, "ANPR-EasyOCR")
        procs["ANPR-EasyOCR"] = {"fn": run_anpr, "proc": p, "started": started, "restarts": 0, "next_restart": 0.0}
    if FACE_ENABLED:
        p, started = spawn(run_face, "FaceEmbeds")
        procs["FaceEmbeds"] = {"fn": run_face, "proc": p, "started": started, "restarts": 0, "next_restart": 0.0}
    if BEHAVIOR_ENABLED:
        p, started = spawn(run_behavior, "BehaviorAI")
        procs["BehaviorAI"] = {"fn": run_behavior, "proc": p, "started": started, "restarts": 0, "next_restart": 0.0}

    publish("supervisor", "RUNNING", os.getpid(), 0, time.time())

    while True:
        now = time.time()
        heartbeat("supervisor", os.getpid(), 0, now)
        for name, state in list(procs.items()):
            p = state["proc"]
            if p.is_alive():
                heartbeat(name, p.pid, state["restarts"], state["started"])
                continue

            exit_code = p.exitcode
            state["restarts"] += 1
            delay = min(RESTART_MAX_DELAY, RESTART_BASE_DELAY * (2 ** min(state["restarts"] - 1, 5)))
            if now < state["next_restart"]:
                publish(name, "BACKOFF", p.pid, state["restarts"], state["started"], exit_code)
                continue

            log.warning("%s died (exit %s). Restarting in %.1fs …", name, exit_code, delay)
            publish(name, "RESTARTING", p.pid, state["restarts"], state["started"], exit_code)
            time.sleep(delay)
            new_proc, started = spawn(state["fn"], name)
            state["proc"] = new_proc
            state["started"] = started
            state["next_restart"] = time.time() + delay
            publish(name, "RUNNING", new_proc.pid, state["restarts"], started)

        time.sleep(SUPERVISOR_INTERVAL)


if __name__ == "__main__":
    main()
