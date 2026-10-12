"""Deployable PACE scheduler (inference only) with the online SLA-target controller."""
from __future__ import annotations

import time
from collections import deque

import numpy as np
import torch

from ..sched.heuristics import Scheduler
from ..views import DEFER, Ctx, est_finish
from .features import K_MAX, featurize
from .model import PACENet


def load_net(path: str) -> PACENet:
    net = PACENet()
    net.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
    net.eval()
    return net


class PACE(Scheduler):
    """w = weight on SLA (MERSEM's w_s); 1 - w on carbon.

    If `sla_target` is set, a PI controller adapts w online so the observed class A/B
    violation rate tracks the target (dual-ascent analogue of a Lagrange multiplier).
    """

    def __init__(self, net: PACENet | str, w: float = 0.5, sla_target: float | None = None, kp: float = 0.8,
                 ki: float = 0.08, window: int = 50, job_level: bool = False, shield: bool = False,
                 label: str | None = None):
        self.net = load_net(net) if isinstance(net, str) else net
        self.w0 = w
        self.w = w
        self.target = sla_target
        self.kp, self.ki, self.window = kp, ki, window
        self.job_level = job_level
        self.shield = shield
        self.name = label or ((f"PACE(target={sla_target:.0%})" if sla_target is not None else f"PACE(w={w})")
                              + ("+shield" if shield else ""))
        self._xn = np.zeros((1, K_MAX, 18), np.float32)
        self._xt = np.zeros((1, 18), np.float32)
        self._m = np.zeros((1, K_MAX + 1), np.bool_)
        self.decide_s = 0.0
        self.n_dec = 0
        self.w_trace: list = []

    def attach(self, sim) -> None:
        self.w = self.w0
        self.integral = 0.0
        self.recent: deque = deque(maxlen=self.window)
        self.since = 0
        self.jobmap: dict = {}
        self.w_trace = []
        if hasattr(sim, "listeners"):
            sim.listeners.append(self.on_job_done)

    def on_job_done(self, rec: dict) -> None:
        if self.target is None or rec["cls"] == 2:
            return
        self.recent.append(float(rec["miss"]))
        self.since += 1
        if self.since >= 10 and len(self.recent) >= 10:
            self.since = 0
            e = float(np.mean(self.recent)) - self.target
            self.integral = float(np.clip(self.integral + e, -5, 5))
            self.w = float(np.clip(self.w0 + self.kp * e + self.ki * self.integral, 0.0, 1.0))
            self.w_trace.append((rec["finish"], self.w, float(np.mean(self.recent))))

    @torch.no_grad()
    def decide(self, ctx: Ctx) -> int:
        t0 = time.perf_counter()
        if self.job_level and not ctx.task.pinned:
            tgt = self.jobmap.get(ctx.task.job_id)
            for k, n in enumerate(ctx.nodes):
                if n.idx == tgt and n.allowed:
                    return k
        featurize(ctx, self.w, self._xn[0], self._xt[0], self._m[0])
        if self.shield:
            self._apply_shield(ctx)
        logits, _ = self.net(torch.from_numpy(self._xn), torch.from_numpy(self._xt), torch.from_numpy(self._m))
        a = int(torch.argmax(logits[0]))
        self.decide_s += time.perf_counter() - t0
        self.n_dec += 1
        if a == K_MAX:
            return DEFER
        if self.job_level and not ctx.task.pinned:
            self.jobmap[ctx.task.job_id] = ctx.nodes[a].idx
        return a

    def _apply_shield(self, ctx: Ctx) -> None:
        """Safety shield: drop nodes whose estimated finish misses the task's sub-deadline
        with a w-dependent margin (w=1 -> 0.4 x budget, w=0 -> 1.0 x budget). If no node is
        safe the shield abstains. The policy still chooses among the remaining nodes."""
        budget = ctx.task.lf - ctx.now
        margin = 1.0 - 0.6 * self.w
        safe = [k for k, n in enumerate(ctx.nodes)
                if n.allowed and est_finish(ctx, n) - ctx.now <= margin * budget]
        if safe:
            m = self._m[0]
            for k in range(len(ctx.nodes)):
                if k not in safe:
                    m[k] = False
