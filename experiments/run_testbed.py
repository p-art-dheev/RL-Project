"""E8: real-testbed comparison. Runs schedulers back-to-back on the same AWS nodes,
interleaved (ABCDE ABCDE ...) so drifting network conditions do not favour any method.
Each (seed) replays the identical job trace and carbon trace for every scheduler.

  python -m experiments.run_testbed --minutes 6 --seeds 3
  python -m experiments.run_testbed --rate-bc 0.15 --out-dir results/testbed/busy      # 2x analytics load
  python -m experiments.run_testbed --methods pace-shield,mersem,ca-eft --minutes 5 --seeds 2
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", default="testbed/nodes.json")
    ap.add_argument("--methods", default="pace-shield,pace,mersem,ca-eft,eft")
    ap.add_argument("--minutes", type=float, default=6)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--drain", type=float, default=90)
    ap.add_argument("--w", type=float, default=0.9, help="PACE SLA weight")
    ap.add_argument("--rate-bc", type=float, default=0.075, help="analytics/batch job rate (orchestrator --rate-bc)")
    ap.add_argument("--out-dir", default="results/testbed")
    ap.add_argument("--extra", default="", help="extra args passed to the orchestrator")
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    methods = a.methods.split(",")
    total = len(methods) * a.seeds
    k = 0
    for seed in range(1, a.seeds + 1):
        for m in methods:
            k += 1
            path = out / f"e8_{m}_s{seed}.json"
            if path.exists():
                print(f"[{k}/{total}] skip {path} (exists)")
                continue
            print(f"[{k}/{total}] {m} seed={seed} ...", flush=True)
            cmd = [sys.executable, "-m", "testbed.orchestrator", "--nodes", a.nodes, "--scheduler", m,
                   "--minutes", str(a.minutes), "--drain", str(a.drain), "--seed", str(seed), "--port", "0",
                   "--w", str(a.w), "--rate-bc", str(a.rate_bc), "--out", str(path)] + a.extra.split()
            t0 = time.time()
            subprocess.run(cmd, check=False)
            print(f"   done in {time.time() - t0:.0f}s", flush=True)
            time.sleep(5)
    summarize(out, methods, a.rate_bc)


def summarize(out: Path, methods, rate_bc: float = 0.075):
    rows = {}
    for p in sorted(out.glob("e8_*.json")):
        d = json.loads(p.read_text())
        rows.setdefault(d["args"]["scheduler"], []).append(d["summary"] | {"decide_ms": d.get("decide_ms", 0)})
    lines = ["| Scheduler | runs | jobs | SLA A % | SLA B % | SLA A+B % | carbon dyn (g) | p95 alert (s) | edge/fog/cloud work % | decision ms |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for m in methods:
        rs = rows.get(m, [])
        if not rs:
            continue
        f = lambda k, s=1: f"{np.mean([r[k] for r in rs]) * s:.2f}"
        sh = "/".join(f"{np.mean([r[k] for r in rs]) * 100:.0f}" for k in ("share_edge", "share_fog", "share_cloud"))
        lines.append(f"| {m} | {len(rs)} | {f('jobs')} | {f('sla_A', 100)} | {f('sla_B', 100)} | {f('sla_AB', 100)} | "
                     f"{np.mean([r['carbon_dyn'] for r in rs]):.4f} | {f('p95_A')} | {sh} | {f('decide_ms')} |")
    text = (f"# E8 — real AWS testbed (Coimbatore edge, Mumbai fog, Stockholm cloud), rate_bc={rate_bc}\n\n"
            + "\n".join(lines) + "\n")
    (out / "E8_SUMMARY.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
