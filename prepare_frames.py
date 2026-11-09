import cv2, csv, argparse
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument("--video", required=True)
p.add_argument("--actions", required=True)
p.add_argument("--out", default="dataset")
a=p.parse_args()
out=Path(a.out); out.mkdir(parents=True, exist_ok=True)
rows=list(csv.DictReader(open(a.actions, newline="", encoding="utf-8")))
cap=cv2.VideoCapture(a.video)
fps=cap.get(cv2.CAP_PROP_FPS) or 30
i=0
while True:
    ok, frame=cap.read()
    if not ok: break
    # Save a low-rate frame sample; precise synchronization requires event timestamps
    if i % max(1, round(fps/5)) == 0:
        cv2.imwrite(str(out/f"frame_{i:08d}.jpg"), cv2.resize(frame,(320,180)))
    i+=1
cap.release()
print(f"Extracted sampled frames to {out}. Align event timestamps before training.")
