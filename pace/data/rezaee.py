"""Parser for the Rezaee & Adabi IoT/Fog/Cloud DAG dataset (Zenodo 10.5281/zenodo.4667690, CC-BY-4.0).

This is the dataset used by the MERSEM base paper. It ships as two zips:
  JobDetails.zip  -> JobDetails.json   (UTF-8 with BOM)
  TaskDetails.zip -> TaskDetails.txt   (UTF-16, comma separated)

Pitfalls handled here:
  * TaskDetails is UTF-16 and ~670 MB uncompressed, so it is streamed.
  * The `ListOfResourceNeeds` column contains unquoted commas, so columns are
    misaligned. We read the first six fields from the left and the three bracketed
    lists (successors, non-immediate successors, predecessors) from the right.
  * `*_Real` / `*_Predicted` columns are zero, so the dataset has no ground-truth
    estimation error; the simulator injects it instead.
  * `JobID` repeats across 3 batches; tasks are matched to jobs by position instead.
  * Per-edge data weights are not given, only per-job min/max/sum; we sample per-edge
    weights consistent with those statistics.

Output: a compact .npz with flat arrays + offsets (see `save_npz`).
"""
from __future__ import annotations

import argparse
import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np

_TAIL = re.compile(r"\[([^\]]*)\],\[([^\]]*)\],\[([^\]]*)\]\s*$")


def _ints(s: str) -> list[int]:
    s = s.strip()
    return [int(x) for x in s.split(",")] if s else []


def load_jobs(job_zip: Path) -> list[dict]:
    with zipfile.ZipFile(job_zip) as z:
        with z.open("JobDetails.json") as f:
            return json.load(io.TextIOWrapper(f, encoding="utf-8-sig"))["Jobs"]


def iter_tasks(task_zip: Path):
    """Yield (owner_job_id, task_id, mi, ram, preds) from TaskDetails.txt."""
    with zipfile.ZipFile(task_zip) as z:
        with z.open("TaskDetails.txt") as f:
            text = io.TextIOWrapper(f, encoding="utf-16")
            next(text)  # header
            for line in text:
                m = _TAIL.search(line)
                if not m:
                    continue
                head = line.split(",", 6)
                yield int(head[2]), int(head[1]), float(head[3]), float(head[4]), _ints(m.group(3))


def build(job_zip: Path, task_zip: Path, sample: int | None, seed: int = 0) -> dict:
    """Parse all jobs, keep a uniform random sample of `sample` jobs (in submission order).

    `JobID` is NOT unique (the file holds 3 simulation batches that reuse IDs), but the
    task file is positionally aligned with the job file: job k owns the next
    `CountOfTasks` task rows. We verified this for all 51,895 jobs. The file is also
    ordered so that early jobs are much larger than average, so we sample uniformly
    instead of taking a prefix.
    """
    rng = np.random.default_rng(seed)
    jobs = load_jobs(job_zip)
    keep = set(range(len(jobs)))
    if sample and sample < len(jobs):
        keep = set(rng.choice(len(jobs), size=sample, replace=False).tolist())
    it = iter_tasks(task_zip)
    picked = []
    for k, j in enumerate(jobs):
        rows = [next(it) for _ in range(int(j["CountOfTasks"]))]
        assert all(r[0] == int(j["JobID"]) for r in rows), f"misaligned at job index {k}"
        if k in keep:
            picked.append((j, [(tid, mi, ram, preds) for _o, tid, mi, ram, preds in rows]))
    picked.sort(key=lambda p: float(p[0]["TimeSubmission"]))
    out = dict(job_offset=[0], edge_offset=[0], mi=[], ram=[], esrc=[], edst=[], emb=[],
               submit=[], deadline=[], cp_cloud=[], cp_fog=[], source_type=[])
    skipped = 0
    for j, rows in picked:
        local = {tid: i for i, (tid, *_r) in enumerate(rows)}
        edges = [(local[p], local[tid]) for tid, _mi, _ram, preds in rows for p in preds if p in local]
        if not _is_dag(len(rows), edges):
            skipped += 1
            continue
        lo, hi = float(j["MinEdgeWeight"]), float(j["MaxEdgeWeight"])
        mean = float(j["SumOfEdgeWeight"]) / max(1, int(j["CountOfEdges"]))
        w = np.clip(rng.uniform(0.5, 1.5, len(edges)) * mean, lo, hi) if edges else np.zeros(0)
        for _tid, mi, ram, _p in rows:
            out["mi"].append(mi)
            out["ram"].append(ram)
        for (s, d), wt in zip(edges, w):
            out["esrc"].append(s)
            out["edst"].append(d)
            out["emb"].append(wt * 0.1)  # dataset weight units -> MB (assumption, documented)
        out["job_offset"].append(len(out["mi"]))
        out["edge_offset"].append(len(out["esrc"]))
        out["submit"].append(float(j["TimeSubmission"]))
        out["deadline"].append(float(j["TimeDeadlineFinal"]))
        out["cp_cloud"].append(float(j["MinTimeForExecuteDagWithMaxParallelismOnCloud"]))
        out["cp_fog"].append(float(j["MinTimeForExecuteDagWithMaxParallelismOnFog"]))
        out["source_type"].append(int(j["JobInitSourceTypeID"]))
    arr = {k: np.asarray(v) for k, v in out.items()}
    arr["mi"] = arr["mi"].astype(np.float32)
    arr["ram"] = arr["ram"].astype(np.float32)
    arr["emb"] = arr["emb"].astype(np.float32)
    arr["esrc"] = arr["esrc"].astype(np.int16)
    arr["edst"] = arr["edst"].astype(np.int16)
    print(f"jobs kept={len(arr['submit'])} skipped={skipped} tasks={len(arr['mi'])} edges={len(arr['esrc'])}")
    return arr


def _is_dag(n: int, edges: list[tuple[int, int]]) -> bool:
    indeg = [0] * n
    adj: list[list[int]] = [[] for _ in range(n)]
    for s, d in edges:
        adj[s].append(d)
        indeg[d] += 1
    stack = [i for i in range(n) if indeg[i] == 0]
    seen = 0
    while stack:
        u = stack.pop()
        seen += 1
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                stack.append(v)
    return seen == n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default="data/processed/rezaee_dags.npz")
    ap.add_argument("--sample", type=int, default=12000)
    a = ap.parse_args()
    arr = build(Path(a.raw) / "JobDetails.zip", Path(a.raw) / "TaskDetails.zip", a.sample)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(a.out, **arr)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
