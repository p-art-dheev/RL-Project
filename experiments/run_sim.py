"""Simulation experiments E1-E7 (see docs/PROPOSAL.md §11). Results -> results/sim/*.csv

  python -m experiments.run_sim --exp all --seeds 10 --procs 4

Every (scenario, seed) pair uses the identical workload and carbon trace for all
methods (paired comparison). Only the test split of the dataset is used.
"""
from __future__ import annotations

import argparse
import csv
import json
import multiprocessing as mp
import os
import time
from pathlib import Path

import numpy as np

from pace.config import Workload, city_topology, testbed_topology
from pace.sched import heuristics as H
from pace.sched.mersem import MERSEM
from pace.sim.core import Simulator

OUT = Path("results/sim")
MODEL = "models/pace.pt"


def methods(names):
    from pace.rl.agent import PACE
    table = {
        "Random": lambda: H.RandomS(), "Edge-only": lambda: H.LocalFirst(), "Fog-only": lambda: H.FogOnly(),
        "Cloud-only": lambda: H.CloudOnly(), "EFT": lambda: H.EFT(), "Carbon-greedy": lambda: H.CarbonGreedy(),
        "CA-EFT": lambda: H.CAEFT(), "Job-EFT": lambda: H.JobEFT(),
        "MERSEM-SLA": lambda: MERSEM(1.0), "MERSEM-Balanced": lambda: MERSEM(0.5), "MERSEM-Carbon": lambda: MERSEM(0.0),
        "MERSEM-Balanced-Oracle": lambda: MERSEM(0.5, oracle=True),
        "PACE(w=0.25)": lambda: PACE(MODEL, w=0.25), "PACE(w=0.5)": lambda: PACE(MODEL, w=0.5),
        "PACE(w=0.75)": lambda: PACE(MODEL, w=0.75), "PACE(w=0.9)": lambda: PACE(MODEL, w=0.9),
        "PACE(w=1.0)": lambda: PACE(MODEL, w=1.0), "PACE(w=0.0)": lambda: PACE(MODEL, w=0.0),
        "PACE-target2%": lambda: PACE(MODEL, w=0.5, sla_target=0.02, label="PACE-target2%"),
        "PACE-target5%": lambda: PACE(MODEL, w=0.5, sla_target=0.05, label="PACE-target5%"),
        "PACE-joblevel": lambda: PACE(MODEL, w=0.5, job_level=True, label="PACE-joblevel(w=0.5)"),
    }
    return {n: table[n] for n in names}


CORE = ["Random", "Edge-only", "Fog-only", "Cloud-only", "EFT", "Carbon-greedy", "CA-EFT", "Job-EFT",
        "MERSEM-SLA", "MERSEM-Balanced", "MERSEM-Carbon", "MERSEM-Balanced-Oracle",
        "PACE(w=0.0)", "PACE(w=0.25)", "PACE(w=0.5)", "PACE(w=0.75)", "PACE(w=0.9)", "PACE(w=1.0)",
        "PACE-target2%", "PACE-target5%", "PACE-joblevel"]
KEY = ["EFT", "CA-EFT", "MERSEM-Balanced", "MERSEM-SLA", "PACE(w=0.5)", "PACE(w=0.75)", "PACE-target5%"]


def scenarios(exp: str):
    """Yield (experiment, scenario label, topology factory name, workload kwargs, method list)."""
    base = dict(split="test", horizon=3600.0, rate_a=0.25, rate_bc=0.015, est_noise=0.2)
    if exp in ("E1", "all"):
        yield "E1", "testbed nominal", "testbed", base, CORE
        yield "E1", "city nominal", "city", {**base, "rate_bc": 0.03}, CORE
    if exp in ("E2", "all"):
        for rb in (0.0075, 0.015, 0.0225, 0.03):
            yield "E2", f"load rate_bc={rb}", "testbed", {**base, "rate_bc": rb}, KEY
    if exp in ("E3", "all"):
        for sg in (0.0, 0.2, 0.4):
            yield "E3", f"estimate noise={sg}", "testbed", {**base, "est_noise": sg}, KEY
    if exp in ("E4", "all"):
        yield "E4", "fog crash + stragglers", "testbed", {**base, "failures": [(1200.0, "bom-c7i", 900.0)],
                                                           "straggle_rate": 1.0}, KEY
        yield "E4", "random failures", "testbed", {**base, "fail_rate": 1.0}, KEY
    if exp in ("E5", "all"):
        yield "E5", "rush hour (x2.5 for 15 min)", "testbed", {**base, "bursts": [(1200.0, 900.0, 2.5)]}, \
            ["CA-EFT", "MERSEM-Balanced", "PACE(w=0.5)", "PACE-target2%", "PACE-target5%"]


def run_one(job):
    exp, label, topo_name, wl_kw, method, seed, carbon, model = job
    global MODEL
    MODEL = model
    import torch
    torch.set_num_threads(1)
    topo = testbed_topology() if topo_name == "testbed" else city_topology()
    wl = Workload(**wl_kw)
    wl.carbon_source = carbon
    wl.start_hour = float((seed * 5) % 24)
    sched = methods([method])[method]()
    sim = Simulator(topo, wl, seed=1000 + seed)
    t0 = time.perf_counter()
    r = sim.run(sched)
    wall = time.perf_counter() - t0
    r.update(exp=exp, scenario=label, method=method, seed=seed, wall_s=wall,
             decide_ms=1000 * getattr(sched, "decide_s", 0.0) / max(1, getattr(sched, "n_dec", 0)) if hasattr(sched, "decide_s") else None,
             plan_s=getattr(sched, "plan_time", None))
    if hasattr(sched, "w_trace") and sched.w_trace:
        r["w_trace"] = json.dumps([(round(a, 1), round(b, 3), round(c, 3)) for a, b, c in sched.w_trace])
    if exp in ("E4", "E5"):  # time series of misses for class A/B by completion time
        bins = np.zeros(int(sim.wl.horizon // 120) + 20)
        tot = np.zeros_like(bins)
        for rec in sim.records:
            if rec["cls"] != 2:
                b = min(len(bins) - 1, int(rec["arrival"] // 120))
                bins[b] += rec["miss"]
                tot[b] += 1
        r["ts_miss"] = json.dumps((bins / np.maximum(tot, 1)).round(4).tolist())
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="all")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--tag", default="")
    ap.add_argument("--carbon", default="synthetic", help='e.g. "data/carbon@2024" (Electricity Maps CSVs)')
    ap.add_argument("--model", default=MODEL)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = []
    for exp, label, topo, wl_kw, ms in scenarios(a.exp):
        n_seeds = a.seeds if exp == "E1" else max(3, a.seeds // 2)
        for m in ms:
            for s in range(n_seeds):
                jobs.append((exp, label, topo, wl_kw, m, s, a.carbon, a.model))
    # slow MERSEM jobs first for better load balance
    jobs.sort(key=lambda j: 0 if j[4].startswith("MERSEM") else 1)
    t0 = time.time()
    rows = []
    with mp.get_context("spawn" if os.name == "nt" else "fork").Pool(a.procs) as pool:
        for i, r in enumerate(pool.imap_unordered(run_one, jobs)):
            rows.append(r)
            if (i + 1) % 25 == 0:
                print(f"{i + 1}/{len(jobs)} done, {time.time() - t0:.0f}s", flush=True)
    keys = sorted({k for r in rows for k in r})
    path = OUT / f"sim_{a.exp}{a.tag}.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print("wrote", path, len(rows), "rows in", round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
