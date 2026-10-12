# Models

| File | What it is | Loads with current code? |
|---|---|---|
| `pace.pt` | **Final PACE policy (v5)**: 20 task features (incl. job pressure), trained with deadline-decomposition reward, class-balanced PPO and class-priority queues. Used by all results in `results/RESULTS.md` and by the testbed. | yes |
| `pace_bc.pt` | Behaviour-cloning warm start for v5 (imitates CA-EFT). `python -m pace.rl.train --init models/pace_bc.pt` | yes |
| `pace_log.json` | Training log of the final model (plotted in `results/plots/training.png`). | n/a |
| `pace_v3.pt` | Reward v3 (deadline decomposition), 18 task features; results in `results/RESULTS_v3.md`. | no: needs the 18-feature code (commit "Reward v3 ...") |
| `pace_v2.pt` | Reward v2 (full job penalty per decision). Historical. | no |
| `pace_v1_weak.pt` | Reward v1 (job penalty split over tasks). It ignored `w` and missed 45% of analytics deadlines on held-out data. Historical. | no |

The training logs of every round are in `results/training_logs/` (v1 to v5). The development history and the reasons for each change are in `docs/PROPOSAL.md` §0.1.
