# E8 (real AWS testbed) — what happened and why

Run: 2026-10-13 evening, campus network in Coimbatore; 5 schedulers x 3 seeds, interleaved
(A B C D E per seed, ~6 min each, 1.6 h in total), nominal load (rate_bc 0.075). Raw runs: `e8_*.json`
(every task: node, network, queue and compute time). Summary: `E8_SUMMARY.md`; sim-to-real: `E9_SIM2REAL.md`.

## Result (mean of 3 seeds)

| Scheduler | Alerts missed | Analytics missed | A+B missed | Carbon dyn (g) | p95 alert (s) |
|---|---|---|---|---|---|
| PACE + shield | 9.9 % | 34.4 % | 11.8 % | 0.0370 | 1.34 |
| PACE | 13.9 % | **23.8 %** | 14.7 % | 0.0328 | 1.29 |
| MERSEM-Balanced | 6.9 % | 49.2 % | 10.3 % | **0.0306** | 1.10 |
| CA-EFT | 21.6 % | 34.6 % | 22.7 % | 0.0471 | 1.54 |
| EFT | 5.5 % | 36.4 % | 7.9 % | 0.2303 | 1.41 |

Per seed (A+B missed): PACE+shield 3.6 / 10.6 / 21.3 %; PACE 3.1 / 19.2 / 21.8 %; MERSEM 10.2 / 9.8 / 10.9 %;
CA-EFT 4.0 / 35.1 / 28.9 %; EFT 12.9 / 2.0 / 8.8 %.

What held: PACE misses half as many analytics deadlines as MERSEM, in every seed (17.6/26.3/27.3 % vs
70.6/31.6/45.5 %); PACE beats CA-EFT on both SLA and carbon; EFT pays ~7x the carbon.
What did not: alert misses (85 % of the jobs) were far above the twin's prediction (~0 %) for every scheduler,
and PACE missed more alerts than MERSEM, so overall PACE did not beat MERSEM on this run.

## Root cause: the network to Mumbai degraded during the run

The task records split each missed alert into network, queue and compute time. Queue ≈ 0 and compute ≈ 0.03 s;
the loss is the **network time of the detection step** (frame upload laptop → Mumbai + controller round trip).
For alert detections on bom-arm with *no* analytics upload in flight at the same time:

| seed (run order) | median | p90 |
|---|---|---|
| 1 (first ~30 min) | 0.25 s | 0.36–0.58 s |
| 2 | 0.41–0.45 s | 0.72–0.92 s |
| 3 (last ~30 min) | 0.47–0.56 s | 0.74–1.33 s |

So the campus uplink to Mumbai slowed down over the evening, independently of our own traffic. All schedulers
saw the same conditions (interleaved runs); the difference is where they put the detection step:
PACE and CA-EFT ran 80–100 % of detections in Mumbai (much less carbon than the Pi-class edge), relying on the
calibrated ~0.3 s; MERSEM ran ~40 % on the edge, which needs no network, and was less exposed. The shield
did not help because it checks against the same static estimate. Alert detections that did run on the edge
took ≤ 0.17 s in every run.

## Fix: online network estimation (commit "Online network estimate in the live orchestrator")

The orchestrator now compares each task's measured network time with the calibrated model and adds the
90th percentile of the last 30 residuals per region to the latency estimate that every scheduler (MERSEM
included), PACE's features and the shield use. Replaying E8's task records through this estimator gives
an extra ~0.1 s for Mumbai in seed 1 (Mumbai stays allowed, carbon savings kept) and 0.3–0.65 s in seeds 2–3,
which pushes the estimated alert time in Mumbai (0.55–0.80 s) over the shield's limit (0.46 s at w = 0.9), so
alerts stay on the edge while the network is degraded.

E8b repeats E8 with the online estimate (`results/testbed/adaptive/`). Network conditions at a different time of
day differ, so E8 and E8b are compared within each run set (interleaved), not across them.

## E8b — the same experiment with the online network estimate (results/testbed/adaptive/)

Run 2026-10-13 night, same settings, interleaved, 3 seeds. EFT's runs were hit by an orchestrator bug and are
excluded (see `invalid/README.md`); the four runs below had no failures and no unfinished jobs.

| Scheduler | Alerts missed | Analytics missed | A+B missed | Carbon dyn (g) | p95 alert (s) |
|---|---|---|---|---|---|
| **PACE** | 1.4 % | **30.3 %** | **3.8 %** | 0.0440 | 0.72 |
| PACE + shield | 4.2 % | 29.0 % | 6.1 % | 0.0495 | 1.07 |
| MERSEM-Balanced | 6.1 % | 45.9 % | 9.4 % | **0.0374** | 1.09 |
| CA-EFT | 0.8 % | 37.0 % | 3.7 % | 0.0509 | 0.44 |

Per seed (A+B missed): PACE 7.6 / 1.2 / 2.5 %; MERSEM 17.3 / 6.1 / 4.6 %; CA-EFT 4.9 / 2.9 / 3.3 %;
PACE+shield 4.0 / 8.6 / 5.9 %.

- **PACE vs MERSEM (the base paper):** fewer missed alerts (1.4 vs 6.1 %), analytics (30 vs 46 %) and overall
  (3.8 vs 9.4 %), better in every seed, for 18 % more operational carbon (0.044 vs 0.037 g). At w = 0.9 PACE is
  set to favour deadlines; MERSEM-Balanced sits at a lower-carbon, higher-miss point, so neither dominates on
  this run (a lower w is PACE's knob for that trade-off; not measured on AWS).
- **PACE vs CA-EFT:** the same deadline performance (3.8 vs 3.7 %) with 14 % less carbon and fewer analytics misses.
- **Effect of the online estimate** (E8 → E8b, different hours so only indicative): PACE 14.7 → 3.8 % missed,
  CA-EFT 22.7 → 3.7 %, PACE+shield 11.8 → 6.1 %, MERSEM 10.3 → 9.4 %. The schedulers that rely on per-task latency
  estimates gain the most; PACE spends more carbon than in E8 because it keeps alerts local when Mumbai is slow.
