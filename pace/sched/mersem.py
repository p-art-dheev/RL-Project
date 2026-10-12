"""Re-implementation of MERSEM (Ramicetty et al., arXiv:2605.13489, 2026), the base paper.

Faithful to the paper where it is specific:
  * job-level placement: a whole job goes to one node (VM); jobs on a node run
    sequentially (Eq. 3), DAG parallelism limited by the node's cores (Eq. 4/5)
  * epoch-based planning with a workload predictor (we give it the *actual* next-epoch
    arrivals: an oracle predictor, which is generous)
  * objective w_s * SLA_rate + w_c * CO2 (Eq. 14), w_s + w_c = 1
  * hybrid EA: population + crossover/mutation (rate 1.0) + dominance-based replacement
  * RL-guided local search on 30% of the population, 10 episodes, 1 step per episode,
    tabular Q-learning (alpha 0.15, gamma 0.9, eps 0.4 decaying), 5 actions = reassign
    2/5/8/10/15% of jobs, reward 0.7*tanh(f_cur - f_new) + 0.3*r_dom (Eq. 17/18),
    trajectory update with improvement signal I (Eq. 19/20)

Unspecified in the paper (our choices, documented): population 20, generations 30
per epoch, uniform crossover, per-gene mutation 1/J, state bins, CO2 normalised by
the same per-class reference carbon used by every method (so w_s is comparable).
Generosity: the population is seeded with a greedy (EFT) mapping; unplanned or
failed placements fall back to EFT immediately (MERSEM itself has no failure handling).
"""
from __future__ import annotations

import math
import time

import numpy as np

from ..config import EDGE
from ..views import Ctx, est_finish
from .heuristics import Scheduler

ACTIONS = (0.02, 0.05, 0.08, 0.10, 0.15)


