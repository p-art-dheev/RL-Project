"""Workload generation: smart-city job classes on top of the MERSEM dataset DAGs.

Class A  camera alert: pre (pinned to camera) -> detect -> alert, deadline ~1 s,
         some feeds privacy-restricted (may not leave India).
Class B  graph analytics: a dataset DAG with a tight deadline derived from the
         dataset's own slack ratio.
Class C  batch analytics: a dataset DAG with a loose (30 min - 2 h) deadline; deferrable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from .config import EDGE, Topology, Workload

REF_MIPS = 2.356e6  # dataset's cloud baseline MIPS -> 1 reference-core second
DATA = Path(__file__).resolve().parents[1] / "data" / "processed" / "rezaee_dags.npz"


@dataclass(slots=True)
class TaskSpec:
    work: float
    work_est: float
    typ: str
    mem: float
    pinned: bool


@dataclass
class JobSpec:
    id: int
    cls: int
    origin: str
    arrival: float
    deadline: float
    tasks: list
    edges: list  # (src, dst, MB)
    input_mb: float
    result_mb: float
    privacy: bool
    deferrable: bool
    cp_ref: float = 0.0
    rem_cp: list | None = None  # per-task estimated remaining critical path after the task
    n_desc: list | None = None
    succs: list | None = None
    preds: list | None = None

    def finalize(self) -> "JobSpec":
        n = len(self.tasks)
        self.succs = [[] for _ in range(n)]
        self.preds = [[] for _ in range(n)]
        for s, d, _mb in self.edges:
            self.succs[s].append(d)
            self.preds[d].append(s)
        order = _topo(n, self.succs, self.preds)
        rem = [0.0] * n
        down = [0.0] * n  # longest true-work path from task to sink (incl. itself)
        desc = [0] * n
        for u in reversed(order):
            rem[u] = max((rem[v] + self.tasks[v].work_est for v in self.succs[u]), default=0.0)
            down[u] = self.tasks[u].work + max((down[v] for v in self.succs[u]), default=0.0)
            desc[u] = len(self.succs[u]) + sum(desc[v] for v in self.succs[u])  # upper bound
        self.rem_cp = rem
        self.n_desc = [min(d, n - 1) for d in desc]
        self.cp_ref = max(down) if n else 0.0
        return self


def _topo(n, succs, preds):
    indeg = [len(p) for p in preds]
    st = [i for i in range(n) if indeg[i] == 0]
    out = []
    while st:
        u = st.pop()
        out.append(u)
        for v in succs[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                st.append(v)
    return out


@lru_cache(maxsize=1)
def _dataset():
    d = np.load(DATA)
    return {k: d[k] for k in d.files}


def dataset_job(idx: int):
    d = _dataset()
    a, b = d["job_offset"][idx], d["job_offset"][idx + 1]
    ea, eb = d["edge_offset"][idx], d["edge_offset"][idx + 1]
    ratio = (d["deadline"][idx] - d["submit"][idx]) / max(d["cp_fog"][idx], 1e-6)
    return d["mi"][a:b], d["ram"][a:b], list(zip(d["esrc"][ea:eb].tolist(), d["edst"][ea:eb].tolist(),
                                                     d["emb"][ea:eb].tolist())), float(ratio)


def n_dataset_jobs() -> int:
    return len(_dataset()["submit"])


def diurnal(hour: float) -> float:
    return 1.0 + 0.35 * math.cos(2 * math.pi * (hour - 14.0) / 24.0)


def generate(topo: Topology, wl: Workload, rng: np.random.Generator, start_hour: float) -> list[JobSpec]:
    edges = [n.name for n in topo.nodes if n.tier == EDGE]
    jobs: list[JobSpec] = []
    nd = n_dataset_jobs()
    lo, hi = (0, int(0.7 * nd)) if wl.split == "train" else (int(0.7 * nd), nd)
    ds_i = int(rng.integers(lo, hi))

    def factor(t):
        f = diurnal(start_hour + t / 3600) if wl.diurnal else 1.0
        for (s, dur, m) in wl.bursts:
            if s <= t < s + dur:
                f *= m
        return f

    def poisson_times(rate):
        # thinning for a non-homogeneous Poisson process
        if rate <= 0:  # e.g. alerts come from real cameras instead (orchestrator --camera)
            return []
        fmax = 1.35 * max([1.0] + [m for (_s, _d, m) in wl.bursts])
        t, out = 0.0, []
        while True:
            t += rng.exponential(1.0 / (rate * fmax))
            if t >= wl.horizon:
                return out
            if rng.random() < factor(t) / fmax:
                out.append(t)

    def est(w):
        return w * math.exp(rng.normal(0.0, wl.est_noise)) if wl.est_noise > 0 else w

    for cam in edges:
        private = rng.random() < wl.privacy_a
        for t in poisson_times(wl.rate_a):
            ws = [0.04, 0.30, 0.02]
            ts = [TaskSpec(ws[0], est(ws[0]), "vision", 0.1, True),
                  TaskSpec(ws[1], est(ws[1]), "vision", 0.3, False),
                  TaskSpec(ws[2], est(ws[2]), "generic", 0.05, False)]
            jobs.append(JobSpec(0, 0, cam, t, t + wl.deadline_a, ts, [(0, 1, 0.10), (1, 2, 0.002)],
                                0.0, 0.001, private, False))
    for t in poisson_times(wl.rate_bc):
        mi, ram, e, ratio = dataset_job(ds_i)
        ds_i = lo + (ds_i + 1 - lo) % (hi - lo)
        ts = []
        for m, r in zip(mi.tolist(), ram.tolist()):
            w = m / REF_MIPS * wl.work_scale
            ts.append(TaskSpec(w, est(w), "generic", r / 4000.0, False))
        is_b = rng.random() < wl.frac_b
        ds = wl.data_scale
        e = [(a, b, mb * ds) for a, b, mb in e]
        j = JobSpec(0, 1 if is_b else 2, edges[int(rng.integers(len(edges)))], t, 0.0, ts, e, 1.0 * ds, 0.1 * ds,
                    False, not is_b)
        j.finalize()
        if is_b:
            j.deadline = t + wl.beta_b * float(np.clip(ratio, 0.8, 3.0)) * j.cp_ref + 2.0
        else:
            j.deadline = t + float(rng.uniform(*wl.deadline_c))
        jobs.append(j)
    jobs.sort(key=lambda j: j.arrival)
    for i, j in enumerate(jobs):
        j.id = i
        if j.rem_cp is None:
            j.finalize()
    return jobs
