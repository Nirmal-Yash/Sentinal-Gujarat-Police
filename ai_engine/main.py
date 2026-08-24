#!/usr/bin/env python3
"""AI Engine — spawns YOLO_WORKERS parallel YOLOv8+DeepSORT processes + ANPR + Face + Behavior."""
import os, time, logging
from multiprocessing import Process

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [AI-ENGINE][%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

YOLO_WORKERS     = int(os.getenv("YOLO_WORKERS",    "4"))
ANPR_ENABLED     = os.getenv("ANPR_ENABLED",    "true").lower() == "true"
FACE_ENABLED     = os.getenv("FACE_ENABLED",    "true").lower() == "true"
BEHAVIOR_ENABLED = os.getenv("BEHAVIOR_ENABLED","true").lower() == "true"


def spawn(target, name):
    p = Process(target=target, name=name, daemon=True)
    p.start()
    log.info(f"Spawned {name} (pid {p.pid})")
    return p


def main():
    log.info("AI Engine starting …")
    time.sleep(6)  # let Redis settle

    from yolo_worker     import run as run_yolo
    from anpr_worker     import run as run_anpr
    from face_worker     import run as run_face
    from behavior_worker import run as run_behavior

    procs = {}

    # Spawn multiple YOLO workers to share the consumer group load across CPUs
    for i in range(YOLO_WORKERS):
        name = f"YOLOv8+DeepSORT-{i+1}"
        procs[name] = (run_yolo, spawn(run_yolo, name))

    if ANPR_ENABLED:
        procs["ANPR-EasyOCR"] = (run_anpr, spawn(run_anpr, "ANPR-EasyOCR"))
    if FACE_ENABLED:
        procs["FaceEmbeds"]   = (run_face, spawn(run_face, "FaceEmbeds"))
    if BEHAVIOR_ENABLED:
        procs["BehaviorAI"]   = (run_behavior, spawn(run_behavior, "BehaviorAI"))

    while True:
        time.sleep(20)
        for name, (fn, p) in list(procs.items()):
            if not p.is_alive():
                log.warning(f"{name} died (exit {p.exitcode}). Restarting …")
                procs[name] = (fn, spawn(fn, name))


if __name__ == "__main__":
    main()
