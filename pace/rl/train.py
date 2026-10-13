"""Train PACE: behaviour cloning from CA-EFT, then preference-conditioned PPO.

  python -m pace.rl.train --minutes 40 --workers 4 --out models/pace.pt

Rollouts run in parallel worker processes over domain-randomised topologies and
workloads (pace.config.randomized); w ~ U[0, 1] is sampled per episode.

Fine-tuning for the real testbed (calibrate -> fine-tune in the digital twin -> deploy):
  python -m pace.rl.train --init models/pace.pt --nodes testbed/nodes.json --out models/pace_live.pt --minutes 25
Reward per decision (attributed to the task it placed):
  r = -[(1 - w) * task_carbon / (task_work * fog_carbon_per_work) + w * (0.5 * task_penalty + 0.5 * job_penalty)]
  penalty = late * (1 + min(1, lateness / window)); task_penalty uses the task's sub-deadline
  (job deadline - estimated remaining critical path), job_penalty the job deadline.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from ..config import Workload, randomized, testbed_topology
from ..sched.heuristics import CAEFT
from ..sim.core import Simulator
from ..views import DEFER
from .features import F_N, F_T, K_MAX, featurize
from .model import PACENet

GAMMA, LAM = 0.8, 0.9  # short horizon: a decision is judged mainly by its own job


B_HEAVY = 0.0  # probability of a class-B-heavy, congested episode (set by --b-heavy)
TWIN = None  # calibrated testbed topology (set by --nodes)


def load_twin(path: str):
    from testbed.orchestrator import load_nodes
    return load_nodes(path)[0]


def make_sim(seed: int, horizon: float = 1200.0):
    rng = np.random.default_rng(seed)
    topo, wl = randomized(TWIN or testbed_topology(), Workload(split="train"), rng, twin=TWIN is not None)
    wl.horizon = horizon
    if rng.random() < B_HEAVY:  # analytics jobs are a small share of decisions; oversample them
        wl.frac_b = 0.85
        wl.rate_bc *= float(rng.uniform(1.0, 1.6))
    return Simulator(topo, wl, seed=seed)


def _rewards(steps, w, sim):
    """Per-decision reward with deadline decomposition.

    carbon : the decision's own task carbon, normalised per unit of work
             (~1 on the near fog, ~0.05 in Stockholm, ~4 on the edge)
    SLA    : half from the task's own sub-deadline (job deadline minus the estimated
             remaining critical path = the latest-finish time the scheduler sees), half
             from the job outcome. The sub-deadline term is attributable to the single
             decision; the job term keeps the true objective. Using only the job term
             (v1/v2) let PPO trade large-DAG deadlines for carbon and ignore w.
    """
    fog = next((n for n in sim.nodes if n.spec.tier == 1), sim.servers[0])
    c_unit = fog.dyn_w / 3.6e6 * sim.carbon.mean(fog.spec.zone)  # g per reference-core second on the fog
    r = np.zeros(len(steps), np.float32)
    for i, task in enumerate(steps):
        job = task.job
        js = job.spec
        miss = job.finish > js.deadline + 1e-9
        tard = max(0.0, job.finish - js.deadline) / max(js.deadline - js.arrival, 1e-6)
        pen_job = float(miss) * (1.0 + min(1.0, tard))
        lf = js.deadline - js.rem_cp[task.i]
        late = task.end - lf
        pen_task = float(late > 0) * (1.0 + min(1.0, late / max(lf - js.arrival, 1e-3)))
        carb = task.carbon / (max(task.spec.work, 1e-3) * c_unit)
        r[i] = -((1 - w) * carb + w * (0.5 * pen_task + 0.5 * pen_job))
    return r


def _gae(r, v):
    adv = np.zeros_like(r)
    last = 0.0
    for t in reversed(range(len(r))):
        nv = v[t + 1] if t + 1 < len(r) else 0.0
        delta = r[t] + GAMMA * nv - v[t]
        last = delta + GAMMA * LAM * last
        adv[t] = last
    return adv, adv + v


def rollout_worker(args):
    """Run episodes with the given policy until >= n_steps decisions; return training arrays."""
    state, n_steps, seed, mode, b_heavy, twin = args
    global B_HEAVY, TWIN
    B_HEAVY = b_heavy
    TWIN = load_twin(twin) if twin else None
    torch.set_num_threads(1)
    net = PACENet()
    if state is not None:
        net.load_state_dict(state)
    net.eval()
    rng = np.random.default_rng(seed)
    buf = {k: [] for k in ("xn", "xt", "m", "a", "logp", "adv", "ret", "cls")}
    stats = []
    teacher = CAEFT()
    total = 0
    ep = 0
    while total < n_steps:
        sim = make_sim(seed * 1000 + ep)
        ep += 1
        w = float(rng.uniform(0, 1))
        if mode == "bc":
            teacher.attach(sim)
        xs_n, xs_t, ms, acts, logps, vals, tasks = [], [], [], [], [], [], []
        while (ctx := sim.next_decision()) is not None:
            xn, xt, m = featurize(ctx, w)
            if mode == "bc":
                k = teacher.decide(ctx)
                a = K_MAX if k == DEFER else k
                lp = v = 0.0
            else:
                with torch.no_grad():
                    logits, val = net(torch.from_numpy(xn)[None], torch.from_numpy(xt)[None], torch.from_numpy(m)[None])
                    dist = torch.distributions.Categorical(logits=logits[0])
                    a_t = dist.sample()
                    a, lp, v = int(a_t), float(dist.log_prob(a_t)), float(val[0])
            xs_n.append(xn)
            xs_t.append(xt)
            ms.append(m)
            acts.append(a)
            logps.append(lp)
            vals.append(v)
            tasks.append(sim.cur)
            sim.apply(DEFER if a == K_MAX else a)
        s = sim.summary()
        r = _rewards(tasks, w, sim)
        adv, ret = _gae(r, np.asarray(vals, np.float32))
        buf["xn"].append(np.stack(xs_n))
        buf["xt"].append(np.stack(xs_t))
        buf["m"].append(np.stack(ms))
        buf["a"].append(np.asarray(acts))
        buf["logp"].append(np.asarray(logps, np.float32))
        buf["adv"].append(adv)
        buf["ret"].append(ret)
        buf["cls"].append(np.asarray([t.job.spec.cls for t in tasks], np.int64))
        stats.append(dict(w=w, steps=len(acts), R=float(r.sum()), sla_AB=s["sla_AB"], sla_B=s["sla_B"],
                          co2n=s["carbon_dyn"] / max(1e-12, sum(sim.c_ref[rr["cls"]] for rr in sim.records)),
                          defer=s["deferrals"]))
        total += len(acts)
    return {k: np.concatenate(v) for k, v in buf.items()}, stats


def _merge(results):
    data = {k: np.concatenate([r[0][k] for r in results]) for k in results[0][0]}
    stats = [s for r in results for s in r[1]]
    return data, stats


def evaluate(net, seeds=(11, 12), w=0.75, twin=None):
    from .agent import PACE
    out = []
    for sd in seeds:
        if twin is None:
            topo, wl = testbed_topology, Workload(split="train", horizon=1800, start_hour=10, rate_a=0.25, rate_bc=0.02)
        else:  # the real-testbed experiment settings (experiments.run_testbed)
            topo = lambda: load_twin(twin)  # noqa: E731
            wl = Workload(split="train", horizon=1800, start_hour=10, rate_a=0.25, rate_bc=0.075, work_scale=0.2,
                          data_scale=0.2, est_noise=0.2)
        r1 = Simulator(topo(), wl, seed=sd).run(PACE(net, w=w))
        r2 = Simulator(topo(), wl, seed=sd).run(CAEFT())
        out.append((r1["sla_A"], r1["sla_B"], r1["carbon_dyn"], r2["sla_A"], r2["sla_B"], r2["carbon_dyn"]))
    return np.mean(out, axis=0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=40)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument("--steps", type=int, default=6000, help="decisions per worker per iteration")
    ap.add_argument("--bc-iters", type=int, default=3)
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--out", default="models/pace.pt")
    ap.add_argument("--init", default=None)
    ap.add_argument("--b-heavy", type=float, default=0.0, help="share of class-B-heavy training episodes")
    ap.add_argument("--class-balance", action="store_true", help="equal PPO loss weight per job class")
    ap.add_argument("--nodes", default=None, help="train in the calibrated digital twin (testbed/nodes.json)")
    a = ap.parse_args()
    torch.manual_seed(0)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    net = PACENet()
    if a.init:
        net.load_state_dict(torch.load(a.init, weights_only=True))
    opt = torch.optim.Adam(net.parameters(), lr=a.lr)
    ctx = mp.get_context("spawn" if os.name == "nt" else "fork")
    log = []
    t_start = time.time()
    seed = 1
    with ctx.Pool(a.workers) as pool:
        # ---------------- behaviour cloning warm start (DeepRM2 idea) ----------------
        if not a.init:
            for it in range(a.bc_iters):
                res = pool.map(rollout_worker, [(None, a.steps, seed + i, "bc", 0.0, a.nodes) for i in range(a.workers)])
                seed += a.workers
                data, _ = _merge(res)
                n = len(data["a"])
                xn, xt, m = (torch.from_numpy(data[k]) for k in ("xn", "xt", "m"))
                y = torch.from_numpy(data["a"]).long()
                for _ep in range(3):
                    perm = torch.randperm(n)
                    for i in range(0, n, 1024):
                        b = perm[i:i + 1024]
                        logits, _ = net(xn[b], xt[b], m[b])
                        loss = F.cross_entropy(logits, y[b])
                        opt.zero_grad()
                        loss.backward()
                        opt.step()
                with torch.no_grad():
                    acc = (net(xn[:20000], xt[:20000], m[:20000])[0].argmax(-1) == y[:20000]).float().mean()
                print(f"[BC {it}] n={n} loss={loss.item():.3f} acc={acc:.3f} t={time.time() - t_start:.0f}s", flush=True)
            torch.save(net.state_dict(), a.out.replace(".pt", "_bc.pt"))
            ev = evaluate(net, twin=a.nodes)
            print(f"[BC eval w=.75] PACE A={ev[0]:.3f} B={ev[1]:.3f} CO2={ev[2]:.2f} | CA-EFT A={ev[3]:.3f} B={ev[4]:.3f} CO2={ev[5]:.2f}", flush=True)
        # ---------------- PPO ----------------
        it = 0
        while time.time() - t_start < a.minutes * 60:
            state = {k: v.clone() for k, v in net.state_dict().items()}
            res = pool.map(rollout_worker, [(state, a.steps, seed + i, "ppo", a.b_heavy, a.nodes) for i in range(a.workers)])
            seed += a.workers
            data, stats = _merge(res)
            n = len(data["a"])
            xn, xt, m = (torch.from_numpy(data[k]) for k in ("xn", "xt", "m"))
            act = torch.from_numpy(data["a"]).long()
            old_lp = torch.from_numpy(data["logp"])
            adv = torch.from_numpy(data["adv"])
            ret = torch.from_numpy(data["ret"])
            adv = (adv - adv.mean()) / (adv.std() + 1e-8)
            cls = torch.from_numpy(data["cls"])
            wts = torch.ones(n)
            if a.class_balance:
                counts = torch.bincount(cls, minlength=3).float().clamp(min=1)
                present = (counts > 1).sum()
                wts = (n / (present * counts))[cls]  # each present class gets equal total weight
                wts = wts / wts.mean()
            ent_coef = max(0.002, 0.01 * (1 - (time.time() - t_start) / (a.minutes * 60)))
            for _ep in range(a.epochs):
                perm = torch.randperm(n)
                for i in range(0, n, 2048):
                    b = perm[i:i + 2048]
                    logits, v = net(xn[b], xt[b], m[b])
                    dist = torch.distributions.Categorical(logits=logits)
                    lp = dist.log_prob(act[b])
                    ratio = torch.exp(lp - old_lp[b])
                    pg = -(wts[b] * torch.min(ratio * adv[b], torch.clamp(ratio, 0.8, 1.2) * adv[b])).mean()
                    vl = F.mse_loss(v, ret[b])
                    ent = dist.entropy().mean()
                    loss = pg + 0.5 * vl - ent_coef * ent
                    opt.zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(net.parameters(), 0.5)
                    opt.step()
            it += 1
            rec = dict(it=it, t=time.time() - t_start, n=n, R=float(np.mean([s["R"] / s["steps"] for s in stats])),
                       sla_AB=float(np.mean([s["sla_AB"] for s in stats])),
                       co2n=float(np.mean([s["co2n"] for s in stats])), defer=float(np.mean([s["defer"] for s in stats])),
                       pg=pg.item(), vl=vl.item(), ent=ent.item())
            if it % 3 == 0:
                ev = evaluate(net, twin=a.nodes)
                rec.update(evA=ev[0], evB=ev[1], evCO2=ev[2], refA=ev[3], refB=ev[4], refCO2=ev[5])
                torch.save(net.state_dict(), a.out.replace(".pt", f"_it{it}.pt"))
            log.append(rec)
            print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in rec.items()}), flush=True)
            torch.save(net.state_dict(), a.out)
    Path(a.out.replace(".pt", "_log.json")).write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
