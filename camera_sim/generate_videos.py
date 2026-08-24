#!/usr/bin/env python3
"""Generate synthetic CCTV test videos for mediamtx simulation."""
import cv2
import numpy as np
import os
import random
import math

OUTPUT_DIR = "/videos"
os.makedirs(OUTPUT_DIR, exist_ok=True)

W, H, FPS, DURATION = 1280, 720, 25, 300  # 5-minute loops

COLORS = {
    "sky": (200, 220, 255), "road": (80, 80, 90), "sidewalk": (140, 140, 150),
    "building": (160, 150, 140), "car_red": (30, 30, 200), "car_blue": (180, 60, 40),
    "car_white": (220, 220, 220), "car_black": (30, 30, 30), "car_yellow": (20, 200, 230),
    "person_shirt": [(60, 90, 200), (40, 160, 60), (200, 60, 60), (200, 160, 40)],
    "person_pants": [(40, 40, 80), (30, 30, 30), (80, 60, 40)],
}

PLATE_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ"
PLATE_NUMS  = "0123456789"

def random_plate():
    return f"GJ{random.randint(1,33):02d}{random.choice(PLATE_CHARS)}{random.choice(PLATE_CHARS)} {random.randint(1000,9999)}"

class Entity:
    def __init__(self, etype, cam_id):
        self.type   = etype
        self.cam_id = cam_id
        self.reset()

    def reset(self):
        side = random.choice(["left", "right"])
        y_road = random.randint(H // 2 + 40, H - 80)
        if self.type == "vehicle":
            self.w, self.h = random.randint(120, 200), random.randint(55, 90)
            self.color = random.choice([COLORS["car_red"], COLORS["car_blue"],
                                        COLORS["car_white"], COLORS["car_black"],
                                        COLORS["car_yellow"]])
            self.speed = random.uniform(4, 10)
            self.plate = random_plate()
        else:
            self.w, self.h = random.randint(28, 40), random.randint(70, 100)
            self.shirt  = random.choice(COLORS["person_shirt"])
            self.pants  = random.choice(COLORS["person_pants"])
            self.speed  = random.uniform(1.2, 2.5)

        if side == "left":
            self.x, self.dir = -self.w - 10, 1
        else:
            self.x, self.dir = W + 10, -1
        self.y = y_road - self.h

    def move(self):
        self.x += self.speed * self.dir
        done = (self.dir == 1 and self.x > W + 20) or (self.dir == -1 and self.x < -self.w - 20)
        if done:
            self.reset()

    def draw(self, frame):
        x, y, w, h = int(self.x), int(self.y), self.w, self.h
        if x + w < 0 or x > W:
            return
        if self.type == "vehicle":
            cv2.rectangle(frame, (x, y), (x + w, y + h), self.color, -1)
            cv2.rectangle(frame, (x + 8, y + 6), (x + w - 8, y + h // 2), (120, 200, 230), -1)
            # wheels
            for wx in [x + 20, x + w - 25]:
                cv2.circle(frame, (wx, y + h - 4), 12, (20, 20, 20), -1)
                cv2.circle(frame, (wx, y + h - 4), 6,  (80, 80, 80), -1)
            # plate
            px, py, pw, ph = x + w // 4, y + h - 20, 60, 16
            cv2.rectangle(frame, (px, py), (px + pw, py + ph), (250, 250, 200), -1)
            cv2.rectangle(frame, (px, py), (px + pw, py + ph), (0, 0, 0), 1)
            cv2.putText(frame, self.plate[:8], (px + 2, py + 11),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.28, (0, 0, 0), 1, cv2.LINE_AA)
        else:
            # torso
            cv2.rectangle(frame, (x, y), (x + w, y + h * 2 // 3), self.shirt, -1)
            # legs
            cv2.rectangle(frame, (x, y + h * 2 // 3), (x + w, y + h), self.pants, -1)
            # head
            cx = x + w // 2
            cv2.circle(frame, (cx, y - h // 6), h // 7, (180, 140, 110), -1)


def draw_background(frame, cam_id):
    """Draw a static street scene background."""
    frame[:] = COLORS["sky"]
    # Buildings
    for i, bw in enumerate([200, 180, 220, 160, 190, 170]):
        bh  = random.randint(120, 280) if cam_id != i % 5 else 200
        bx  = i * (W // 5)
        by  = H // 2 - bh
        col = tuple(max(0, c + random.randint(-20, 20)) for c in COLORS["building"])
        cv2.rectangle(frame, (bx, by), (bx + bw, H // 2), col, -1)
        # windows
        for wy in range(by + 10, H // 2 - 10, 30):
            for wx in range(bx + 10, bx + bw - 10, 25):
                lit = random.random() > 0.3
                wc  = (255, 255, 180) if lit else (60, 60, 80)
                cv2.rectangle(frame, (wx, wy), (wx + 14, wy + 18), wc, -1)
    # Road
    cv2.rectangle(frame, (0, H // 2), (W, H), COLORS["road"], -1)
    # Road markings
    for x in range(0, W, 80):
        cv2.rectangle(frame, (x, H * 3 // 4 - 3), (x + 40, H * 3 // 4 + 3), (200, 200, 50), -1)
    # Sidewalk
    cv2.rectangle(frame, (0, H // 2), (W, H // 2 + 35), COLORS["sidewalk"], -1)
    # Timestamp area
    cv2.rectangle(frame, (0, 0), (340, 28), (0, 0, 0), -1)


def add_overlay(frame, cam_id, frame_no):
    """Add camera overlay: ID, timestamp, frame counter."""
    import time
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(frame, f"CAM-0{cam_id}  {ts}  F:{frame_no:06d}",
                (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 255, 200), 1, cv2.LINE_AA)
    cv2.rectangle(frame, (W - 80, 0), (W, 26), (0, 0, 0), -1)
    cv2.putText(frame, "● REC", (W - 74, 18), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (0, 0, 255) if (frame_no // 15) % 2 == 0 else (60, 60, 60), 1)


def generate_video(cam_id, seed=None):
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    path = os.path.join(OUTPUT_DIR, f"cam{cam_id}.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out    = cv2.VideoWriter(path, fourcc, FPS, (W, H))

    # spawn entities
    n_vehicles = random.randint(3, 6)
    n_persons  = random.randint(2, 5)
    entities   = [Entity("vehicle", cam_id) for _ in range(n_vehicles)] + \
                 [Entity("person", cam_id)  for _ in range(n_persons)]

    # stagger starting positions
    for i, e in enumerate(entities):
        e.x = random.uniform(-200, W + 200)

    bg = np.zeros((H, W, 3), dtype=np.uint8)
    draw_background(bg, cam_id)

    total = FPS * DURATION
    for f in range(total):
        frame = bg.copy()
        # add subtle noise for realism
        noise = np.random.randint(0, 8, frame.shape, dtype=np.uint8)
        frame = cv2.add(frame, noise)

        # sort by y so closer objects draw on top
        entities.sort(key=lambda e: e.y)
        for ent in entities:
            ent.move()
            ent.draw(frame)

        add_overlay(frame, cam_id, f)
        out.write(frame)

        if f % (FPS * 30) == 0:
            pct = int(f / total * 100)
            print(f"  cam{cam_id}: {pct}%", flush=True)

    out.release()
    print(f"  cam{cam_id}: done → {path}")


if __name__ == "__main__":
    print("Generating synthetic CCTV videos …")
    for cid in range(1, 6):
        generate_video(cid, seed=cid * 42)
    print("All videos ready.")
