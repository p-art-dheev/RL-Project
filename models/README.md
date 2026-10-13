# Models

| File | What it is | Loads with current code? |
|---|---|---|
| `pace.pt` | **Final PACE policy (v5)**: 20 task features (incl. job pressure), trained with deadline-decomposition reward, class-balanced PPO and class-priority queues. Used by all results in `results/RESULTS.md` and by the testbed. | yes |
| `pace_live.pt` | **PACE fine-tuned for the real AWS testbed**: `pace.pt` further trained in the calibrated digital twin (`python -m pace.rl.train --init ... --nodes testbed/twin.json`), three stages as the twin was corrected by real measurements (controller round trip, SMT contention); stage-3 checkpoint of iteration 57, chosen on the training-split validation runs. Used automatically by the live orchestrator, E8 and the demo. Story and predictions: `results/testbed/TWIN_PREDICTION.md`; logs: `results/training_logs/train_live_stage*.log`, `pace_live_log.json` (stage 3). | yes |
| `pace_bc.pt` | Behaviour-cloning warm start for v5 (imitates CA-EFT). `python -m pace.rl.train --init models/pace_bc.pt` | yes |
| `pace_log.json` | Training log of the final model (plotted in `results/plots/training.png`). | n/a |
| `pace_v3.pt` | Reward v3 (deadline decomposition), 18 task features; results in `results/RESULTS_v3.md`. | no: needs the 18-feature code (commit "Reward v3 ...") |
| `pace_v2.pt` | Reward v2 (full job penalty per decision). Historical. | no |
| `pace_v1_weak.pt` | Reward v1 (job penalty split over tasks). It ignored `w` and missed 45% of analytics deadlines on held-out data. Historical. | no |

The training logs of every round are in `results/training_logs/` (v1 to v5). The development history and the reasons for each change are in `docs/PROPOSAL.md` §0.1.