class MERSEM(Scheduler):
    def __init__(self, w_s: float = 0.5, oracle: bool = False, epoch: float = 900.0, pop: int = 20,
                 gens: int = 30, ls_frac: float = 0.3, ls_episodes: int = 10, seed: int = 0, label: str | None = None):
        self.w_s, self.oracle, self.epoch = w_s, oracle, epoch
        self.pop_n, self.gens, self.ls_frac, self.ls_eps = pop, gens, ls_frac, ls_episodes
        self.rng = np.random.default_rng(seed)
        self.q: dict = {}
        self.eps = 0.4
        self.plan: dict[int, int] = {}
        self.plan_time = 0.0
        tag = {1.0: "SLA", 0.5: "Balanced", 0.0: "Carbon"}.get(w_s, f"w{w_s}")
        self.name = label or f"MERSEM-{tag}" + ("-Oracle" if oracle else "")

    # ---------------------------------------------------------------- simulator hooks
    def attach(self, sim) -> None:
        self.sim = sim
        self.plan = {}
        t = 0.0
        while t < sim.wl.horizon:
            sim._push(t, 9, self._on_epoch, None)  # 9 == EPOCH
            t += self.epoch

    def _on_epoch(self, sim) -> None:
        t0 = sim.now
        jobs = [j for j in sim.job_specs if t0 <= j.arrival < t0 + self.epoch]
        if not jobs:
            return
        start = time.perf_counter()
        self.plan.update(self._optimise(sim, jobs))
        self.plan_time += time.perf_counter() - start

    def decide(self, ctx: Ctx) -> int:
        ks = [k for k, n in enumerate(ctx.nodes) if n.allowed]
        if ctx.task.pinned:
            return next(k for k in ks if ctx.nodes[k].is_origin)
        target = self.plan.get(ctx.task.job_id)
        for k in ks:
            if ctx.nodes[k].idx == target:
                return k
        return min(ks, key=lambda k: est_finish(ctx, ctx.nodes[k]))  # generous fallback

    # ---------------------------------------------------------------- planning model
    def _optimise(self, sim, jobs) -> dict:
        servers = [n for n in sim.servers if n.alive]
        country = sim.topo.country
        J = len(jobs)
        cand, execs, comms, carb, dl, arr = [], [], [], [], [], []
        node_index: dict[int, int] = {}
        nodes = []
        for n in servers:
            node_index[n.idx] = len(nodes)
            nodes.append(n)
        for j in jobs:
            origin = sim.by_name[j.origin]
            if origin.idx not in node_index:
                node_index[origin.idx] = len(nodes)
                nodes.append(origin)
            cs = [node_index[origin.idx]] + [node_index[n.idx] for n in servers
                                               if not (j.privacy and country[n.spec.loc] != country[origin.spec.loc])]
            work = [t.work if self.oracle else t.work_est for t in j.tasks if not t.pinned]
            W = sum(work)
            cp = _cp(j, self.oracle)
            ex, co, ca = [], [], []
            for c in cs:
                n = nodes[c]
                sp = n.spec.speed["vision" if j.cls == 0 else "generic"]
                ex.append(max(cp, W / n.spec.cores) / sp)
                tx = 0.0 if n is origin else sim.transfer(origin, n, max(j.input_mb, 0.1 if j.cls == 0 else 0), False) \
                    + sim.transfer(n, origin, j.result_mb, False)
                co.append(tx)
                ca.append(n.dyn_w * W / sp / 3.6e6 * sim.carbon.at(n.spec.zone, j.arrival))
            cand.append(cs)
            execs.append(ex)
            comms.append(co)
            carb.append(ca)
            dl.append(j.deadline - j.arrival)
            arr.append(j.arrival)
        free0 = [sim.now + sim.est_wait(n) for n in nodes]
        cref = sum(sim.c_ref[j.cls] for j in jobs)
        ncand = [len(c) for c in cand]

        def evaluate(g):
            free = list(free0)
            miss = 0
            co2 = 0.0
            for i in range(J):
                k = g[i]
                node = cand[i][k]
                st = max(arr[i] + comms[i][k], free[node])
                fin = st + execs[i][k]
                free[node] = fin
                if fin - arr[i] > dl[i]:
                    miss += 1
                co2 += carb[i][k]
            sla = miss / J
            c = co2 / cref
            return sla, c, self.w_s * sla + (1 - self.w_s) * c

        def greedy():
            free = list(free0)
            g = []
            for i in range(J):
                k = min(range(ncand[i]), key=lambda k: max(arr[i] + comms[i][k], free[cand[i][k]]) + execs[i][k])
                free[cand[i][k]] = max(arr[i] + comms[i][k], free[cand[i][k]]) + execs[i][k]
                g.append(k)
            return g

        rng = self.rng
        pop = [greedy()] + [[int(rng.integers(n)) for n in ncand] for _ in range(self.pop_n - 1)]
        fit = [evaluate(g) for g in pop]
        hour = int(((sim.start_hour + sim.now / 3600) % 24) // 6)
        for _gen in range(self.gens):
            # RL-guided local search on a subset
            idx = rng.choice(len(pop), size=max(1, int(self.ls_frac * len(pop))), replace=False)
            for i in idx:
                pop[i], fit[i] = self._local_search(pop[i], fit[i], evaluate, ncand, J, hour, cand, nodes)
            # crossover + mutation (rate 1.0)
            off = []
            for _ in range(len(pop)):
                a, b = rng.choice(len(pop), 2, replace=False)
                mask = rng.random(J) < 0.5
                child = [pop[a][i] if mask[i] else pop[b][i] for i in range(J)]
                for i in np.nonzero(rng.random(J) < 1.0 / J)[0]:
                    child[i] = int(rng.integers(ncand[i]))
                off.append(child)
            offf = [evaluate(g) for g in off]
            # dominance-based replacement
            allp, allf = pop + off, fit + offf
            rank = _nd_rank([(f[0], f[1]) for f in allf])
            order = sorted(range(len(allp)), key=lambda i: (rank[i], allf[i][2]))[: self.pop_n]
            pop, fit = [allp[i] for i in order], [allf[i] for i in order]
        best = min(range(len(pop)), key=lambda i: fit[i][2])
        g = pop[best]
        return {jobs[i].id: nodes[cand[i][g[i]]].idx for i in range(J)}

    def _state(self, f, g, J, hour, cand, nodes):
        layers = [0, 0, 0]
        for i in range(J):
            layers[nodes[cand[i][g[i]]].spec.tier] += 1
        b = lambda x, k: min(k - 1, int(x * k))
        return (b(min(f[2], 1.0), 5), b(f[0], 5), b(min(f[1], 2.0) / 2, 5),
                tuple(b(l / J, 4) for l in layers), min(3, J // 200), hour)

    def _local_search(self, g, f, evaluate, ncand, J, hour, cand, nodes):
        best_g, best_f = g, f
        traj = []
        f_start = f[2]
        for _ep in range(self.ls_eps):
            s = self._state(best_f, best_g, J, hour, cand, nodes)
            qs = self.q.setdefault(s, [0.0] * len(ACTIONS))
            a = int(self.rng.integers(len(ACTIONS))) if self.rng.random() < self.eps else int(np.argmax(qs))
            new = list(best_g)
            for i in self.rng.choice(J, size=max(1, int(ACTIONS[a] * J)), replace=False):
                new[i] = int(self.rng.integers(ncand[i]))
            nf = evaluate(new)
            dom = 1.0 if _dominates(nf, best_f) else (-0.5 if _dominates(best_f, nf) else 0.1)
            r = 0.7 * math.tanh(best_f[2] - nf[2]) + 0.3 * dom
            traj.append((s, a, r))
            if nf[2] < best_f[2]:
                best_g, best_f = new, nf
        imp = math.tanh(f_start - best_f[2])
        G = 0.0
        for s, a, r in reversed(traj):
            G = r + 0.9 * G
            q = self.q[s]
            q[a] += 0.15 * (G + imp - q[a])
        self.eps = max(0.05, self.eps * 0.995)
        return best_g, best_f


def _cp(j, oracle):
    n = len(j.tasks)
    down = [0.0] * n
    order = []
    indeg = [len(p) for p in j.preds]
    st = [i for i in range(n) if indeg[i] == 0]
    while st:
        u = st.pop()
        order.append(u)
        for v in j.succs[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                st.append(v)
    for u in reversed(order):
        w = 0.0 if j.tasks[u].pinned else (j.tasks[u].work if oracle else j.tasks[u].work_est)
        down[u] = w + max((down[v] for v in j.succs[u]), default=0.0)
    return max(down) if n else 0.0


def _dominates(a, b):
    return a[0] <= b[0] and a[1] <= b[1] and (a[0] < b[0] or a[1] < b[1])


def _nd_rank(objs):
    n = len(objs)
    rank = [0] * n
    remaining = set(range(n))
    r = 0
    while remaining:
        front = [i for i in remaining if not any(_dominates(objs[j], objs[i]) for j in remaining if j != i)]
        for i in front:
            rank[i] = r
        remaining -= set(front)
        r += 1
    return rank
