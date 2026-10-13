# Digital twin of the real testbed, and its predictions for E8 (written before the real runs)

The twin is the simulator configured with the measured testbed (`testbed/twin.json`): node speeds per task type,
the slowdown when all cores of a node are busy, laptop→Mumbai / laptop→Stockholm / Mumbai↔Stockholm round trip
and bandwidth (`python -m testbed.calibrate`, campus network in Coimbatore, 2026-10-13), plus the orchestrator's
round trip per task. Settings = E8 (`experiments.run_testbed`): 6 min, test-split jobs, work_scale 0.2,
rate_a 0.25, PACE w = 0.9, MERSEM-Balanced (w_s = 0.5, 120 s epochs). 5 seeds, `python -m experiments.twin_check`.

## How the twin was corrected by real measurements

| Step | What we learned | Fix |
|---|---|---|
| 1st calibration | HOG on a server takes 0.011–0.016 s (simulator: ~0.3 s); ARM 0.25–0.33× x86 on BLAS (sim: 0.85×); one HTTP call laptop→Mumbai / Stockholm ~110 / 425 ms (sim: 35 / 160 ms); uplink 3–5 Mbps. `models/pace.pt` (generic simulator only) was predicted to miss **32 % of alerts** without the shield. | Fine-tune PACE in the calibrated twin (`pace.rl.train --nodes`). |
| Laptop edge | OpenCV used all 12 laptop threads, so the "1-core Pi-class" edge was faster than the servers. | One thread per task (`cv2.setNumThreads(1)`). |
| 1st smoke test (CA-EFT, 2 min) | Real: 18 % alerts and 56 % analytics missed; twin: 0 %. The orchestrator held a core during the whole HTTP round trip, and the twin had no per-task controller round trip. | Tasks are sent when placed, workers fetch inputs while others compute and start tasks by class priority; twin and all schedulers (MERSEM included) see the controller round trip. |
| 2nd smoke test | Alerts 0 % missed (p95 0.73 s). Task records: on c7i-flex (2 vCPU = 1 physical core) two tasks at once each run **1.7–1.8× slower**; t4g (2 physical cores) 1.0×. Twin assumed 1.15× everywhere. | `calibrate` measures the slowdown per node; the twin uses it. Twin now predicts this smoke test at 2/9 analytics misses vs 3/9 real, 0 alert misses vs 0. |

`models/pace_live.pt` = `pace.pt` fine-tuned in three stages in the successively corrected twins (~1 h on 4 CPUs);
the final checkpoint (stage 3, iteration 57) was chosen on the training-split validation runs, not on the test seeds below.

## Predicted E8, nominal load (rate_bc = 0.075)

| Scheduler | SLA A % | SLA B % | SLA A+B % | carbon dyn (g) | p95 alert (s) |
|---|---|---|---|---|---|
| PACE (w=0.9) | 0.0 | 25.1 | 2.0 | 0.0264 | 0.88 |
| PACE + shield | 0.0 | 20.8 | 1.7 | 0.0309 | 0.47 |
| MERSEM-Balanced | 2.7 | 46.9 | 6.1 | 0.0290 | 0.49 |
| CA-EFT | 0.2 | 29.2 | 2.5 | 0.0471 | 0.49 |
| EFT | 0.2 | 5.0 | 0.7 | 0.2121 | 0.12 |

## Predicted E8, busy hour (rate_bc = 0.15)

| Scheduler | SLA A % | SLA B % | SLA A+B % | carbon dyn (g) | p95 alert (s) |
|---|---|---|---|---|---|
| PACE (w=0.9) | 0.5 | 35.6 | 5.6 | 0.0694 | 0.88 |
| PACE + shield | 0.0 | 35.3 | 5.0 | 0.0766 | 0.48 |
| MERSEM-Balanced | 4.5 | 60.2 | 12.3 | 0.0609 | 0.74 |
| CA-EFT | 0.7 | 46.8 | 7.2 | 0.1114 | 0.63 |

Predicted claims for the real runs: PACE misses fewer deadlines than MERSEM at both loads (−4 pp nominal, −7 pp busy)
with less carbon at nominal load (−9 %) and somewhat more under the busy hour (+14 %, MERSEM missing 60 % of analytics
jobs); PACE dominates CA-EFT (fewer misses and 38–44 % less carbon); EFT meets most deadlines at 7–8× the carbon.
Analytics deadlines are hard for every scheduler on this testbed because a 2-vCPU x86 instance delivers ~1.1 cores
when busy. E8 measures the real outcome; E9 compares it with these predictions.
