"""Live orchestrator: runs a workload on real nodes with any PACE-project scheduler.

It *reuses* the simulator's decision-context builder, job bookkeeping and metrics
(by duck-typing pace.sim.core.Simulator), so schedulers see exactly the same Ctx
in simulation and on AWS. Only the execution mechanics differ: tasks are sent to
real workers over HTTP, inputs move between real nodes, runtimes are measured.
The network estimates start from the calibration and are corrected online from the network time of
recently completed tasks (90th percentile per region, at most 3 s), so all schedulers see latency drift.
A failed task is placed again (up to 3 times); only the heartbeat or a worker's "503 down" takes a node out.

  python -m testbed.orchestrator --nodes testbed/nodes.json --scheduler pace-shield --minutes 10
  open http://localhost:8080  (live dashboard; fault injection, SLA target, carbon spike)
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import random
import time
from collections import deque
from pathlib import Path

import numpy as np
from aiohttp import ClientSession, ClientTimeout, TCPConnector, web

from pace.carbon import CarbonTrace
from pace.config import EDGE, NodeSpec, Topology, Workload
from pace.sim.core import DEFER_DT, DONE, READY, RUNNING, SJob, SNode, Simulator
from pace.views import DEFER, carbon_est, est_finish
from pace.workload import JobSpec, TaskSpec, generate

ROOT = Path(__file__).resolve().parent


class CompressedCarbon:
    """Carbon clock running `scale`x faster than wall time (1 grid hour per 3600/scale s)."""

    def __init__(self, trace: CarbonTrace, scale: float):
        self.trace, self.scale = trace, scale
        self.spikes: dict[str, tuple[float, float]] = {}  # zone -> (factor, until wall-time)
        self.clock = lambda: 0.0

    def _mult(self, zone):
        f, until = self.spikes.get(zone, (1.0, 0.0))
        return f if self.clock() < until else 1.0

    def at(self, zone, t):
        return self.trace.at(zone, t * self.scale) * self._mult(zone)

    def forecast(self, zone, t, ahead_h, rng=None, err=0.05):
        return self.trace.forecast(zone, t * self.scale, ahead_h, rng, err)

    def mean(self, zone):
        return self.trace.mean(zone)

    def set_start(self, h):
        self.trace.set_start(h)


def load_nodes(path: str) -> tuple[Topology, str]:
    cfg = json.loads(Path(path).read_text())
    nodes = []
    for n in cfg["nodes"]:
        nodes.append(NodeSpec(n["name"], int(n["tier"]), n["loc"], n["zone"], int(n["cores"]), dict(n["speed"]),
                              float(n["idle_w"]), float(n["max_w"]), float(n.get("pue", 1.0)), n.get("arch", "x86"),
                              n["name"] if int(n["tier"]) == EDGE else None, float(n.get("mem_gb", 4.0)), n["url"],
                              float(n.get("contention", 0.15))))
    topo = Topology(nodes)
    if "net" in cfg:
        topo.net = {tuple(k.split("-")): tuple(v) for k, v in cfg["net"].items()}
    if "country" in cfg:
        topo.country = cfg["country"]
    # the orchestrator runs next to the edge devices (the laptop) unless the file says otherwise
    topo.ctrl_loc = cfg.get("controller") or next((n.loc for n in nodes if n.tier == EDGE), None)
    return topo, cfg.get("token", os.environ.get("PACE_TOKEN", "pace-demo"))


# the policy fine-tuned in the calibrated twin of the real testbed, when present (pace.rl.train --nodes)
DEFAULT_MODEL = "models/pace_live.pt" if Path("models/pace_live.pt").exists() else "models/pace.pt"


def make_scheduler(a):
    from pace.sched import heuristics as H
    from pace.sched.mersem import MERSEM
    name = a.scheduler.lower()
    if name in ("pace", "pace-shield"):
        from pace.rl.agent import PACE
        return PACE(a.model, w=a.w, sla_target=a.target, shield=name == "pace-shield")
    if name.startswith("mersem"):
        return MERSEM(w_s=getattr(a, "mersem_w", 0.5), epoch=a.epoch, gens=15)
    table = {"ca-eft": H.CAEFT, "eft": H.EFT, "cloud": H.CloudOnly, "fog": H.FogOnly, "edge": H.LocalFirst,
             "carbon": H.CarbonGreedy, "random": H.RandomS}
    return table[name]()


class NodeDown(Exception):
    pass


class LiveOrchestrator(Simulator):
    """Duck-types Simulator: same _ctx / _job_done / summary, real execution."""

    def __init__(self, topo: Topology, wl: Workload, scheduler, token: str, seed: int = 1, time_scale: float = 60.0,
                 camera: bool = False, run_id: str = "run"):
        self.topo, self.wl, self.seed = topo, wl, seed
        self.rng = np.random.default_rng(seed)
        zones = sorted({n.zone for n in topo.nodes})
        self.carbon = CompressedCarbon(CarbonTrace(zones, wl.carbon_source, seed=seed), time_scale)
        self.start_hour = wl.start_hour if wl.start_hour is not None else 10.0
        self.carbon.set_start(int(self.start_hour))
        self.time_scale = time_scale
        self.nodes = [SNode(s, i, wl.priority) for i, s in enumerate(topo.nodes)]
        self.by_name = {n.spec.name: n for n in self.nodes}
        self.servers = [n for n in self.nodes if n.spec.tier != EDGE]
        if camera:
            wl.rate_a = 0.0
        self.job_specs = generate(topo, wl, self.rng, self.start_hour)
        self.ready: deque = deque()
        self.records: list[dict] = []
        self.task_records: list[dict] = []  # per task: where, network/queue/compute time (sim-to-real E9)
        # online network estimate: measured minus modelled network time of recent tasks, per location
        self.net_resid: dict[str, deque] = {}
        self.net_corr: dict[str, float] = {}
        self.net_trace: list[dict] = []
        self.placed_at: dict[int, float] = {}
        self.jobs: list[SJob] = []
        self.sla_ewma = 0.0
        self.listeners: list = []
        self.n_decisions = 0
        self.c_ref = self._c_ref()
        self.sched = scheduler
        self.token = token
        self.run_id = run_id
        self.decisions: deque = deque(maxlen=40)
        self.series: list = []
        self.events: list = []
        self.frames: dict = {}
        self.last_frame: dict = {}
        self.t0 = None
        self.cur = None
        self.cur_ctx = None
        self.hb_fail = {n.idx: 0 for n in self.nodes}
        self.attempts: dict[int, int] = {}
        self.closing = False
        self.decide_wall = 0.0

    # --------------------------------------------------------------- time
    @property
    def now(self) -> float:
        return 0.0 if self.t0 is None else time.monotonic() - self.t0

    @now.setter
    def now(self, v):  # Simulator code may assign; wall clock is authoritative
        pass

    def _push(self, t, kind, a=None, b=None):
        if kind == 9:  # EPOCH callback (MERSEM planning)
            asyncio.get_running_loop().call_later(max(0.0, t - self.now), a, self)

    # --------------------------------------------------------------- decisions
    def _drain(self):
        while self.ready:
            task = self.ready.popleft()
            if task.state != READY:
                continue
            ctx = self._ctx(task)
            if not any(n.allowed for n in ctx.nodes):  # every candidate is down: try again in a second
                asyncio.get_running_loop().call_later(1.0, self._wake, task, task.ver)
                continue
            self.cur, self.cur_ctx = task, ctx
            t0 = time.perf_counter()
            k = self.sched.decide(ctx)
            self.decide_wall += time.perf_counter() - t0
            self._log_decision(ctx, k)
            self.apply(k)

    def apply(self, k):
        task, ctx = self.cur, self.cur_ctx
        task.n_decisions += 1
        self.n_decisions += 1
        if k == DEFER:
            task.defer_count += 1
            task.ver += 1
            ver = task.ver
            asyncio.get_running_loop().call_later(DEFER_DT / self.time_scale, self._wake, task, ver)
            return
        node = self.nodes[ctx.nodes[k].idx]
        task.node = node
        task.state = 2
        task.ver += 1
        node.queue.append(task)
        b = task.spec.work_est / node.spec.speed[task.spec.typ]
        node.backlog += b
        node.backlog_cls[task.job.spec.cls] += b
        node.count_cls[task.job.spec.cls] += 1
        # send it now: the worker fetches the inputs while earlier tasks compute and starts it when a core
        # is free (class priority), so transfers overlap with computation as in the simulator
        self.placed_at[id(task)] = (self.now, Simulator._ctrl(self, node) + self._data_transfer(task, node, False))
        asyncio.create_task(self._exec(task, node, task.ver))
        self._pump(node)

    def _wake(self, task, ver):
        if ver == task.ver:
            task.state = READY
            self.ready.append(task)
            self._drain()

    def _log_decision(self, ctx, k):
        cands = sorted(((est_finish(ctx, n) - ctx.now, carbon_est(ctx, n), n.name, n.allowed) for n in ctx.nodes),
                       key=lambda x: x[0])
        chosen = "DEFER" if k == DEFER else ctx.nodes[k].name
        self.decisions.appendleft(dict(t=round(ctx.now, 2), job=ctx.task.job_id, cls="ABC"[ctx.task.cls],
                                       task=ctx.task.tid, chosen=chosen, budget=round(ctx.task.lf - ctx.now, 2),
                                       cands=[dict(node=c[2], eft=round(c[0], 2), gco2=c[1], ok=c[3]) for c in cands[:4]]))

    # --------------------------------------------------------------- execution
    def _pump(self, node: SNode):
        """Mirror of the worker's own queue (for the schedulers' wait estimates); the HTTP request is
        already on its way (see apply)."""
        while node.alive and node.queue and len(node.running) < node.spec.cores:
            task = node.queue.popleft()
            sp = node.spec.speed[task.spec.typ]
            node.backlog = max(0.0, node.backlog - task.spec.work_est / sp)
            c = task.job.spec.cls
            node.backlog_cls[c] = max(0.0, node.backlog_cls[c] - task.spec.work_est / sp)
            node.count_cls[c] = max(0, node.count_cls[c] - 1)
            task.state = RUNNING
            task.start = self.now
            task.est_end = self.now + task.spec.work_est / sp
            node.running.add(task)

    def _ctrl(self, node: SNode) -> float:
        """Controller round trip as calibrated, plus what the network has recently been adding on top of
        the calibrated model (90th percentile of the last 30 residuals). Every scheduler's transfer
        estimate, PACE's features and the shield use it, so they all see the network as it is now."""
        return Simulator._ctrl(self, node) + self.net_corr.get(node.spec.loc, 0.0)

    def _observe_net(self, node: SNode, resid: float):
        loc = node.spec.loc
        if loc == self.topo.ctrl_loc:
            return
        d = self.net_resid.setdefault(loc, deque(maxlen=30))
        d.append(resid)
        if len(d) >= 5:
            corr = min(3.0, max(0.0, float(np.quantile(list(d), 0.9))))
            if abs(corr - self.net_corr.get(loc, 0.0)) > 0.05:
                self.net_trace.append(dict(t=round(self.now, 1), loc=loc, extra_s=round(corr, 3)))
            self.net_corr[loc] = corr

    async def _gc(self, node: SNode, prefix: str):
        try:
            async with self.http.post(f"{node.spec.url}/gc", json={"prefix": prefix}) as r:
                await r.read()
        except Exception:  # noqa: BLE001 - best effort (older workers have no /gc)
            pass

    def _key(self, task):
        return f"{self.run_id}-{task.job.spec.id}-{task.i}"

    async def _exec(self, task, node: SNode, ver: int):
        js = task.job.spec
        body = dict(key=self._key(task), work=task.spec.work, typ=task.spec.typ, inputs=[], inline=[], prio=js.cls)
        succ = js.succs[task.i]
        body["out_mb"] = max([mb for (a, b, mb) in js.edges if a == task.i] + [0.0]) if succ else js.result_mb
        frame = self.frames.get(js.id)
        if js.cls == 0 and frame is not None:
            if task.i == 0:
                body["frame"] = base64.b64encode(frame).decode()
                body["pass_frame"] = True
        try:
            for p in js.preds[task.i]:
                pt = task.job.tasks[p]
                pn = pt.node
                url = f"{pn.spec.url}/blob/{self._key(pt)}"
                if pn.spec.tier == EDGE and node.spec.tier != EDGE:
                    async with self.http.get(url) as r:  # edge is behind NAT: relay its output inline
                        r.raise_for_status()
                        data = await r.read()
                    if js.cls == 0 and data[:2] == b"\xff\xd8":
                        body["frame"] = base64.b64encode(data).decode()
                    else:
                        body["inline"].append(base64.b64encode(data).decode())
                else:
                    body["inputs"].append(url)
            if not js.preds[task.i] and not task.spec.pinned and node.idx != task.job.origin:
                body["inline"].append(base64.b64encode(os.urandom(int(js.input_mb * 1e6))).decode())
            async with self.http.post(f"{node.spec.url}/run", json=body) as r:
                if r.status == 503:
                    raise NodeDown(f"{node.spec.name} down")
                if r.status != 200:
                    raise RuntimeError(f"{node.spec.name} HTTP {r.status}: {(await r.text())[:60]}")
                res = await r.json()
        except Exception as e:  # noqa: BLE001
            if self.closing or ver != task.ver:
                return
            if isinstance(e, NodeDown):  # the worker says it is down (crash): take the node out now
                if node.alive:
                    self.events.append(dict(t=round(self.now, 2), ev="task-failed", node=node.spec.name, err=str(e)[:80]))
                    self._fail_node(node)
            else:  # one task failed (reset, timeout, lost input): place it again; outages are the heartbeat's job
                self._retry(task, node, f"{type(e).__name__}: {e}")
            return
        if ver != task.ver:
            return
        if self._unmirror(task, node) == "queued":  # finished before the mirror queue promoted it
            task.start = self.now - float(res.get("t_exec", 0.0))
        task.end = self.now
        t_exec = float(res.get("t_exec", task.end - task.start))
        placed, pred_net = self.placed_at.pop(id(task), (task.start, None))
        if pred_net is not None:
            self._observe_net(node, (self.now - placed) - float(res.get("t_queue", 0)) - t_exec - pred_net)
        self.task_records.append(dict(job=js.id, cls=js.cls, i=task.i, node=node.spec.name, placed=round(placed, 3),
                                      total=round(self.now - placed, 3), fetch=round(float(res.get("t_fetch", 0)), 3),
                                      queue=round(float(res.get("t_queue", 0)), 3), exec=round(t_exec, 3)))
        self._account(task, node, t_exec)
        task.state = DONE
        job = task.job
        job.n_done += 1
        job.rem_work = max(0.0, job.rem_work - task.spec.work_est)
        if js.cls == 0 and res.get("boxes") is not None and task.spec.typ == "vision" and task.i == 1:
            self.last_frame = dict(job=js.id, boxes=res["boxes"], node=node.spec.name)
        for v in js.succs[task.i]:
            st = job.tasks[v]
            st.n_pending -= 1
            if st.n_pending == 0:
                st.state = READY
                self.ready.append(st)
        if not js.succs[task.i]:
            job.finish = max(job.finish, self.now)  # response reached the origin (laptop)
        if job.n_done == len(job.tasks):
            self._job_done(job)
            self.frames.pop(js.id, None)
            for n in {t.node for t in job.tasks if t.node is not None}:
                asyncio.create_task(self._gc(n, f"{self.run_id}-{js.id}-"))
        self._pump(node)
        self._drain()

    def _unmirror(self, task, node: SNode):
        """Take a task out of the node's mirror queue / running set."""
        if task in node.running:
            node.running.discard(task)
            return "running"
        if node.queue.remove(task):
            sp = node.spec.speed[task.spec.typ]
            c = task.job.spec.cls
            node.backlog = max(0.0, node.backlog - task.spec.work_est / sp)
            node.backlog_cls[c] = max(0.0, node.backlog_cls[c] - task.spec.work_est / sp)
            node.count_cls[c] = max(0, node.count_cls[c] - 1)
            return "queued"
        return None

    def _retry(self, task, node: SNode, err: str):
        n = self.attempts.get(id(task), 0) + 1
        self.attempts[id(task)] = n
        self._unmirror(task, node)
        self.placed_at.pop(id(task), None)
        task.ver += 1
        task.node = None
        self.events.append(dict(t=round(self.now, 2), ev="task-retry" if n <= 3 else "task-abandoned",
                                node=node.spec.name, err=err[:80], attempt=n))
        self._pump(node)
        if n <= 3:
            task.state = READY
            task.retry = True
            self.ready.append(task)
            self._drain()

    def _fail_node(self, node: SNode):
        if not node.alive:
            return
        node.alive = False
        node.down_since = self.now
        lost = list(node.running) + list(node.queue)
        for t in node.running:
            self._account(t, node, max(0.0, self.now - t.start))
        node.running.clear()
        node.queue.clear()
        node.backlog = 0.0
        node.backlog_cls = [0.0, 0.0, 0.0]
        node.count_cls = [0, 0, 0]
        for t in lost:
            t.ver += 1
            t.state = READY
            t.retry = True
            t.node = None
            self.ready.append(t)
        self.events.append(dict(t=round(self.now, 2), ev="node-down", node=node.spec.name, requeued=len(lost)))
        self._drain()

    async def _heartbeat(self):
        while True:
            for n in self.nodes:
                ok = False
                try:
                    async with self.http.get(f"{n.spec.url}/status", timeout=ClientTimeout(total=3)) as r:
                        ok = r.status == 200
                except Exception:  # noqa: BLE001
                    ok = False
                if ok:
                    self.hb_fail[n.idx] = 0
                    if not n.alive:
                        n.alive = True
                        n.down_total += self.now - n.down_since
                        self.events.append(dict(t=round(self.now, 2), ev="node-up", node=n.spec.name))
                        self._pump(n)
                else:
                    self.hb_fail[n.idx] += 1
                    if self.hb_fail[n.idx] >= 2:
                        self._fail_node(n)
            await asyncio.sleep(2.0)

    async def _sampler(self):
        while True:
            self.series.append(self._snapshot_metrics())
            await asyncio.sleep(5.0)

    def _snapshot_metrics(self):
        recs = self.records
        ab = [r for r in recs if r["cls"] != 2][-60:]
        a = [r["latency"] for r in recs if r["cls"] == 0][-100:]
        return dict(t=round(self.now, 1), jobs=len(recs), sla_AB_recent=float(np.mean([r["miss"] for r in ab])) if ab else 0.0,
                    carbon=float(sum(r["carbon"] for r in recs)), p95_A=float(np.percentile(a, 95)) if a else 0.0,
                    w=getattr(self.sched, "w", None))

    # --------------------------------------------------------------- arrivals
    def _arrive(self, spec: JobSpec):
        job = SJob(spec, self.by_name[spec.origin].idx)
        self.jobs.append(job)
        for t in job.tasks:
            if t.n_pending == 0:
                t.state = READY
                self.ready.append(t)
        self._drain()

    def camera_job(self, cam: str, frame: bytes, private: bool = False):
        now = self.now
        ws = [0.04, 0.30, 0.02]
        ts = [TaskSpec(ws[0], ws[0], "vision", 0.1, True), TaskSpec(ws[1], ws[1], "vision", 0.3, False),
              TaskSpec(ws[2], ws[2], "generic", 0.05, False)]
        spec = JobSpec(len(self.job_specs) + 100000, 0, cam, now, now + self.wl.deadline_a, ts,
                       [(0, 1, len(frame) / 1e6), (1, 2, 0.002)], 0.0, 0.001, private, False).finalize()
        self.job_specs.append(spec)
        self.frames[spec.id] = frame
        self._arrive(spec)

    def burst(self, mult: float, secs: float):
        rng = np.random.default_rng(int(self.now))
        wl = Workload(**{**self.wl.__dict__, "horizon": secs, "rate_a": 0.0, "rate_bc": self.wl.rate_bc * mult,
                         "bursts": [], "split": "test"})
        loop = asyncio.get_running_loop()
        base = self.now
        for j in generate(self.topo, wl, rng, self.start_hour):
            j.id += 200000 + int(base * 1000)
            j.arrival += base
            j.deadline += base
            loop.call_later(j.arrival - base, self._arrive, j)

    # --------------------------------------------------------------- main
    async def run(self, minutes: float, drain_s: float = 120.0):
        # keep connections to the workers open between tasks: a new TCP handshake costs one more round trip
        self.http = ClientSession(timeout=ClientTimeout(total=180), headers={"X-Token": self.token},
                                  connector=TCPConnector(limit=0, keepalive_timeout=120))
        loop = asyncio.get_running_loop()
        self.t0 = time.monotonic()
        self.carbon.clock = lambda: self.now
        if hasattr(self.sched, "attach"):
            self.sched.attach(self)
        for j in self.job_specs:
            if j.arrival < minutes * 60:
                loop.call_later(j.arrival, self._arrive, j)
        hb = asyncio.create_task(self._heartbeat())
        sp = asyncio.create_task(self._sampler())
        await asyncio.sleep(minutes * 60)
        end = self.now + drain_s
        while self.now < end and any(not j.done for j in self.jobs):
            await asyncio.sleep(1.0)
        hb.cancel()
        sp.cancel()
        self.closing = True
        await self.http.close()
        return self.summary()

    def state(self) -> dict:
        nodes = []
        for n in self.nodes:
            nodes.append(dict(name=n.spec.name, tier=n.spec.tier, loc=n.spec.loc, zone=n.spec.zone, alive=n.alive,
                              running=len(n.running), queued=len(n.queue), cores=n.spec.cores,
                              ci=round(self.carbon.at(n.spec.zone, self.now), 1), busy_s=round(n.busy_s, 1)))
        s = self.summary() if self.records else {}
        return dict(run=self.run_id, scheduler=self.sched.name, t=round(self.now, 1), w=getattr(self.sched, "w", None),
                    target=getattr(self.sched, "target", None), grid_hour=round((self.start_hour + self.now *
                                                                               self.time_scale / 3600) % 24, 2),
                    summary={k: v for k, v in s.items() if isinstance(v, (int, float))}, nodes=nodes,
                    decisions=list(self.decisions)[:15], events=self.events[-10:], series=self.series[-120:],
                    frame=self.last_frame, decide_ms=1000 * self.decide_wall / max(1, self.n_decisions),
                    net_extra={k: round(v, 3) for k, v in self.net_corr.items()})


