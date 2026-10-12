"""Stream camera frames as class-A (safety alert) jobs to the orchestrator.

  python -m testbed.camera --source 0 --camera edge0 --fps 2                 # laptop webcam
  python -m testbed.camera --source http://PHONE_IP:8080/video --camera edge1  # phone (IP Webcam app)
  python -m testbed.camera --source traffic.mp4 --camera edge0                 # recorded video (repeatable)

Frames are downscaled to 320x240 JPEG (~15 KB) before upload, like a real camera box would.
"""
from __future__ import annotations

import argparse
import time
import urllib.request

import cv2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="0")
    ap.add_argument("--camera", default="edge0")
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--orchestrator", default="http://127.0.0.1:8080")
    ap.add_argument("--private", action="store_true", help="feed may not leave India (data residency)")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    src = int(a.source) if a.source.isdigit() else a.source
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise SystemExit(f"cannot open camera/video {a.source}")
    period = 1.0 / a.fps
    sent = 0
    while True:
        t0 = time.time()
        ok, frame = cap.read()
        if not ok:
            if isinstance(src, str):
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop a video file
                continue
            break
        small = cv2.resize(frame, (320, 240))
        ok, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
        req = urllib.request.Request(a.orchestrator + "/api/frame", data=jpg.tobytes(), method="POST",
                                     headers={"X-Camera": a.camera, "X-Private": "1" if a.private else "0",
                                              "Content-Type": "image/jpeg"})
        try:
            urllib.request.urlopen(req, timeout=5).read()
            sent += 1
        except Exception as e:  # noqa: BLE001
            print("orchestrator not reachable:", e)
        if a.show:
            cv2.imshow(a.camera, small)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        if sent % 20 == 0:
            print(f"{a.camera}: sent {sent} frames ({len(jpg) / 1000:.0f} KB each)")
        time.sleep(max(0.0, period - (time.time() - t0)))


if __name__ == "__main__":
    main()
