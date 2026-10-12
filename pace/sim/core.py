"""Discrete-event simulator for task-level DAG scheduling on an edge-fog-cloud system.

Model (documented assumptions, see docs/PROPOSAL.md):
  * Each node has `cores` execution slots; tasks wait FIFO when all slots are busy.
    Co-located tasks interfere: runtime x (1 + 0.15 * (busy-1)/(cores-1)).
  * A task can start only after all parents finished and their outputs were transferred
    to its node (RTT/2 + MB/bandwidth, log-normal jitter). Entry tasks fetch the job input
    from the origin device; exit tasks send results back to the origin.
  * Energy: idle power always (reported), dynamic power per busy core (drives decisions).
    Carbon = energy x grid intensity of the node's zone at task start (hourly trace).
  * Failures drop running/queued/in-transit tasks on the node; they are re-scheduled.
    Completed outputs are assumed persisted (regional object store).
  * Schedulers only see estimates (work_est), never true runtimes.
"""
from __future__ import annotations

import heapq
import math
from collections import deque

import numpy as np

from ..carbon import CarbonTrace
from ..config import EDGE, Topology, Workload
from ..views import DEFER, Ctx, NodeView, TaskView
from ..workload import JobSpec, generate

ARRIVE, DATA, FINISH, JOBDONE, FAIL, RECOVER, SLOW, UNSLOW, WAKE, EPOCH = range(10)
PENDING, READY, PLACED, RUNNING, DONE = range(5)
DEFER_DT = 900.0


class STask:
    __slots__ = ("job", "i", "spec", "node", "state", "ver", "start", "end", "est_end", "carbon", "energy",
                 "n_pending", "defer_count", "n_decisions", "retry")

    def __init__(self, job, i, spec):
        self.job, self.i, self.spec = job, i, spec
        self.node = None
        self.state = PENDING
        self.ver = 0
        self.start = self.end = self.est_end = 0.0
        self.carbon = self.energy = 0.0
        self.n_pending = 0
        self.defer_count = 0
        self.n_decisions = 0
        self.retry = False


class SJob:
    __slots__ = ("spec", "tasks", "n_done", "finish", "carbon", "done", "origin")

    def __init__(self, spec: JobSpec, origin: int):
        self.spec = spec
        self.tasks = [STask(self, i, t) for i, t in enumerate(spec.tasks)]
        for i, p in enumerate(spec.preds):
            self.tasks[i].n_pending = len(p)
        self.n_done = 0
        self.finish = 0.0
        self.carbon = 0.0
        self.done = False
        self.origin = origin


class SNode:
    __slots__ = ("spec", "idx", "alive", "running", "queue", "transit", "slow", "backlog", "down_total",
                 "down_since", "dyn_w", "busy_s")

    def __init__(self, spec, idx):
        self.spec, self.idx = spec, idx
        self.alive = True
        self.running: set = set()
        self.queue: deque = deque()
        self.transit: set = set()
        self.slow = 1.0
        self.backlog = 0.0  # est seconds of queued + in-transit work on this node
        self.down_total = 0.0
        self.down_since = 0.0
        self.dyn_w = (spec.max_w - spec.idle_w) / spec.cores * spec.pue
        self.busy_s = 0.0


