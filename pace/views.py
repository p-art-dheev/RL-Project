"""Decision context shared by the simulator and the real testbed orchestrator.

Every scheduler (heuristics, MERSEM, PACE) only sees a `Ctx`, so the exact same
scheduler code runs in simulation and on AWS.
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFER = -1


@dataclass(slots=True)
class TaskView:
    tid: int
    job_id: int
    cls: int  # 0 = A (alert), 1 = B (graph analytics), 2 = C (batch)
    typ: str
    work_est: float  # estimated work, reference-core seconds
    mem: float
    deadline: float  # absolute job deadline
    lf: float  # latest finish for this task so the job can still meet its deadline
    rem_cp: float  # estimated critical path remaining after this task (ref seconds)
    n_desc: int
    privacy: bool
    deferrable: bool
    defer_count: int
    pinned: bool
    retry: bool
    arrival: float
    n_tasks: int
    job_rem_work: float = 0.0  # estimated work of the job's unfinished tasks (ref-core seconds)


@dataclass(slots=True)
class NodeView:
    idx: int  # global node index
    name: str
    tier: int
    loc: str
    alive: bool
    cores: int
    running: int
    queued: int  # queued + in transit
    est_wait: float  # s until a core is expected to be free
    speed: float  # speed for this task's type
    est_transfer: float  # s to move this task's inputs to the node
    ci: float  # gCO2/kWh now
    ci_f1: float  # forecast +1 h
    ci_f3: float  # forecast +3 h
    dyn_w: float  # dynamic W per busy core, incl. PUE
    allowed: bool
    is_origin: bool


@dataclass(slots=True)
class Ctx:
    now: float
    task: TaskView
    nodes: list
    can_defer: bool
    tod: float  # local hour of day
    util: float  # server utilisation 0..1
    sla_recent: float  # EWMA of recent class A/B misses
    c_ref: float  # reference carbon (g) of an average job of this class on the near fog
    extra: dict = field(default_factory=dict)
    cap: float = 1.0  # alive server cores (fog + cloud)


def est_exec(t: TaskView, n: NodeView) -> float:
    return t.work_est / max(n.speed, 1e-6)


def est_finish(c: Ctx, n: NodeView) -> float:
    return c.now + max(n.est_transfer, n.est_wait) + est_exec(c.task, n)


def carbon_est(c: Ctx, n: NodeView) -> float:
    """Estimated dynamic operational carbon (g) of running the task on node n."""
    return n.dyn_w * est_exec(c.task, n) / 3.6e6 * n.ci
