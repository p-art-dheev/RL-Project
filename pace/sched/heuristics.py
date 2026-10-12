"""Online, task-level heuristic baselines. All see only estimates via `Ctx`."""
from __future__ import annotations

import numpy as np

from ..config import CLOUD, FOG
from ..views import Ctx, carbon_est, est_finish


class Scheduler:
    name = "base"

    def decide(self, ctx: Ctx) -> int:
        raise NotImplementedError

    def attach(self, sim) -> None:  # called once per episode by the simulator / orchestrator
        pass


def _allowed(ctx):
    return [k for k, n in enumerate(ctx.nodes) if n.allowed]


def _eft(ctx, ks):
    return min(ks, key=lambda k: est_finish(ctx, ctx.nodes[k]))


class RandomS(Scheduler):
    name = "Random"

    def __init__(self, seed=0):
        self.rng = np.random.default_rng(seed)

    def decide(self, ctx):
        ks = _allowed(ctx)
        return int(ks[self.rng.integers(len(ks))])


class LocalFirst(Scheduler):
    """Run on the originating edge device (what a device does with no offloading)."""
    name = "Edge-only"

    def decide(self, ctx):
        ks = _allowed(ctx)
        return next((k for k in ks if ctx.nodes[k].is_origin), _eft(ctx, ks))


class TierOnly(Scheduler):
    def __init__(self, tier, name):
        self.tier, self.name = tier, name

    def decide(self, ctx):
        ks = _allowed(ctx)
        sub = [k for k in ks if ctx.nodes[k].tier == self.tier]
        return _eft(ctx, sub or ks)


def CloudOnly():
    return TierOnly(CLOUD, "Cloud-only")


def FogOnly():
    return TierOnly(FOG, "Fog-only")


class EFT(Scheduler):
    """Earliest estimated finish time (online HEFT-style list scheduling)."""
    name = "EFT"

    def decide(self, ctx):
        return _eft(ctx, _allowed(ctx))


class CarbonGreedy(Scheduler):
    """Lowest estimated carbon; ties broken by finish time."""
    name = "Carbon-greedy"

    def decide(self, ctx):
        ks = _allowed(ctx)
        return min(ks, key=lambda k: (round(carbon_est(ctx, ctx.nodes[k]), 9), est_finish(ctx, ctx.nodes[k])))


class CAEFT(Scheduler):
    """Carbon-aware EFT: greenest node whose estimated finish still meets the task's
    latest-finish time; if none can, fall back to EFT. Strongest hand-made baseline."""
    name = "CA-EFT"

    def __init__(self, margin: float = 0.4):  # tuned on training seeds (see experiments)
        self.margin = margin

    def decide(self, ctx):
        ks = _allowed(ctx)
        t = ctx.task
        budget = t.lf - ctx.now
        ok = [k for k in ks if est_finish(ctx, ctx.nodes[k]) - ctx.now <= budget * self.margin]
        if ok:
            return min(ok, key=lambda k: (carbon_est(ctx, ctx.nodes[k]), est_finish(ctx, ctx.nodes[k])))
        return _eft(ctx, ks)


class JobEFT(Scheduler):
    """Job-level EFT (MERSEM's granularity, greedy): the job's first placed task picks the
    EFT node and every other task of the job follows it. Control for granularity effects."""
    name = "Job-EFT"

    def attach(self, sim):
        self.m = {}

    def decide(self, ctx):
        ks = _allowed(ctx)
        if ctx.task.pinned:
            return next(k for k in ks if ctx.nodes[k].is_origin)
        tgt = self.m.get(ctx.task.job_id)
        for k in ks:
            if ctx.nodes[k].idx == tgt:
                return k
        k = _eft(ctx, ks)
        self.m[ctx.task.job_id] = ctx.nodes[k].idx
        return k


def all_heuristics():
    return [RandomS(), LocalFirst(), FogOnly(), CloudOnly(), EFT(), CarbonGreedy(), CAEFT()]
