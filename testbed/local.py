"""Start testbed workers on this machine (Windows / Linux / macOS).

  python -m testbed.local --edges 2                 # edge workers for the real AWS testbed
  python -m testbed.local --edges 2 --servers 4     # fully local rehearsal (no AWS), writes nodes.local.json

Edge workers emulate a Raspberry-Pi-class camera box: 1 core, work inflated x3.
Stop with Ctrl+C (all workers are terminated).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def spawn(port: int, name: str, cores: int, slowdown: float, token: str) -> subprocess.Popen:
    env = {**os.environ, "PACE_TOKEN": token, "PACE_NAME": name, "PACE_CORES": str(cores),
           "PACE_SLOWDOWN": str(slowdown)}
    return subprocess.Popen([sys.executable, str(ROOT / "worker.py"), "--port", str(port)], env=env)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edges", type=int, default=2)
    ap.add_argument("--servers", type=int, default=0, help="also emulate fog/cloud servers locally")
    ap.add_argument("--slowdown", type=float, default=3.0)
    ap.add_argument("--token", default=None, help="defaults to the token in the nodes file")
    ap.add_argument("--pool", default="a", help="'b' = edge workers for the second (A/B) pool, ports 8110+")
    a = ap.parse_args()
    token = a.token
    nodes_file = ROOT / ("nodes.json" if a.pool == "a" else f"nodes_{a.pool}.json")
    if token is None:
        token = json.loads(nodes_file.read_text())["token"] if nodes_file.exists() and not a.servers else "local-demo"
    base = 8100 if a.pool == "a" else 8110
    procs = [spawn(base + i, f"edge{i}", 1, a.slowdown, token) for i in range(a.edges)]
    if a.servers:
        nodes = [dict(name=f"edge{i}", tier=0, loc="CBE", zone="IN-SO", cores=1, url=f"http://127.0.0.1:{8100 + i}",
                      speed={"generic": 0.3, "vision": 0.3}, idle_w=2.0, max_w=6.0, pue=1.0, mem_gb=2.0)
                 for i in range(a.edges)]
        layout = [("bom-x86", 1, "BOM", "IN-WE", "x86"), ("bom-arm", 1, "BOM", "IN-WE", "arm"),
                  ("arn-x86", 2, "ARN", "SE-SE3", "x86"), ("arn-arm", 2, "ARN", "SE-SE3", "arm")]
        for i in range(a.servers):
            name, tier, loc, zone, arch = layout[i % 4]
            name = name if i < 4 else f"{name}{i // 4}"
            procs.append(spawn(8001 + i, name, 2, 1.0, token))
            lo, hi = (0.74, 3.5) if arch == "x86" else (0.47, 1.69)
            nodes.append(dict(name=name, tier=tier, loc=loc, zone=zone, cores=2, arch=arch,
                              url=f"http://127.0.0.1:{8001 + i}",
                              speed={"generic": 1.0, "vision": 1.0} if arch == "x86" else {"generic": 0.85, "vision": 0.6},
                              idle_w=2 * lo, max_w=2 * hi, pue=1.135, mem_gb=4.0))
        cfg = dict(token=token, nodes=nodes, country={"CBE": "IN", "BOM": "IN", "ARN": "SE"},
                   net={"CBE-BOM": [0.035, 20.0], "CBE-ARN": [0.16, 15.0], "BOM-ARN": [0.12, 200.0]})
        (ROOT / "nodes.local.json").write_text(json.dumps(cfg, indent=1))
        print("wrote", ROOT / "nodes.local.json", "(local rehearsal: network delays are NOT real here)")
    print(f"started {len(procs)} workers; Ctrl+C to stop", flush=True)
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