def web_app(orch: LiveOrchestrator) -> web.Application:
    @web.middleware
    async def cors(request, handler):
        resp = await handler(request)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp

    async def index(_r):
        return web.FileResponse(ROOT / "dashboard.html")

    async def state(_r):
        return web.json_response(orch.state())

    async def fail(r):
        n = orch.by_name[r.query["node"]]
        secs = float(r.query.get("secs", "60"))
        async with orch.http.post(f"{n.spec.url}/admin/crash?secs={secs}") as resp:
            await resp.read()
        orch.events.append(dict(t=round(orch.now, 2), ev="inject-crash", node=n.spec.name, secs=secs))
        return web.json_response({"ok": True})

    async def target(r):
        v = r.query.get("value")
        if hasattr(orch.sched, "target"):
            orch.sched.target = None if v in (None, "", "none") else float(v)
        orch.events.append(dict(t=round(orch.now, 2), ev="sla-target", value=v))
        return web.json_response({"ok": True})

    async def spike(r):
        z, f, secs = r.query["zone"], float(r.query.get("factor", "3")), float(r.query.get("secs", "60"))
        orch.carbon.spikes[z] = (f, orch.now + secs)
        orch.events.append(dict(t=round(orch.now, 2), ev="carbon-spike", zone=z, factor=f))
        return web.json_response({"ok": True})

    async def burst(r):
        orch.burst(float(r.query.get("mult", "3")), float(r.query.get("secs", "60")))
        orch.events.append(dict(t=round(orch.now, 2), ev="burst", mult=r.query.get("mult", "3")))
        return web.json_response({"ok": True})

    async def frame(r):
        data = await r.read()
        orch.camera_job(r.headers.get("X-Camera", orch.nodes[0].spec.name), data,
                        r.headers.get("X-Private", "0") == "1")
        return web.json_response({"ok": True})

    app = web.Application(middlewares=[cors], client_max_size=16 * 1024 ** 2)
    app.add_routes([web.get("/", index), web.get("/api/state", state), web.post("/api/fail", fail),
                    web.post("/api/target", target), web.post("/api/spike", spike), web.post("/api/burst", burst),
                    web.post("/api/frame", frame)])
    return app


