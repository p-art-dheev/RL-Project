# PACE: carbon- and SLA-aware edge–cloud scheduling with deep RL

PACE (Preference-conditioned, Adaptive, Carbon-aware Edge scheduler) places every task of a job DAG on an **edge** device (Coimbatore), a **fog** node (AWS Mumbai, carbon-heavy grid, near) or a **cloud** node (AWS Stockholm, clean grid, far), **online and in about 1 ms per decision**. One policy covers the whole SLA-vs-carbon trade-off (`w`), and a feedback controller tracks an operator's SLA target at runtime.

- **Base paper to beat:** MERSEM (Ramicetty et al., arXiv:2605.13489, 2026), re-implemented in `pace/sched/mersem.py`.
- **RL lineage:** DeepRM (HotNets 2016) for online RL scheduling, and DeepRM2 (2018) for the behaviour-cloning warm start.
- **Design, paper critique, novelty:** [`docs/PROPOSAL.md`](docs/PROPOSAL.md)
- **How to run everything (laptop, AWS, demo):** [`docs/RUNBOOK.md`](docs/RUNBOOK.md)
- **Results:** [`results/RESULTS.md`](results/RESULTS.md) (simulation) and `results/testbed/` (real AWS)

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
experiments/         run_sim.py (E1-E5), run_testbed.py (E8), sim2real.py (E9), plots.py
```

## Quick start
```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m experiments.run_sim --exp E1 --seeds 5 --procs 4 && python -m experiments.plots
```

Dataset: S. A. Ali Rezaee, S. Adabi, *Jobs (DAG workflow) and tasks dataset*, Zenodo 10.5281/zenodo.4667690 (CC-BY-4.0).
