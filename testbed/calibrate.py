"""Measure the real testbed and write the numbers into testbed/nodes.json.

  * per-node speed for each task type (generic BLAS kernel, HOG vision), in work units per second
  * per-node slowdown when every core is busy (SMT threads share a physical core)
  * laptop -> region RTT and bandwidth, Mumbai <-> Stockholm RTT and bandwidth
The same file then parameterises the simulator's "testbed mirror" (sim-to-real check).

  python -m testbed.calibrate
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DETECT_WORK = 0.30  # reference-core seconds assumed for the detect task in the workload model


def _req(url, token, data=None, timeout=60):
    r = urllib.request.Request(url, data=data, headers={"X-Token": token})
    t0 = time.perf_counter()
    body = urllib.request.urlopen(r, timeout=timeout).read()
    return time.perf_counter() - t0, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", default=str(ROOT / "nodes.json"))
    p = Path(ap.parse_args().nodes)
    cfg = json.loads(p.read_text())
    tok = cfg["token"]
    cal = {}
    for n in cfg["nodes"]:
        _req(n["url"] + "/calibrate?reps=2", tok, timeout=180)  # warm-up: worker processes load numpy / OpenCV
        _t, body = _req(n["url"] + "/calibrate?reps=3", tok, timeout=180)
        cal[n["name"]] = json.loads(body)
        print(n["name"], cal[n["name"]])
    # slowdown with every core busy (2 vCPUs of an x86 instance are one physical core with 2 SMT threads)
    for n in cfg["nodes"]:
        if n["cores"] < 2:
            continue
        with ThreadPoolExecutor(n["cores"]) as ex:
            loaded = list(ex.map(lambda _i: json.loads(_req(n["url"] + "/calibrate?reps=2", tok, timeout=180)[1]),
                                 range(n["cores"])))
        busy = statistics.mean(c["generic_s_per_unit"] for c in loaded)
        n["contention"] = round(max(0.0, busy / cal[n["name"]]["generic_s_per_unit"] - 1.0), 2)
        print(f"{n['name']}: {n['cores']} tasks at once -> each {1 + n['contention']:.2f}x slower")
    ref = next((n for n in cfg["nodes"] if n["tier"] == 1 and n.get("arch") == "x86"), cfg["nodes"][-1])
    for n in cfg["nodes"]:
        c = cal[n["name"]]
        # absolute speeds: work units per second, so est_exec = work / speed is in real seconds
        n["speed"] = {"generic": round(1.0 / c["generic_s_per_unit"], 3),
                      "vision": round(DETECT_WORK / c["vision_s"], 3)}
    # laptop -> each region
    net = dict(cfg.get("net", {}))
    by_loc = {}
    for n in cfg["nodes"]:
        by_loc.setdefault(n["loc"], n)
    for loc, n in by_loc.items():
        if n["tier"] == 0:
            continue
        rtts = [_req(n["url"] + "/bytes/100", tok)[0] for _ in range(5)]
        down = min(_req(n["url"] + "/bytes/2000000", tok)[0] for _ in range(2))
        up = min(_req(n["url"] + "/echo", tok, data=os.urandom(2_000_000))[0] for _ in range(2))
        rtt = statistics.median(rtts)
        bw = 2_000_000 * 8 / 1e6 / max(1e-3, (up + down) / 2 - rtt)
        net[f"CBE-{loc}"] = [round(rtt, 4), round(bw, 1)]
        print(f"CBE-{loc}: rtt={rtt*1000:.0f} ms bw~{bw:.1f} Mbps")
    if "BOM" in by_loc and "ARN" in by_loc:
        _t, body = _req(by_loc["BOM"]["url"] + "/probe?url=" + by_loc["ARN"]["url"], tok)
        pr = json.loads(body)
        rtt = pr["1000"]
        bw = 2_000_000 * 8 / 1e6 / max(1e-3, pr["2000000"] - rtt)
        net["BOM-ARN"] = [round(rtt, 4), round(bw, 1)]
        print(f"BOM-ARN: rtt={rtt*1000:.0f} ms bw~{bw:.1f} Mbps")
    cfg["net"] = net
    cfg["calibration"] = dict(raw=cal, reference=ref["name"], at=time.strftime("%Y-%m-%d %H:%M:%S"))
    p.write_text(json.dumps(cfg, indent=1))
    print("updated", p)


if __name__ == "__main__":
    main()