async def amain(a):
    topo, token = load_nodes(a.nodes)
    wl = Workload(split="test", horizon=a.minutes * 60, start_hour=a.start_hour, rate_a=a.rate_a, rate_bc=a.rate_bc,
                  work_scale=a.work_scale, data_scale=a.work_scale, est_noise=a.est_noise,
                  carbon_source=a.carbon)
    sched = make_scheduler(a)
    run_id = f"{a.scheduler}-s{a.seed}-{int(time.time()) % 100000}"
    orch = LiveOrchestrator(topo, wl, sched, token, seed=a.seed, time_scale=a.time_scale, camera=a.camera, run_id=run_id)
    runner = None
    if a.port:
        runner = web.AppRunner(web_app(orch))
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", a.port).start()
        print(f"dashboard: http://localhost:{a.port}", flush=True)
    summary = await orch.run(a.minutes, a.drain)
    out = dict(args=vars(a), summary=summary, records=orch.records, tasks=orch.task_records, net_trace=orch.net_trace,
               events=orch.events,
               series=orch.series,
               decide_ms=1000 * orch.decide_wall / max(1, orch.n_decisions),
               w_trace=getattr(sched, "w_trace", None), plan_s=getattr(sched, "plan_time", None))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in summary.items()}), flush=True)
    if runner and a.linger:
        print("run finished; dashboard still up (Ctrl+C to exit)", flush=True)
        await asyncio.Event().wait()
    if runner:
        await runner.cleanup()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", default="testbed/nodes.json")
    ap.add_argument("--scheduler", default="pace")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--w", type=float, default=0.9, help="PACE SLA weight (0 = carbon only, 1 = SLA only)")
    ap.add_argument("--mersem-w", type=float, default=0.5, help="MERSEM w_s (0.5 = MERSEM-Balanced)")
    ap.add_argument("--target", type=float, default=None)
    ap.add_argument("--epoch", type=float, default=120.0, help="MERSEM planning epoch (s)")
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--drain", type=float, default=120)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--rate-a", type=float, default=0.25)
    ap.add_argument("--rate-bc", type=float, default=0.075)
    ap.add_argument("--work-scale", type=float, default=0.2)
    ap.add_argument("--est-noise", type=float, default=0.2)
    ap.add_argument("--start-hour", type=float, default=10.0)
    ap.add_argument("--time-scale", type=float, default=60.0, help="carbon clock speed-up (60 = 1 grid hour/min)")
    ap.add_argument("--carbon", default="synthetic")
    ap.add_argument("--camera", action="store_true", help="class-A jobs come from testbed/camera.py frames")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--linger", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    a.out = a.out or f"results/testbed/{a.scheduler}_s{a.seed}_{int(time.time())}.json"
    random.seed(a.seed)
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(amain(a))


if __name__ == "__main__":
    main()
