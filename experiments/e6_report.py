"""E6 report: zero-shot generalisation to setups outside the training distribution.

  python -m experiments.run_sim --exp E6 --seeds 10 --procs 12
  python -m experiments.e6_report            # or --csv results/sim/sim_E6_real.csv --tag _real

Writes results/E6_GENERALISATION<tag>.md and results/plots/e6_generalisation<tag>.png.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy.stats import wilcoxon  # noqa: E402

from experiments.plots import ci, load, mcol  # noqa: E402

METHODS = ["MERSEM-Balanced", "MERSEM-SLA", "EFT", "CA-EFT", "PACE(w=0.9)", "PACE+shield(w=0.9)", "PACE+shield-target5%"]
LABEL = {"MERSEM-Balanced": "MERSEM-Balanced (base paper)", "PACE(w=0.9)": "PACE, w = 0.9",
         "PACE+shield(w=0.9)": "PACE + shield, w = 0.9", "PACE+shield-target5%": "PACE + shield, target 5%"}
PAIRS = [("PACE(w=0.9)", "MERSEM-Balanced"), ("PACE+shield(w=0.9)", "MERSEM-Balanced"),
         ("PACE(w=0.9)", "CA-EFT"), ("PACE+shield(w=0.9)", "CA-EFT")]


def pval(d):
    d = [x for x in d if abs(x) > 1e-12]
    return wilcoxon(d).pvalue if len(d) > 5 else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="results/sim/sim_E6.csv")
    ap.add_argument("--tag", default="")
    ap.add_argument("--carbon-note", default="carbon: SYNTHETIC hourly profiles")
    a = ap.parse_args()
    rows = [r for r in load(Path(a.csv)) if r["exp"] == "E6"]
    scen = list(dict.fromkeys(r["scenario"] for r in sorted(rows, key=lambda r: (not r["scenario"].startswith("seen"),))))
    by = {(r["scenario"], r["method"], int(r["seed"])): r for r in rows}
    seeds = sorted({int(r["seed"]) for r in rows})
    md = [f"# E6: generalisation to unseen setups (simulation, {len(seeds)} paired seeds)\n",
          f"> {a.carbon_note}. PACE (`models/pace.pt`) was trained on city topologies with 2-6 edge, 1-3 fog and 1-3 cloud "
          "nodes, Mumbai + Stockholm only, WAN RTT x0.7-1.5 and bandwidth x0.5-1.5 around the defaults, and the dataset's "
          "train split. Every setup below except the first is outside that range; nothing was retrained. "
          "All runs use the held-out test split; each seed is a different day, workload and carbon trace shared by every method.\n",
          "> **Change needed for the larger city:** the policy scores each node with a shared network, but the code had a fixed "
          "buffer of 12 candidate nodes (the training maximum). The buffer now grows with the topology; the weights are unchanged "
          "and results for 12 or fewer candidates are identical.\n"]
    for sc in scen:
        md += [f"\n## {sc}\n", "| Method | alerts missed % | analytics missed % | A+B missed % | carbon dyn (g) | p95 alert (s) | work edge/fog/cloud % |",
               "|---|---|---|---|---|---|---|"]
        for m in METHODS:
            rs = [by[(sc, m, s)] for s in seeds if (sc, m, s) in by]
            if not rs:
                continue
            f = lambda k, x=100: "%.1f ± %.1f" % tuple(x * v for v in ci([r[k] for r in rs]))
            split = "/".join("%.0f" % (100 * np.mean([r[k] for r in rs])) for k in ("share_edge", "share_fog", "share_cloud"))
            md.append(f"| {LABEL.get(m, m)} | {f('sla_A')} | {f('sla_B')} | **{f('sla_AB')}** | {f('carbon_dyn', 1)} | "
                      f"{np.mean([r['p95_A'] for r in rs]):.2f} | {split} |")
    md += ["\n## Paired comparison (Wilcoxon signed-rank over seeds; negative Δ = PACE better)\n",
           "| Setup | PACE variant | vs | better in | Δ A+B missed (pp) | p | Δ carbon dyn | p |", "|---|---|---|---|---|---|---|---|"]
    for sc in scen:
        for p, b in PAIRS:
            ss = [s for s in seeds if (sc, p, s) in by and (sc, b, s) in by]
            dm = [100 * (by[(sc, p, s)]["sla_AB"] - by[(sc, b, s)]["sla_AB"]) for s in ss]
            dc = [by[(sc, p, s)]["carbon_dyn"] - by[(sc, b, s)]["carbon_dyn"] for s in ss]
            cb = np.mean([by[(sc, b, s)]["carbon_dyn"] for s in ss])
            md.append(f"| {sc} | {LABEL.get(p, p)} | {LABEL.get(b, b)} | {sum(x < 0 for x in dm)}/{len(ss)} | "
                      f"{np.mean(dm):+.1f} | {pval(dm):.3f} | {100 * np.mean(dc) / cb:+.0f}% | {pval(dc):.3f} |")
    fig, ax = plt.subplots(1, 2, figsize=(15, 5))
    x = np.arange(len(scen))
    show = ["MERSEM-Balanced", "CA-EFT", "PACE(w=0.9)", "PACE+shield(w=0.9)"]
    wdt = 0.8 / len(show)
    for i, m in enumerate(show):
        for j, (k, mult) in enumerate((("sla_AB", 100), ("carbon_dyn", 1))):
            vals = [ci([mult * by[(sc, m, s)][k] for s in seeds if (sc, m, s) in by]) for sc in scen]
            ax[j].bar(x + (i - 1.5) * wdt, [v[0] for v in vals], wdt, yerr=[v[1] for v in vals], label=LABEL.get(m, m),
                      color=mcol(m), capsize=3)
    for j, t in enumerate(("deadlines missed, classes A+B (%)", "dynamic carbon (g)")):
        ax[j].set_xticks(x, [s.replace(": ", ":\n").replace(" (", "\n(") for s in scen], fontsize=8)
        ax[j].set_title(t)
        ax[j].grid(axis="y", alpha=.3)
    ax[0].legend(fontsize=8)
    fig.suptitle(f"E6: zero-shot generalisation ({a.carbon_note})", fontsize=10)
    fig.tight_layout()
    out = Path(f"results/plots/e6_generalisation{a.tag}.png")
    fig.savefig(out, dpi=130)
    md.insert(3, f"\n![E6](plots/{out.name})\n")
    Path(f"results/E6_GENERALISATION{a.tag}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("wrote", f"results/E6_GENERALISATION{a.tag}.md", out)


if __name__ == "__main__":
    main()
