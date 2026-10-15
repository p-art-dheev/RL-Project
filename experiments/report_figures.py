"""Single-column figures for the IEEE report (report/ieee/figures/*.png), readable at 3.5 in width.

  python -m experiments.report_figures

Sources: results/sim/sim_all.csv (E1, E2), results/sim/sim_E6.csv (E6), results/sim/bc_ablation.json,
models/pace_log.json (training), results/REAL_TESTBED.md (E8b) and results/testbed/E9_SIM2REAL.md (E9).
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

OUT = Path("report/ieee/figures")
W = 3.5  # IEEE column width (inches)
plt.rcParams.update({"font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "legend.fontsize": 7,
                     "xtick.labelsize": 7, "ytick.labelsize": 7, "lines.linewidth": 1.4, "savefig.dpi": 300,
                     "axes.grid": True, "grid.alpha": 0.3, "axes.spines.top": False, "axes.spines.right": False})
C = {"PACE": "#1f5fa8", "PACE+shield": "#17a2b8", "CA-EFT": "#2a9d4b", "MERSEM": "#c0392b", "EFT": "#e67e22",
     "BC": "#8e44ad", "real": "#34495e", "twin": "#95a5a6"}


def sim_means(path, exp):
    g = defaultdict(list)
    for r in csv.DictReader(open(path)):
        if r["exp"] == exp:
            g[(r["scenario"], r["method"])].append(r)
    return {k: (100 * np.mean([float(r["sla_AB"]) for r in v]), np.mean([float(r["carbon_dyn"]) for r in v]))
            for k, v in g.items()}


def save(fig, name):
    fig.tight_layout(pad=0.3)
    fig.savefig(OUT / name, bbox_inches="tight")
    plt.close(fig)


def fig_training():
    log = json.load(open("models/pace_log.json"))
    it = np.array([r["it"] for r in log])
    R = np.array([r["R"] for r in log])
    ma = np.convolve(R, np.ones(7) / 7, mode="valid")
    ev = [r for r in log if "evA" in r]
    e = [r["it"] for r in ev]
    fig, ax = plt.subplots(3, 1, figsize=(W, 4.2), sharex=True)
    ax[0].plot(it, R, color=C["PACE"], alpha=0.3, lw=0.8, label="per iteration")
    ax[0].plot(it[3:-3], ma, color=C["PACE"], label="7-iteration mean")
    ax[0].set_ylabel("reward per\ndecision")
    ax[0].set_title("(a) training reward, w ~ U[0,1], randomised environments")
    ax[0].legend(loc="lower right", ncol=2)
    ax[1].plot(e, [r["evCO2"] for r in ev], "o-", ms=2.5, color=C["PACE"], label="PACE (w = 0.5)")
    ax[1].plot(e, [r["refCO2"] for r in ev], "--", color=C["CA-EFT"], label="CA-EFT (BC teacher)")
    ax[1].set_ylabel("carbon (g)")
    ax[1].set_title("(b) validation dynamic carbon")
    ax[1].legend(loc="upper right")
    ax[2].plot(e, [100 * r["evA"] for r in ev], "o-", ms=2.5, color=C["PACE"], label="PACE (w = 0.5)")
    ax[2].plot(e, [100 * r["refA"] for r in ev], "--", color=C["CA-EFT"], label="CA-EFT")
    ax[2].set_ylabel("alerts\nmissed (%)")
    ax[2].set_ylim(0, 1.5)
    ax[2].set_title("(c) validation alert (class A) misses")
    ax[2].set_xlabel("PPO iteration (after 3 behaviour-cloning iterations)")
    save(fig, "training.png")


def fig_tradeoff():
    m = sim_means("results/sim/sim_all.csv", "E1")
    s = "testbed nominal"
    bc = json.load(open("results/sim/bc_ablation.json"))
    fig, ax = plt.subplots(figsize=(W, 2.6))
    ws = ["0.0", "0.25", "0.5", "0.75", "0.9", "1.0"]
    p = [m[(s, f"PACE(w={w})")] for w in ws]
    ax.plot([x for x, _ in p], [y for _, y in p], "o-", color=C["PACE"], ms=4, label="PACE, one policy, w = 0 ... 1")
    for (x, y), w in zip(p, ws):
        if w in ("0.0", "0.25", "0.5", "1.0"):
            ax.annotate(f"w={float(w):g}", (x, y), textcoords="offset points", xytext=(4, -9 if w == "1.0" else 3), fontsize=6.5)
    ca = [m[(s, k)] for k in ("CA-EFT(m=0.25)", "CA-EFT", "CA-EFT(m=0.6)", "CA-EFT(m=0.8)", "CA-EFT(m=1.0)")]
    ca.sort()
    ax.plot([x for x, _ in ca], [y for _, y in ca], "s--", color=C["CA-EFT"], ms=3.5, label="CA-EFT, margin sweep")
    me = [m[(s, k)] for k in ("MERSEM-SLA", "MERSEM-Balanced", "MERSEM-Carbon")]
    ax.plot([x for x, _ in me], [y for _, y in me], "^:", color=C["MERSEM"], ms=4, label="MERSEM (base paper), 3 weights")
    for w, mk in (("PACE(w=0.9)", "D"),):
        rs = [r for r in bc if r["method"] == w]
        ax.plot(100 * np.mean([r["sla_AB"] for r in rs]), np.mean([r["carbon_dyn"] for r in rs]), mk, color=C["BC"],
                ms=5, label="behaviour cloning only (no PPO)")
    ax.set_xscale("log")
    ax.set_xticks([1, 2, 5, 10, 20])
    ax.set_xticklabels(["1", "2", "5", "10", "20"])
    ax.set_xlabel("deadlines missed, classes A+B (%, log scale)")
    ax.set_ylabel("dynamic carbon (g)")
    ax.legend(loc="upper left", fontsize=6.5)
    save(fig, "tradeoff.png")


def fig_load():
    m = sim_means("results/sim/sim_all.csv", "E2")
    loads = [0.0075, 0.015, 0.0225, 0.03]
    fig, ax = plt.subplots(figsize=(W, 2.2))
    for meth, lab, col, mk in (("MERSEM-Balanced", "MERSEM", C["MERSEM"], "^"), ("CA-EFT", "CA-EFT", C["CA-EFT"], "s"),
                               ("PACE(w=0.9)", "PACE", C["PACE"], "o"), ("PACE+shield(w=0.9)", "PACE + shield", C["PACE+shield"], "D")):
        ax.plot([lo / 0.015 for lo in loads], [m[(f"load rate_bc={lo}", meth)][0] for lo in loads], marker=mk, color=col,
                ms=4, label=lab)
    ax.set_xticks([0.5, 1, 1.5, 2])
    ax.set_xticklabels(["0.5x", "1x", "1.5x", "2x"])
    ax.set_xlabel("analytics and batch load (multiple of nominal)")
    ax.set_ylabel("deadlines missed (%)")
    ax.legend(ncol=2)
    save(fig, "load.png")


def fig_e6():
    m = sim_means("results/sim/sim_E6.csv", "E6")
    scen = [("seen: city nominal", "Seen city\n(8/3/4 nodes)"),
            ("unseen: 2x larger city (16/6/8 nodes)", "2x larger city"),
            ("unseen: cloud in Frankfurt (zone DE)", "Cloud in Frankfurt\n(unseen zone)"),
            ("unseen: 2x heavier jobs, 3x more data", "2x work,\n3x data"),
            ("unseen: slow WAN (RTT x2, bandwidth x0.3)", "Slow WAN\n(RTT x2, BW x0.3)")]
    meths = [("MERSEM-Balanced", "MERSEM", C["MERSEM"]), ("CA-EFT", "CA-EFT", C["CA-EFT"]), ("PACE(w=0.9)", "PACE", C["PACE"])]
    fig, ax = plt.subplots(figsize=(W, 2.9))
    y = np.arange(len(scen))[::-1]
    h = 0.26
    for i, (k, lab, col) in enumerate(meths):
        v = [m[(s, k)][0] for s, _ in scen]
        ax.barh(y + (1 - i) * h, v, h, color=col, label=lab)
        for yy, vv in zip(y + (1 - i) * h, v):
            ax.text(vv + 0.4, yy, f"{vv:.1f}", va="center", fontsize=6)
    ax.set_yticks(y, [lab for _, lab in scen])
    ax.set_xlabel("deadlines missed, classes A+B (%)")
    ax.set_xlim(0, 32)
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0)
    save(fig, "e6.png")


def fig_real():
    # E8b means from results/REAL_TESTBED.md (A+B missed %, 3 seeds per load)
    sched = ["MERSEM", "EFT", "CA-EFT", "PACE", "PACE+shield"]
    nominal = [9.4, 14.4, 3.7, 3.8, 6.1]
    busy = [14.3, np.nan, 6.2, 6.6, 4.6]
    fig, ax = plt.subplots(figsize=(W, 2.1))
    x = np.arange(len(sched))
    ax.bar(x - 0.19, nominal, 0.38, color=C["twin"], label="nominal load")
    ax.bar(x + 0.19, busy, 0.38, color=C["real"], label="busy hour (2x analytics)")
    for xx, a, b in zip(x, nominal, busy):
        ax.text(xx - 0.19, a + 0.3, f"{a:.1f}", ha="center", fontsize=6)
        if not np.isnan(b):
            ax.text(xx + 0.19, b + 0.3, f"{b:.1f}", ha="center", fontsize=6)
    ax.text(1.19, 0.6, "not\nrun", ha="center", fontsize=6)
    ax.set_xticks(x, ["MERSEM", "EFT", "CA-EFT", "PACE", "PACE\n+shield"])
    ax.set_ylabel("deadlines missed (%)")
    ax.legend()
    ax.grid(axis="x", alpha=0)
    save(fig, "real.png")


def fig_sim2real():
    rows = defaultdict(lambda: {"real": [], "twin": []})
    for line in Path("results/testbed/E9_SIM2REAL.md").read_text(encoding="utf-8").splitlines():
        mt = re.match(r"\| (adaptive|adaptive_busy)/e8_([a-z-]+)_s\d \| [^|]+ \| ([\d.]+)% \| ([\d.]+)% \|", line)
        if mt:
            rows[mt.group(2)]["real"].append(float(mt.group(3)))
            rows[mt.group(2)]["twin"].append(float(mt.group(4)))
    order = [("mersem", "MERSEM"), ("ca-eft", "CA-EFT"), ("pace", "PACE"), ("pace-shield", "PACE\n+shield")]
    fig, ax = plt.subplots(figsize=(W, 2.1))
    x = np.arange(len(order))
    tw = [np.mean(rows[k]["twin"]) for k, _ in order]
    rl = [np.mean(rows[k]["real"]) for k, _ in order]
    ax.bar(x - 0.19, tw, 0.38, color=C["twin"], label="twin prediction (simulator)")
    ax.bar(x + 0.19, rl, 0.38, color=C["real"], label="real AWS run")
    for xx, a, b in zip(x, tw, rl):
        ax.text(xx - 0.19, a + 0.3, f"{a:.1f}", ha="center", fontsize=6)
        ax.text(xx + 0.19, b + 0.3, f"{b:.1f}", ha="center", fontsize=6)
    ax.set_xticks(x, [lab for _, lab in order])
    ax.set_ylabel("deadlines missed (%)")
    ax.legend(loc="upper right")
    ax.grid(axis="x", alpha=0)
    save(fig, "sim2real.png")
    return {lab.replace("\n", " "): (round(a, 1), round(b, 1), len(rows[k]["real"])) for (k, lab), a, b in zip(order, tw, rl)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fig_training()
    fig_tradeoff()
    fig_load()
    fig_e6()
    fig_real()
    print("E9 twin vs real (A+B %, runs):", fig_sim2real())
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))


if __name__ == "__main__":
    main()