class Simulator:
    def __init__(self, topo: Topology, wl: Workload, seed: int = 0, carbon: CarbonTrace | None = None,
                 jobs: list[JobSpec] | None = None):
        self.topo, self.wl, self.seed = topo, wl, seed
        self.rng = np.random.default_rng(seed)
        zones = sorted({n.zone for n in topo.nodes})
        self.carbon = carbon or CarbonTrace(zones, wl.carbon_source, seed=seed)
        start_hour = wl.start_hour if wl.start_hour is not None else float(self.rng.integers(0, 24))
        self.start_hour = start_hour
        self.carbon.set_start(int(start_hour) + 24 * int(self.rng.integers(0, 7)))
        self.nodes = [SNode(s, i) for i, s in enumerate(topo.nodes)]
        self.by_name = {n.spec.name: n for n in self.nodes}
        self.servers = [n for n in self.nodes if n.spec.tier != EDGE]
        self.job_specs = jobs if jobs is not None else generate(topo, wl, self.rng, start_hour)
        self.heap: list = []
        self.seq = 0
        self.now = 0.0
        self.ready: deque = deque()
        self.records: list[dict] = []
        self.jobs: list[SJob] = []
        self.sla_ewma = 0.0
        self.cur: STask | None = None
        self.cur_ctx: Ctx | None = None
        self.listeners: list = []  # callables(record) on job completion
        self.n_decisions = 0
        self.c_ref = self._c_ref()
        for j in self.job_specs:
            self._push(j.arrival, ARRIVE, j)
        for (t, name, down) in wl.failures:
            self._push(t, FAIL, self.by_name[name], down)
        horizon = wl.horizon
        for n in self.servers:
            for t in _poisson(self.rng, wl.fail_rate / 3600.0, horizon):
                self._push(t, FAIL, n, float(self.rng.uniform(120, 600)))
            for t in _poisson(self.rng, wl.straggle_rate / 3600.0, horizon):
                self._push(t, SLOW, n, float(self.rng.uniform(1.5, 3.0)))

    # ------------------------------------------------------------------ helpers
    def _c_ref(self) -> list[float]:
        """Mean dynamic carbon of a job of each class on the near fog (x86) at mean intensity."""
        fogs = [n for n in self.nodes if n.spec.tier == 1] or self.servers
        f = fogs[0]
        ci = self.carbon.mean(f.spec.zone)
        work = {0: 0.36, 1: 90.0 * self.wl.work_scale, 2: 90.0 * self.wl.work_scale}  # mean job work (ref-s)
        return [work[c] * f.dyn_w / 3.6e6 * ci for c in range(3)]

    def _push(self, t, kind, a=None, b=None):
        self.seq += 1
        heapq.heappush(self.heap, (t, self.seq, kind, a, b))

    def transfer(self, src: SNode, dst: SNode, mb: float, jitter: bool = True) -> float:
        if src is dst or mb <= 0:
            return 0.0
        rtt, bw = self.topo.link(src.spec.loc, dst.spec.loc)
        tx = mb * 8.0 / bw
        if jitter:
            tx *= math.exp(self.rng.normal(0.0, 0.2))
        return rtt / 2.0 + tx

    def est_wait(self, n: SNode) -> float:
        occ = len(n.running) + len(n.queue) + len(n.transit)
        if occ < n.spec.cores:
            return 0.0
        rem = sum(max(0.0, t.est_end - self.now) for t in n.running)
        return (rem + n.backlog) / n.spec.cores

    def _input_transfer(self, task: STask, node: SNode, jitter: bool) -> float:
        job = task.job
        preds = job.spec.preds[task.i]
        if not preds:
            if task.spec.pinned:
                return 0.0
            return self.transfer(self.nodes[job.origin], node, job.spec.input_mb, jitter)
        best = 0.0
        for p in preds:
            pn = job.tasks[p].node
            mb = _edge_mb(job.spec, p, task.i)
            best = max(best, self.transfer(pn, node, mb, jitter))
        return best

    # ------------------------------------------------------------------ decision API
    def next_decision(self) -> Ctx | None:
        while not self.ready:
            if not self.heap:
                return None
            t, _s, kind, a, b = heapq.heappop(self.heap)
            self.now = t
            self._handle(kind, a, b)
        task = self.ready.popleft()
        self.cur = task
        self.cur_ctx = self._ctx(task)
        return self.cur_ctx

    def apply(self, k: int) -> None:
        task, ctx = self.cur, self.cur_ctx
        task.n_decisions += 1
        self.n_decisions += 1
        if k == DEFER:
            assert ctx.can_defer
            task.defer_count += 1
            task.ver += 1
            self._push(self.now + DEFER_DT, WAKE, task, task.ver)
            return
        nv = ctx.nodes[k]
        assert nv.allowed, "scheduler chose a masked node"
        self._place(task, self.nodes[nv.idx])

    def run(self, scheduler) -> dict:
        if hasattr(scheduler, "attach"):
            scheduler.attach(self)
        while (c := self.next_decision()) is not None:
            self.apply(scheduler.decide(c))
        return self.summary()

    # ------------------------------------------------------------------ context
    def _ctx(self, task: STask) -> Ctx:
        job = task.job
        js = job.spec
        sp = task.spec
        lf = js.deadline - js.rem_cp[task.i] - 0.05
        tv = TaskView(task.i, js.id, js.cls, sp.typ, sp.work_est, sp.mem, js.deadline, lf, js.rem_cp[task.i],
                      js.n_desc[task.i], js.privacy, js.deferrable, task.defer_count, sp.pinned, task.retry,
                      js.arrival, len(job.tasks))
        origin = self.nodes[job.origin]
        cands = [origin] + self.servers
        ct = self.topo.country
        tod_t = self.now
        nvs = []
        for n in cands:
            s = n.spec
            allowed = n.alive and sp.mem <= s.mem_gb
            if sp.pinned and n is not origin:
                allowed = False
            if js.privacy and ct[s.loc] != ct[origin.spec.loc]:
                allowed = False
            ci = self.carbon.at(s.zone, tod_t)
            nvs.append(NodeView(n.idx, s.name, s.tier, s.loc, n.alive, s.cores, len(n.running),
                                len(n.queue) + len(n.transit), self.est_wait(n) if n.alive else 1e4,
                                s.speed[sp.typ],  # stragglers are hidden state
                                self._input_transfer(task, n, False), ci,
                                self.carbon.forecast(s.zone, tod_t, 1.0, self.rng),
                                self.carbon.forecast(s.zone, tod_t, 3.0, self.rng),
                                n.dyn_w, allowed, n is origin))
        can_defer = (js.deferrable and task.defer_count < 3
                     and lf - self.now - DEFER_DT > 1.5 * sp.work_est + 10.0)
        busy = sum(len(n.running) for n in self.servers)
        cap = sum(n.spec.cores for n in self.servers if n.alive) or 1
        tod = (self.start_hour + self.now / 3600.0) % 24.0
        return Ctx(self.now, tv, nvs, can_defer, tod, busy / cap, self.sla_ewma, self.c_ref[js.cls])

    # ------------------------------------------------------------------ mechanics
    def _place(self, task: STask, node: SNode) -> None:
        task.node = node
        task.state = PLACED
        task.ver += 1
        node.transit.add(task)
        node.backlog += task.spec.work_est / node.spec.speed[task.spec.typ]
        self._push(self.now + self._input_transfer(task, node, True), DATA, task, task.ver)

    def _start(self, task: STask, node: SNode) -> None:
        s = node.spec
        busy = len(node.running) + 1
        cont = 1.0 + 0.15 * (busy - 1) / max(1, s.cores - 1)
        sp = s.speed[task.spec.typ]
        dur = task.spec.work / sp * node.slow * cont
        task.start, task.end = self.now, self.now + dur
        task.est_end = self.now + task.spec.work_est / sp
        task.state = RUNNING
        node.running.add(task)
        node.backlog = max(0.0, node.backlog - task.spec.work_est / sp)
        self._push(task.end, FINISH, task, task.ver)

    def _try_start(self, node: SNode) -> None:
        while node.alive and node.queue and len(node.running) < node.spec.cores:
            self._start(node.queue.popleft(), node)

    def _account(self, task: STask, node: SNode, dur: float) -> None:
        e = node.dyn_w * dur
        c = e / 3.6e6 * self.carbon.at(node.spec.zone, task.start)
        task.energy += e
        task.carbon += c
        task.job.carbon += c
        node.busy_s += dur

    def _handle(self, kind, a, b) -> None:
        if kind == ARRIVE:
            spec: JobSpec = a
            job = SJob(spec, self.by_name[spec.origin].idx)
            self.jobs.append(job)
            for t in job.tasks:
                if t.n_pending == 0:
                    t.state = READY
                    self.ready.append(t)
        elif kind == DATA:
            task: STask = a
            if b != task.ver:
                return
            node = task.node
            node.transit.discard(task)
            node.queue.append(task)
            self._try_start(node)
        elif kind == FINISH:
            task = a
            if b != task.ver:
                return
            node = task.node
            node.running.discard(task)
            self._account(task, node, task.end - task.start)
            task.state = DONE
            job = task.job
            job.n_done += 1
            succs = job.spec.succs[task.i]
            for v in succs:
                st = job.tasks[v]
                st.n_pending -= 1
                if st.n_pending == 0:
                    st.state = READY
                    self.ready.append(st)
            if not succs:
                n_exit = sum(1 for s in job.spec.succs if not s)
                arr = self.now + self.transfer(node, self.nodes[job.origin], job.spec.result_mb / n_exit)
                job.finish = max(job.finish, arr)
            if job.n_done == len(job.tasks):
                self._push(job.finish, JOBDONE, job)
            self._try_start(node)
        elif kind == JOBDONE:
            self._job_done(a)
        elif kind == FAIL:
            node: SNode = a
            if not node.alive:
                return
            node.alive = False
            node.down_since = self.now
            lost = list(node.running) + list(node.queue) + list(node.transit)
            for t in node.running:
                self._account(t, node, self.now - t.start)  # wasted work still emits
            node.running.clear()
            node.queue.clear()
            node.transit.clear()
            node.backlog = 0.0
            for t in lost:
                t.ver += 1
                t.state = READY
                t.retry = True
                t.node = None
                self.ready.append(t)
            self._push(self.now + b, RECOVER, node)
        elif kind == RECOVER:
            a.alive = True
            a.down_total += self.now - a.down_since
        elif kind == SLOW:
            a.slow = b
            self._push(self.now + float(self.rng.uniform(300, 900)), UNSLOW, a)
        elif kind == UNSLOW:
            a.slow = 1.0
        elif kind == WAKE:
            task = a
            if b == task.ver:
                task.state = READY
                self.ready.append(task)
        elif kind == EPOCH:
            a(self)

    def _job_done(self, job: SJob) -> None:
        js = job.spec
        lat = job.finish - js.arrival
        miss = job.finish > js.deadline + 1e-9
        tard = max(0.0, job.finish - js.deadline) / max(js.deadline - js.arrival, 1e-6)
        job.done = True
        rec = dict(id=js.id, cls=js.cls, arrival=js.arrival, finish=job.finish, latency=lat, miss=miss,
                   tard=tard, carbon=job.carbon, n_tasks=len(job.tasks), cp_ref=js.cp_ref,
                   slowdown=lat / max(js.cp_ref, 1e-3),
                   deferrals=sum(t.defer_count for t in job.tasks))
        self.records.append(rec)
        if js.cls != 2:
            self.sla_ewma = 0.97 * self.sla_ewma + 0.03 * float(miss)
        for f in self.listeners:
            f(rec)

    # ------------------------------------------------------------------ metrics
    def summary(self) -> dict:
        recs = self.records
        end = max([self.now] + [r["finish"] for r in recs])
        idle_c = 0.0
        idle_e = 0.0
        for n in self.nodes:
            up = end - n.down_total - ((end - n.down_since) if not n.alive else 0.0)
            e = n.spec.idle_w * n.spec.pue * up
            hours = max(1, int(math.ceil(end / 3600)))
            ci = float(np.mean([self.carbon.at(n.spec.zone, h * 3600) for h in range(hours)]))
            idle_e += e
            idle_c += e / 3.6e6 * ci
        out = dict(jobs=len(recs), unfinished=len(self.jobs) - len(recs), decisions=self.n_decisions,
                   carbon_dyn=sum(r["carbon"] for r in recs), carbon_idle=idle_c, makespan=end)
        out["carbon_total"] = out["carbon_dyn"] + idle_c
        lat = np.array([r["latency"] for r in recs]) if recs else np.zeros(1)
        out["sla_viol"] = float(np.mean([r["miss"] for r in recs])) if recs else 0.0
        for c, nm in enumerate("ABC"):
            rc = [r for r in recs if r["cls"] == c]
            out[f"sla_{nm}"] = float(np.mean([r["miss"] for r in rc])) if rc else 0.0
            out[f"n_{nm}"] = len(rc)
            out[f"carbon_{nm}"] = float(sum(r["carbon"] for r in rc))
            out[f"p95_{nm}"] = float(np.percentile([r["latency"] for r in rc], 95)) if rc else 0.0
        out["sla_AB"] = float(np.mean([r["miss"] for r in recs if r["cls"] != 2])) if recs else 0.0
        out["p95"] = float(np.percentile(lat, 95))
        out["p99"] = float(np.percentile(lat, 99))
        out["slowdown"] = float(np.mean([r["slowdown"] for r in recs])) if recs else 0.0
        out["carbon_per_job"] = out["carbon_total"] / max(1, len(recs))
        tiers = [0.0, 0.0, 0.0]
        for n in self.nodes:
            tiers[n.spec.tier] += n.busy_s
        tot = sum(tiers) or 1.0
        out["share_edge"], out["share_fog"], out["share_cloud"] = (t / tot for t in tiers)
        out["deferrals"] = int(sum(r["deferrals"] for r in recs))
        return out


def _edge_mb(js: JobSpec, s: int, d: int) -> float:
    cache = getattr(js, "_emb", None)
    if cache is None:
        cache = {(a, b): mb for a, b, mb in js.edges}
        js._emb = cache
    return cache.get((s, d), 0.0)


def _poisson(rng, rate, horizon):
    if rate <= 0:
        return []
    t, out = 0.0, []
    while True:
        t += rng.exponential(1.0 / rate)
        if t >= horizon:
            return out
        out.append(t)
