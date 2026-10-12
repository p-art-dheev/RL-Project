"""Figures + results table from results/sim/sim_all.csv (and testbed runs if present).

  python -m experiments.plots
Writes results/plots/*.png and results/RESULTS.md.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy.stats import wilcoxon  # noqa: E402

SIM = Path("results/sim/sim_all.csv")
PLOTS = Path("results/plots")
COL = {"PACE": "#1f77b4", "MERSEM": "#d62728", "CA-EFT": "#2ca02c", "EFT": "#ff7f0e", "other": "#7f7f7f"}
SYN = "carbon: SYNTHETIC hourly profiles (replace with Electricity Maps data)"


def fam(m):
    return "PACE" if m.startswith("PACE") else "MERSEM" if m.startswith("MERSEM") else m if m in COL else "other"


def load(path=SIM):
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        for k, v in r.items():
            try:
                r[k] = float(v)
            except (TypeError, ValueError):
                pass
    return rows


def group(rows, exp, scen=None):
    g = defaultdict(list)
    for r in rows:
        if r["exp"] == exp and (scen is None or r["scenario"] == scen):
            g[r["method"]].append(r)
    return g


def ci(x):
    x = np.asarray(x, float)
    return x.mean(), 1.96 * x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0.0


def hv2d(points, ref):
    """2-D hypervolume (minimisation) of a point set w.r.t. reference point."""
    pts = sorted([p for p in points if p[0] < ref[0] and p[1] < ref[1]])
    hv, best_y = 0.0, ref[1]
    for x, y in pts:
        if y < best_y:
            hv += (ref[0] - x) * (best_y - y)
            best_y = y
    return hv


def fig_e1(rows, scen, tag, md):
    g = group(rows, "E1", scen)
    order = [m for m in ["Random", "Edge-only", "Fog-only", "Cloud-only", "Carbon-greedy", "EFT", "Job-EFT", "CA-EFT",
                         "MERSEM-Carbon", "MERSEM-Balanced", "MERSEM-SLA", "MERSEM-Balanced-Oracle", "PACE-joblevel",
                         "PACE(w=0.25)", "PACE(w=0.5)", "PACE(w=0.75)", "PACE(w=0.9)", "PACE-target5%", "PACE-target2%"] if m in g]
    fig, ax = plt.subplots(1, 3, figsize=(17, 5.2))
    for i, (key, lab) in enumerate([("sla_A", "Alert (class A) SLA violation %"), ("sla_B", "Analytics (class B) SLA violation %"),
                                    ("carbon_dyn", "Operational carbon, dynamic (gCO2 / hour)")]):
        mu = [ci([r[key] * (100 if key != "carbon_dyn" else 1) for r in g[m]]) for m in order]
        ax[i].barh(range(len(order)), [m for m, _ in mu], xerr=[c for _, c in mu], color=[COL[fam(m)] for m in order])
        ax[i].set_yticks(range(len(order)))
        ax[i].set_yticklabels(order if i == 0 else [""] * len(order), fontsize=9)
        ax[i].set_title(lab, fontsize=10)
        ax[i].invert_yaxis()
        ax[i].grid(axis="x", alpha=.3)
    fig.suptitle(f"E1 {scen}: mean ± 95% CI over {len(g[order[0]])} seeds  ({SYN})", fontsize=10)
    fig.tight_layout()
    fig.savefig(PLOTS / f"e1_{tag}.png", dpi=130)
    plt.close(fig)
    # table
    md.append(f"\n### E1 — {scen} ({len(g[order[0]])} paired seeds, mean ± 95% CI)\n")
    md.append("| Method | SLA A % | SLA B % | SLA A+B % | Carbon dyn (g) | Carbon total (g) | p95 alert latency (s) | Work edge/fog/cloud | Decision (ms) |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for m in order:
        rs = g[m]
        f = lambda k, s=1: "{:.2f} ± {:.2f}".format(*[v * s for v in ci([r[k] for r in rs])])
        dm = np.mean([r["decide_ms"] for r in rs if isinstance(r.get("decide_ms"), float)] or [float("nan")])
        sh = "/".join(f"{np.mean([r[k] for r in rs]) * 100:.0f}" for k in ("share_edge", "share_fog", "share_cloud"))
        md.append(f"| {m} | {f('sla_A', 100)} | {f('sla_B', 100)} | {f('sla_AB', 100)} | {f('carbon_dyn')} | "
                  f"{f('carbon_total')} | {f('p95_A')} | {sh} | {'' if np.isnan(dm) else f'{dm:.2f}'} |")
    # paired comparisons
    md.append("\n**Paired comparison (Wilcoxon signed-rank over seeds).** Negative Δ = PACE better.\n")
    md.append("| PACE variant | vs | Δ SLA A+B (pp) | p | Δ carbon dyn | p |")
    md.append("|---|---|---|---|---|---|")
    for p in [m for m in ("PACE(w=0.5)", "PACE(w=0.75)", "PACE-target5%") if m in g]:
        for b in [m for m in ("MERSEM-Balanced", "MERSEM-SLA", "MERSEM-Balanced-Oracle", "CA-EFT", "EFT") if m in g]:
            A = {r["seed"]: r for r in g[p]}
            B = {r["seed"]: r for r in g[b]}
            seeds = sorted(set(A) & set(B))
            ds = [100 * (A[s]["sla_AB"] - B[s]["sla_AB"]) for s in seeds]
            dc = [A[s]["carbon_dyn"] - B[s]["carbon_dyn"] for s in seeds]
            rel = 100 * np.mean(dc) / max(1e-12, np.mean([B[s]["carbon_dyn"] for s in seeds]))
            pv = lambda d: wilcoxon(d).pvalue if len(d) > 5 and any(abs(x) > 1e-12 for x in d) else float("nan")
            md.append(f"| {p} | {b} | {np.mean(ds):+.2f} | {pv(ds):.3g} | {rel:+.1f}% | {pv(dc):.3g} |")


def fig_pareto(rows, scen, tag, md):
    g = group(rows, "E1", scen)
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    pts = {m: (100 * np.mean([r["sla_AB"] for r in v]), np.mean([r["carbon_dyn"] for r in v])) for m, v in g.items()}
    pace = [m for m in ("PACE(w=0.0)", "PACE(w=0.25)", "PACE(w=0.5)", "PACE(w=0.75)", "PACE(w=0.9)", "PACE(w=1.0)") if m in pts]
    mers = [m for m in ("MERSEM-Carbon", "MERSEM-Balanced", "MERSEM-SLA") if m in pts]
    ax.plot([pts[m][0] for m in pace], [pts[m][1] for m in pace], "o-", color=COL["PACE"], label="PACE (one policy, w sweep)")
    for m in pace:
        ax.annotate(m.replace("PACE", ""), pts[m], fontsize=8, xytext=(4, 4), textcoords="offset points")
    ax.plot([pts[m][0] for m in mers], [pts[m][1] for m in mers], "s--", color=COL["MERSEM"], label="MERSEM (base paper)")
    for m in mers:
        ax.annotate(m.replace("MERSEM-", ""), pts[m], fontsize=8, xytext=(4, -10), textcoords="offset points", color=COL["MERSEM"])
    for m in ("EFT", "CA-EFT", "Carbon-greedy", "Cloud-only", "Fog-only", "Job-EFT"):
        if m in pts:
            ax.scatter(*pts[m], marker="^", color=COL.get(m, COL["other"]))
            ax.annotate(m, pts[m], fontsize=8, xytext=(4, 4), textcoords="offset points")
    allp = list(pts.values())
    ref = (max(p[0] for p in allp) * 1.05 + 1e-9, max(p[1] for p in allp) * 1.05 + 1e-9)
    hv_p = hv2d([pts[m] for m in pace], ref)
    hv_m = hv2d([pts[m] for m in mers], ref)
    ax.set_xlabel("SLA violation rate, classes A+B (%)")
    ax.set_ylabel("Operational carbon, dynamic (gCO2)")
    ax.set_title(f"Pareto front, {scen}\nhypervolume: PACE {hv_p:.3g} vs MERSEM {hv_m:.3g}", fontsize=10)
    ax.set_xscale("symlog", linthresh=1)
    ax.grid(alpha=.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(PLOTS / f"pareto_{tag}.png", dpi=130)
    plt.close(fig)
    md.append(f"\n**Pareto hypervolume ({scen}, ref = 1.05 × worst point):** PACE {hv_p:.4g} vs MERSEM {hv_m:.4g} "
              f"({100 * (hv_p / max(hv_m, 1e-12) - 1):+.0f}%).\n")


def fig_sweep(rows, exp, xname, parse, fname, md):
    scen = sorted({r["scenario"] for r in rows if r["exp"] == exp}, key=parse)
    if not scen:
        return
    meths = sorted({r["method"] for r in rows if r["exp"] == exp})
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    md.append(f"\n### {exp} — {xname}\n")
    md.append("| " + xname + " | " + " | ".join(meths) + " |")
    md.append("|---" * (len(meths) + 1) + "|")
    table = defaultdict(dict)
    for m in meths:
        xs, s, c = [], [], []
        for sc in scen:
            rs = [r for r in rows if r["exp"] == exp and r["scenario"] == sc and r["method"] == m]
            if not rs:
                continue
            xs.append(parse(sc))
            s.append(ci([100 * r["sla_AB"] for r in rs]))
            c.append(ci([r["carbon_dyn"] for r in rs]))
            table[sc][m] = f"{s[-1][0]:.1f}% / {c[-1][0]:.2f}g"
        col = COL[fam(m)] if fam(m) != "PACE" or m == "PACE(w=0.5)" else "#17becf"
        ax[0].errorbar(xs, [a for a, _ in s], yerr=[b for _, b in s], marker="o", label=m, color=col, capsize=3)
        ax[1].errorbar(xs, [a for a, _ in c], yerr=[b for _, b in c], marker="o", label=m, color=col, capsize=3)
    for sc in scen:
        md.append(f"| {parse(sc)} | " + " | ".join(table[sc].get(m, "") for m in meths) + " |")
    ax[0].set_ylabel("SLA violation A+B (%)")
    ax[1].set_ylabel("Carbon dynamic (g)")
    for a in ax:
        a.set_xlabel(xname)
        a.grid(alpha=.3)
    ax[0].legend(fontsize=8)
    fig.suptitle(f"{exp}: {xname} (SLA % / carbon g per cell in RESULTS.md)", fontsize=10)
    fig.tight_layout()
    fig.savefig(PLOTS / fname, dpi=130)
    plt.close(fig)


def fig_timeseries(rows, exp, fname, md):
    scen = sorted({r["scenario"] for r in rows if r["exp"] == exp})
    if not scen:
        return
    fig, axes = plt.subplots(1, len(scen), figsize=(7 * len(scen), 4.5), squeeze=False)
    md.append(f"\n### {exp}\n")
    md.append("| Scenario | Method | SLA A+B % | Carbon dyn (g) |")
    md.append("|---|---|---|---|")
    for ax, sc in zip(axes[0], scen):
        for m in sorted({r["method"] for r in rows if r["exp"] == exp and r["scenario"] == sc}):
            rs = [r for r in rows if r["exp"] == exp and r["scenario"] == sc and r["method"] == m]
            ts = np.array([json.loads(r["ts_miss"]) for r in rs])
            ax.plot(np.arange(ts.shape[1]) * 2, 100 * ts.mean(0), label=m, color=COL[fam(m)] if m in ("CA-EFT", "EFT") or fam(m) != "PACE" or m == "PACE(w=0.5)" else None)
            md.append(f"| {sc} | {m} | {ci([100 * r['sla_AB'] for r in rs])[0]:.2f} | {ci([r['carbon_dyn'] for r in rs])[0]:.3f} |")
        ax.set_title(sc, fontsize=10)
        ax.set_xlabel("job arrival time (min)")
        ax.set_ylabel("SLA violations A+B (%)")
        ax.grid(alpha=.3)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(PLOTS / fname, dpi=130)
    plt.close(fig)


def fig_training(md):
    p = Path("models/pace_log.json")
    if not p.exists():
        return
    log = json.loads(p.read_text())
    ev = [r for r in log if "evCO2" in r]
    fig, ax = plt.subplots(1, 3, figsize=(15, 4))
    it = [r["it"] for r in log]
    ax[0].plot(it, [r["R"] for r in log], alpha=.6)
    ax[0].set_title("mean reward per decision (randomised train envs)")
    ax[1].plot([r["it"] for r in ev], [r["evCO2"] for r in ev], "o-", label="PACE w=0.5")
    ax[1].plot([r["it"] for r in ev], [r["refCO2"] for r in ev], "--", label="CA-EFT")
    ax[1].set_title("validation carbon (g)")
    ax[2].plot([r["it"] for r in ev], [100 * (r["evA"] + r["evB"]) / 2 for r in ev], "o-", label="PACE w=0.5")
    ax[2].plot([r["it"] for r in ev], [100 * (r["refA"] + r["refB"]) / 2 for r in ev], "--", label="CA-EFT")
    ax[2].set_title("validation SLA violation (mean of A,B) %")
    for a in ax:
        a.set_xlabel("PPO iteration")
        a.grid(alpha=.3)
    ax[1].legend()
    fig.tight_layout()
    fig.savefig(PLOTS / "training.png", dpi=130)
    plt.close(fig)


def main():
    PLOTS.mkdir(parents=True, exist_ok=True)
    rows = load()
    md = ["# PACE results (simulation)\n", f"> {SYN}. All runs use the dataset's held-out test split; "
          "each seed is a different day/hour, workload and carbon trace shared by every method.\n"]
    for scen, tag in (("testbed nominal", "testbed"), ("city nominal", "city")):
        if any(r["exp"] == "E1" and r["scenario"] == scen for r in rows):
            fig_e1(rows, scen, tag, md)
            fig_pareto(rows, scen, tag, md)
    fig_sweep(rows, "E2", "load (class B/C jobs per s)", lambda s: float(s.split("=")[1]), "e2_load.png", md)
    fig_sweep(rows, "E3", "runtime-estimate noise sigma", lambda s: float(s.split("=")[1]), "e3_noise.png", md)
    fig_timeseries(rows, "E4", "e4_failures.png", md)
    fig_timeseries(rows, "E5", "e5_rush_hour.png", md)
    fig_training(md)
    Path("results/RESULTS.md").write_text("\n".join(md) + "\n")
    print("wrote results/RESULTS.md and", sorted(p.name for p in PLOTS.glob("*.png")))


if __name__ == "__main__":
    main()
