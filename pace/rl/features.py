"""Observation encoding shared by training, simulation and the live testbed."""
from __future__ import annotations

import math

import numpy as np

from ..views import Ctx, carbon_est, est_exec, est_finish

K_MAX = 12  # max candidate nodes (origin edge + servers); extra slot K_MAX = DEFER
F_N = 18
F_T = 18


def featurize(ctx: Ctx, w: float, out_n: np.ndarray | None = None, out_t: np.ndarray | None = None,
              out_m: np.ndarray | None = None):
    t = ctx.task
    nodes = ctx.nodes
    K = len(nodes)
    assert K <= K_MAX, f"too many candidates ({K} > {K_MAX})"
    xn = out_n if out_n is not None else np.zeros((K_MAX, F_N), np.float32)
    xt = out_t if out_t is not None else np.zeros(F_T, np.float32)
    m = out_m if out_m is not None else np.zeros(K_MAX + 1, np.bool_)
    xn[:] = 0.0
    m[:] = False
    budget = max(t.lf - ctx.now, 0.05)
    c_task = max(ctx.c_ref / max(t.n_tasks, 1), 1e-12)
    for k, n in enumerate(nodes):
        ex = est_exec(t, n)
        ef = est_finish(ctx, n) - ctx.now
        row = xn[k]
        row[n.tier] = 1.0
        row[3] = float(n.is_origin)
        row[4] = n.speed
        row[5] = min(n.est_transfer / budget, 5.0)
        row[6] = min(n.est_wait / budget, 5.0)
        row[7] = min(ex / budget, 5.0)
        row[8] = min(ef / budget, 5.0)
        row[9] = math.log1p(ef)
        row[10] = n.ci / 1000.0
        row[11] = (n.ci_f1 - n.ci) / 1000.0
        row[12] = (n.ci_f3 - n.ci) / 1000.0
        row[13] = math.log1p(carbon_est(ctx, n) / c_task)
        row[14] = n.running / n.cores
        row[15] = min(n.queued / (4.0 * n.cores), 2.0)
        row[16] = float(ef <= budget)
        row[17] = float(ef <= 0.4 * budget)
        m[k] = n.allowed
    m[K_MAX] = ctx.can_defer
    xt[:] = 0.0
    xt[t.cls] = 1.0
    xt[3] = math.log1p(t.work_est)
    xt[4] = math.log1p(t.rem_cp)
    xt[5] = math.log1p(budget) / 5.0
    xt[6] = min(budget / (t.work_est + t.rem_cp + 0.01), 20.0) / 10.0
    xt[7] = float(ctx.can_defer)
    xt[8] = t.defer_count / 3.0
    xt[9] = float(t.privacy)
    xt[10] = w
    xt[11] = ctx.sla_recent
    xt[12] = ctx.util
    xt[13] = math.sin(2 * math.pi * ctx.tod / 24)
    xt[14] = math.cos(2 * math.pi * ctx.tod / 24)
    xt[15] = float(t.retry)
    xt[16] = math.log1p(t.n_desc) / 4.0
    xt[17] = float(t.pinned)
    return xn, xt, m
