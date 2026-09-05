#!/usr/bin/env python3
"""Generate eight lightweight deterministic Sentinel demo videos.

The clips are visual demo assets for Test Mode. They are intentionally synthetic
and contain no real government footage. Run from the repository root:
    python test-data/generate_demo_videos.py
"""
from pathlib import Path
import math
try:
    import cv2
    import numpy as np
except ImportError as exc:
    raise SystemExit("Install OpenCV and NumPy first: pip install opencv-python numpy") from exc

OUT=Path(__file__).resolve().parent/"videos"
W,H,FPS,SECONDS=960,540,15,30
PLATES=["GJ01AB1234","GJ05CD5678"]

def write(name, mode):
    path=OUT/name
    out=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*"mp4v"),FPS,(W,H))
    for frame in range(FPS*SECONDS):
        t=frame/FPS
        img=np.zeros((H,W,3),dtype=np.uint8); img[:]=((24,24,24))
        # scene-specific background
        if mode==3:
            for y in range(100,H,70): cv2.line(img,(0,y),(W,y),(55,55,55),1)
        elif mode==7:
            img[:]=((10,10,10))
        else:
            for y in range(0,H,90): cv2.line(img,(0,y),(W,y),(42,42,42),1)
        cv2.putText(img,name.replace(".mp4",""),(25,42),cv2.FONT_HERSHEY_SIMPLEX,.8,(230,230,230),2)
        if mode in (1,2,4,7):
            x=int(90+(W-260)*((t%6)/6)); y=300 if mode!=7 else 325
            cv2.rectangle(img,(x,y,x+220,y+85),(55,55,55),-1); cv2.rectangle(img,(x+55,y+58,x+185,y+78),(235,235,235),-1)
            plate=PLATES[0] if mode!=4 else PLATES[1]
            cv2.putText(img,plate,(x+60,y+74),cv2.FONT_HERSHEY_SIMPLEX,.48,(15,15,15),1)
        people=range(10) if mode in (3,5,8) else range(2)
        for k in people:
            x=int((80+k*80+(frame*(2+k%3)))% (W-80)); y=180+(k%5)*55
            if mode==3 and t>18: x=int((x+70*(t-18))%(W-60))
            cv2.circle(img,(x,y-22),10,(170,170,170),-1); cv2.line(img,(x,y-10),(x,y+28),(170,170,170),4)
        out.write(img)
    out.release()

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    specs=[
      ("cam01_highway_entry.mp4",1),("cam02_highway_exit.mp4",2),("cam03_market_crowd.mp4",3),
      ("cam04_intersection.mp4",4),("cam05_parking.mp4",5),("cam06_junction.mp4",6),
      ("cam07_night_sim.mp4",7),("cam08_pedestrian.mp4",8)]
    for name,mode in specs: write(name,mode)
    print(f"Generated {len(specs)} clips in {OUT}")
if __name__=="__main__": main()
