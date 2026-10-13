# Digital-twin predictions for E8 (written before the real AWS runs)

The twin is the simulator configured with the measured testbed (`testbed/twin.json`, from
`python -m testbed.calibrate` on 2026-10-13, campus network in Coimbatore): node speeds per task type,
laptop→Mumbai / laptop→Stockholm / Mumbai↔Stockholm round-trip and bandwidth.
Settings = E8 (`experiments.run_testbed`): 6 min, test-split jobs, work_scale 0.2, rate_a 0.25, PACE w = 0.9,
MERSEM-Balanced (w_s = 0.5, 120 s epochs). 5 seeds. Produced with `python -m experiments.twin_check`.

## Why fine-tune: the generic policy did not transfer

| Measured testbed vs simulator assumptions | Simulator (training) | Real testbed |
|---|---|---|
| HOG detection on a server | ~0.3 s | 0.011–0.016 s |
| ARM (t4g) vs x86 (c7i-flex) generic speed | 0.85× | ≈ 0.25–0.33× |
| one HTTP call laptop→Mumbai / →Stockholm | ~35 / 160 ms | ~110 / 425 ms |
| uplink bandwidth | 15–20 Mbps | 3–5 Mbps |

With the first calibration, `models/pace.pt` (trained only in the generic randomised simulator) was predicted to
miss **32 % of alerts** without the shield (the shield kept it at 0.2 %). Fine-tuning in the calibrated twin
(`pace.rl.train --init models/pace.pt --nodes testbed/twin.json`, ~25 min on 4 CPUs, checkpoint chosen on the
training-split validation runs, not on these test seeds) gives `models/pace_live.pt`.

## Predicted E8, nominal load (rate_bc = 0.075)

| Scheduler | SLA A % | SLA B % | SLA A+B % | carbon dyn (g) | p95 alert (s) |
|---|---|---|---|---|---|
| PACE (pace_live, w=0.9) | 0.0 | 4.2 | 0.4 | 0.0112 | 0.83 |
| PACE + shield (pace_live) | 0.0 | 2.5 | 0.3 | 0.0140 | 0.70 |
| PACE + shield (generic pace.pt) | 0.3 | 2.9 | 0.5 | 0.0245 | 0.60 |
| PACE (generic pace.pt) | 0.7 | 3.4 | 0.9 | 0.0218 | 0.60 |
| MERSEM-Balanced | 0.1 | 5.8 | 0.7 | 0.0138 | 0.80 |
| CA-EFT | 0.3 | 1.7 | 0.4 | 0.0151 | 0.80 |
| EFT | 0.9 | 0.0 | 0.8 | 0.1371 | 0.13 |

## Predicted E8, busy hour (rate_bc = 0.15, 2× analytics load)

| Scheduler | SLA A % | SLA B % | SLA A+B % | carbon dyn (g) | p95 alert (s) |
|---|---|---|---|---|---|
| PACE (pace_live, w=0.9) | 0.5 | 13.2 | 2.4 | 0.0259 | 0.85 |
| PACE + shield (pace_live) | 0.5 | 9.7 | 1.8 | 0.0321 | 0.71 |
| MERSEM-Balanced | 2.0 | 19.3 | 4.6 | 0.0395 | 0.83 |
| CA-EFT | 0.2 | 6.9 | 1.2 | 0.0365 | 0.85 |
| EFT | 2.3 | 1.1 | 2.1 | 0.2649 | 0.54 |

Predicted: PACE beats MERSEM on both SLA and carbon at both loads (nominal: −19 % carbon; busy: −2.2 pp SLA,
−34 % carbon). Against CA-EFT, PACE trades a little SLA for 26–29 % less carbon. At nominal load the light
testbed leaves little to optimise and the carbon totals are small, so real-world noise can blur the gaps;
E8 (real) and E9 (sim-to-real) test these predictions.
