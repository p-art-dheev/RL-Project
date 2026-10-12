"""E9: sim-to-real fidelity. For every real testbed run (results/testbed/e8_*.json), replay
the identical job trace in the simulator configured with the calibrated topology
(testbed/nodes.json) and compare outcomes.

  python -m experiments.sim2real
Writes results/testbed/E9_SIM2REAL.md and results/plots/e9_latency_cdf.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy.stats import ks_2samp  # noqa: E402

from pace.config import Workload  # noqa: E402
from pace.sim.core import Simulator  # noqa: E402
from pace.workload import generate  # noqa: E402
from testbed.orchestrator import load_nodes, make_scheduler  # noqa: E402


class _Args:
    def __init__(self, d):
        self.__dict__.update(d)


def replay(run: dict, nodes: str):
    a = _Args(run["args"])
    topo, _tok = load_nodes(nodes)
    wl = Workload(split="test", horizon=a.minutes * 60, start_hour=a.start_hour, rate_a=a.rate_a, rate_bc=a.rate_bc,
                  work_scale=a.work_scale, data_scale=a.work_scale, est_noise=a.est_noise, carbon_source=a.carbon)
    if a.camera:
        wl.rate_a = 0.0
    jobs = generate(topo, wl, np.random.default_rng(a.seed), a.start_hour)  # same RNG path as the orchestrator
    sim = Simulator(topo, wl, seed=a.seed, jobs=[j for j in jobs if j.arrival < a.minutes * 60])
    return sim.run(make_scheduler(a)), sim.records


def main():
    runs = sorted(Path("results/testbed").glob("e8_*.json"))
    if not runs:
        print("no testbed runs found in results/testbed/ (run experiments.run_testbed first)")
        return
    lines = ["| run | jobs real/sim | SLA A+B real | SLA A+B sim | p95 alert real | p95 alert sim | KS(latency A) | KS(latency B) |",
             "|---|---|---|---|---|---|---|---|"]
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for i, p in enumerate(runs):
        run = json.loads(p.read_text())
        s_sum, s_rec = replay(run, "testbed/nodes.json")
        r_rec = run["records"]
        ks = []
        for c in (0, 1):
            lr = [r["latency"] for r in r_rec if r["cls"] == c]
            ls = [r["latency"] for r in s_rec if r["cls"] == c]
            ks.append(ks_2samp(lr, ls).statistic if lr and ls else float("nan"))
            if i < 4:
                for data, style in ((lr, "-"), (ls, "--")):
                    if data:
                        x = np.sort(data)
                        ax[c].plot(x, np.arange(1, len(x) + 1) / len(x), style, label=f"{p.stem} {'real' if style == '-' else 'sim'}")
        rs = run["summary"]
        lines.append(f"| {p.stem} | {rs['jobs']}/{s_sum['jobs']} | {100 * rs['sla_AB']:.1f}% | {100 * s_sum['sla_AB']:.1f}% | "
                     f"{rs['p95_A']:.2f}s | {s_sum['p95_A']:.2f}s | {ks[0]:.2f} | {ks[1]:.2f} |")
    for c, t in enumerate(("class A (alert) latency CDF", "class B (analytics) latency CDF")):
        ax[c].set_title(t)
        ax[c].set_xlabel("latency (s)")
        ax[c].grid(alpha=.3)
        ax[c].legend(fontsize=6)
    Path("results/plots").mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig("results/plots/e9_latency_cdf.png", dpi=130)
    text = "# E9 — sim-to-real fidelity (same job trace, calibrated simulator vs real AWS)\n\n" + "\n".join(lines) + \
        "\n\nKS = Kolmogorov-Smirnov distance between real and simulated latency distributions (0 = identical).\n"
    Path("results/testbed/E9_SIM2REAL.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
