"""Predict the real-testbed experiment (E8) in the calibrated digital twin, in about a minute.

Run it after `python -m testbed.calibrate` and before spending hours on AWS: it replays the
E8 settings (same workload, seeds and scheduler options as experiments.run_testbed) in the
simulator configured with the measured node speeds, RTTs and bandwidths.

  python -m experiments.twin_check                                  # uses testbed/nodes.json
  python -m experiments.twin_check --nodes testbed/twin.json --model models/pace.pt
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch

from pace.config import Workload
from pace.sim.core import Simulator
from pace.workload import generate
from testbed.orchestrator import DEFAULT_MODEL, load_nodes, make_scheduler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", default="testbed/nodes.json")
    ap.add_argument("--methods", default="pace-shield,pace,mersem,ca-eft,eft")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--minutes", type=float, default=6)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--w", type=float, default=0.9)
    a = ap.parse_args()
    torch.set_num_threads(1)
    print(f"twin: {a.nodes}   PACE model: {a.model}   {a.minutes:g} min x {a.seeds} seeds\n")
    print(f"| Scheduler | SLA A % | SLA B % | SLA A+B % | carbon dyn (g) | p95 alert (s) |\n|---|---|---|---|---|---|")
    for m in a.methods.split(","):
        rs = []
        for seed in range(1, a.seeds + 1):
            opts = argparse.Namespace(scheduler=m, model=a.model, w=a.w, target=None, mersem_w=0.5, epoch=120.0)
            topo, _tok = load_nodes(a.nodes)
            wl = Workload(split="test", horizon=a.minutes * 60, start_hour=10.0, rate_a=0.25, rate_bc=0.075,
                          work_scale=0.2, data_scale=0.2, est_noise=0.2)
            jobs = generate(topo, wl, np.random.default_rng(seed), 10.0)  # same RNG path as the orchestrator
            sim = Simulator(topo, wl, seed=seed, jobs=[j for j in jobs if j.arrival < a.minutes * 60])
            rs.append(sim.run(make_scheduler(opts)))
        f = lambda k, s=100: np.mean([r[k] for r in rs]) * s  # noqa: E731
        print(f"| {m} | {f('sla_A'):.1f} | {f('sla_B'):.1f} | {f('sla_AB'):.1f} | {f('carbon_dyn', 1):.4f} | "
              f"{f('p95_A', 1):.2f} |")
    if not Path(a.model).exists():
        print(f"\n(note: {a.model} not found)")


if __name__ == "__main__":
    main()
