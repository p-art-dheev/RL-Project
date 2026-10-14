# PACE: carbon- and SLA-aware edge–cloud scheduling with deep RL

PACE (Preference-conditioned, Adaptive, Carbon-aware Edge scheduler) places every task of a job DAG on an **edge** device (Coimbatore), a **fog** node (AWS Mumbai, carbon-heavy grid, near) or a **cloud** node (AWS Stockholm, clean grid, far), **online, in about 0.5 ms per decision**. One policy covers the whole SLA-vs-carbon trade-off (`w`), and a feedback controller tracks an operator's SLA target at runtime.

- **Base paper to beat:** MERSEM (Ramicetty et al., arXiv:2605.13489, 2026), re-implemented in `pace/sched/mersem.py`.
- **RL lineage:** DeepRM (HotNets 2016) for online RL scheduling, and DeepRM2 (2018) for the behaviour-cloning warm start.
- **Design, paper critique, novelty:** [`docs/PROPOSAL.md`](docs/PROPOSAL.md)
- **How to run everything (laptop, AWS, demo):** [`docs/RUNBOOK.md`](docs/RUNBOOK.md)
- **Results:** [`results/RESULTS.md`](results/RESULTS.md) (simulation) and [`results/REAL_TESTBED.md`](results/REAL_TESTBED.md) (real AWS)

## Headline results (simulation, held-out jobs, 10 paired seeds, testbed topology)

| Method | Alert misses | Analytics misses | All jobs (MERSEM metric) | Dynamic gCO₂ |
|---|---|---|---|---|
| MERSEM-Balanced (base paper, re-implemented) | 12.7% | 45.4% | 13.3% | 0.51 |
| CA-EFT (tuned carbon-aware heuristic) | 2.8% | 5.6% | 2.8% | 0.74 |
| **PACE, w = 0.9** | **0.9%** | 23.1% | **1.3%** | **0.39** |
| **PACE + shield, w = 1** | 1.8% | 6.0% | 1.9% | 0.55 |

- **PACE vs MERSEM:** −12 pp SLA violations and −22% dynamic carbon (Wilcoxon p = 0.002). On the larger city topology: −17 pp and −34%.
- **PACE + shield vs CA-EFT:** better on alerts, equal on analytics (within the CI), −26% carbon (p = 0.002). Pure PACE misses more large analytics jobs; see `results/RESULTS.md` for the per-class discussion.
- Under rush hours, node crashes, random failures, 2× load and ±40% runtime-estimate noise, a PACE variant has the fewest violations in every scenario. PACE + shield beats both CA-EFT and MERSEM in each one, with less carbon than CA-EFT.
- **Unseen setups, no retraining (E6):** on a 2× larger city, a cloud moved to Frankfurt (a grid zone never seen) and 2× heavier jobs, PACE beats MERSEM by 15–25 pp and CA-EFT by 2–5 pp in 10/10 seeds (p = 0.002), with less carbon than both. **It fails on a much slower WAN** (RTT ×2, bandwidth ×0.3): 17% missed vs CA-EFT's 1.4%, because it keeps sending alerts to Stockholm. See `results/E6_GENERALISATION.md`.
- Carbon intensities are **synthetic** hourly profiles built from real annual means (free hourly data for the Indian grid zones was not available; Electricity Maps CSVs can be dropped into `data/carbon/`).

## Headline results (real AWS testbed: laptop edge in Coimbatore, EC2 Mumbai + Stockholm)

With the online network estimate (E8b), 6-minute runs, schedulers interleaved per seed, 3 seeds per load:

| Method | Missed (nominal load) | Missed (busy hour) | Dynamic gCO₂ nominal / busy |
|---|---|---|---|
| MERSEM-Balanced (base paper) | 9.4% | 14.3% | 0.037 / 0.063 |
| CA-EFT | 3.7% | 6.2% | 0.051 / 0.083 |
| EFT | 14.4% | – | 0.282 / – |
| **PACE, w = 0.9** | **3.8%** | 6.6% | 0.044 / 0.067 |
| **PACE + shield, w = 0.9** | 6.1% | **4.6%** (0 alerts missed) | 0.050 / 0.069 |

- **PACE vs MERSEM:** fewer missed deadlines in all 6 paired runs (−6.6 pp, Wilcoxon p = 0.031), for +15% carbon on average (not significant).
- **PACE vs CA-EFT:** the same deadline performance with 15% less carbon (p = 0.031).
- The testbed exposed three sim-to-real gaps, each fixed and documented: the dispatch model (tasks now overlap transfers and computation), SMT contention (2 x86 vCPUs = 1 core: 1.75× slower when both busy, measured by `calibrate`), and network drift to Mumbai over the evening (online latency estimate). PACE was fine-tuned in the calibrated digital twin (`models/pace_live.pt`). Details: `results/testbed/E8_ANALYSIS.md`, `results/testbed/TWIN_PREDICTION.md`.

## Layout
```
pace/
  data/rezaee.py     parser for the MERSEM dataset (Zenodo 4667690, CC-BY-4.0); sample in data/processed/
  workload.py        smart-city job classes: A camera alerts, B graph analytics, C deferrable batch
  carbon.py          hourly grid carbon intensity (synthetic, or Electricity Maps CSVs)
  sim/core.py        discrete-event edge-fog-cloud DAG simulator (transfers, contention, failures)
  views.py           decision context shared by the simulator and the real orchestrator
  sched/heuristics.py  EFT, CA-EFT, carbon-greedy, edge/fog/cloud-only, Job-EFT, random
  sched/mersem.py    MERSEM: evolutionary search + Q-learning-guided local search, job-level
  rl/                PACE: features, size-agnostic policy, BC + PPO training, deployable agent + SLA controller
testbed/
  worker.py          real task executor (BLAS kernel, OpenCV HOG pedestrian detection)
  orchestrator.py    live scheduler runtime + dashboard (same scheduler code as the simulator)
  aws.py             deploy / stop / start / destroy workers in ap-south-1 + eu-north-1 (Free-plan types)
  calibrate.py       measures node speeds and real RTT / bandwidth
  camera.py          webcam / phone / video frames -> class-A jobs
  local.py           edge workers on the laptop (or a fully local rehearsal)
experiments/         run_sim.py (E1-E5), run_testbed.py (E8), sim2real.py (E9), plots.py,
                     twin_check.py (predict E8 in the calibrated twin), testbed_report.py (real-AWS report)
```

## Quick start
```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m experiments.run_sim --exp E1 --seeds 5 --procs 4 && python -m experiments.plots
```

Dataset: S. A. Ali Rezaee, S. Adabi, *Jobs (DAG workflow) and tasks dataset*, Zenodo 10.5281/zenodo.4667690 (CC-BY-4.0).
