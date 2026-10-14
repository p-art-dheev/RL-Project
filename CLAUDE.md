# PACE project: working notes for Claude

## Rules from the owner (always follow)
- Work on `main` only. Never create other branches, and never branches named after Claude.
- Commit and push progress to GitHub as the owner: `git config user.name "p-art-dheev"`,
  `git config user.email "pardheev.vatturu1234@gmail.com"`. Do not add Claude as a co-author and add no trailers.
- The owner runs Windows 11 (HP Victus, i5-12th gen, RTX 3050), PowerShell, from
  `C:\Users\PARDHEEV\MyGitHubRepos\RL-Project` with the venv `rl-project-venv`. Every new terminal:
  `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` then `.\rl-project-venv\Scripts\Activate.ps1`.
- Explain simply and step by step, and say which terminal each command goes in. Stick to the project.

## What this is
PACE: preference-conditioned, adaptive, carbon-aware edge-cloud scheduler (PPO, task-level DAG placement,
safety shield, SLA-target controller). Base paper to beat: MERSEM (arXiv:2605.13489), re-implemented in
`pace/sched/mersem.py`. Real testbed: laptop edge workers (Coimbatore) + EC2 in Mumbai (fog) and Stockholm (cloud).
- Overview and headline numbers: `README.md`. Design and viva Q&A: `docs/PROPOSAL.md`. How to run: `docs/RUNBOOK.md`.
- Simulation results: `results/RESULTS.md`. Real AWS results: `results/REAL_TESTBED.md` (+ `results/plots/e8_real.png`).
- What the real testbed taught us (three sim-to-real gaps and fixes): `results/testbed/E8_ANALYSIS.md`,
  `results/testbed/TWIN_PREDICTION.md`; excluded runs and why: `results/testbed/invalid/README.md`.
- Slide deck (17 slides): https://claude.ai/artifact/X9Ky61KvcCb7Ujkd247Ceh; sources mirrored in `docs/slides/project/`.
- Animated methodology page: `docs/methodology.html`.

## State on 2026-10-14
- Done: simulation E1-E7; real AWS E8 (static estimates), E8b nominal + busy hour (online network estimate), E9
  sim-to-real; report, figure and deck updated. Live runs use `models/pace_live.pt` (fine-tuned in the calibrated twin).
- Headline (real AWS, E8b): PACE missed fewer deadlines than MERSEM in all 6 paired runs (-6.6 pp, p = 0.031) at +15%
  carbon (not significant); same deadline performance as CA-EFT with 15% less carbon (p = 0.031).
- Testbed: 4 EC2 instances were left running (pace-bom-x86/arm in ap-south-1, pace-arn-x86/arm in eu-north-1), deployed
  with the current worker code and calibrated. `testbed/nodes.json` (gitignored, holds the access token) is on the laptop.
- Remaining: rehearse the live demo (RUNBOOK section 5; `walk.mp4` in the repo root is the backup camera video,
  `python -m testbed.camera --source walk.mp4 --camera edge0 --fps 2`); fill the deck cover placeholders
  ([Your name], [Course], [Professor]); `python -m testbed.aws stop` at the end of each day, `aws down` after presenting.

## Testbed gotchas (learned the hard way)
- Cloudflare WARP (1.1.1.1 app) must be off: AWS then sees 104.28.x.x and blocks the laptop.
- The campus network uses 4 public IPs: use `python -m testbed.aws up --wide` / `allow --wide`.
- Start the edge workers (`python -m testbed.local --edges 2`, its own terminal) after `aws up`: it reads the new token.
- After `aws start`: `allow --wide`, restart the edge workers, `python -m testbed.calibrate`.
- Worker code is shipped at launch (EC2 user-data): a change to `testbed/worker.py` needs `aws down` + `aws up --wide`.
  Orchestrator, scheduler and experiment changes need only `git pull` on the laptop.
- Never run two orchestrators against the same nodes, and never `git pull` while an experiment chain is running.
- Predict a run in the calibrated twin first: `python -m experiments.twin_check`. Real-AWS report:
  `python -m experiments.testbed_report`.
