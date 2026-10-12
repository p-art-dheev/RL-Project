# PACE results (simulation)

> carbon: SYNTHETIC hourly profiles (replace with Electricity Maps data). All runs use the dataset's held-out test split; each seed is a different day/hour, workload and carbon trace shared by every method.

> **How to read this.** "SLA A+B" weights every job equally, as MERSEM's SLA-violation rate does. Camera alerts (class A) are about 98% of jobs, so also read the per-class columns and the class-B-only fronts. **Dynamic carbon** is the part a scheduler controls and is the primary carbon metric. **Total carbon** adds idle power over each run's own length. Runs where batch work was deferred last longer, so their total includes more idle time; compare totals only with that in mind.
> Final model: PACE v5 (job-pressure features), class-priority node queues for every method. Earlier v3 results (FIFO queues): `RESULTS_v3.md`.


### E1 — testbed nominal (10 paired seeds, mean ± 95% CI)

| Method | SLA A % | SLA B % | SLA A+B % | Carbon dyn (g) | Carbon total (g) | p95 alert latency (s) | Work edge/fog/cloud | Decision (ms) |
|---|---|---|---|---|---|---|---|---|
| Random | 64.92 ± 8.07 | 63.86 ± 7.12 | 64.88 ± 7.96 | 3.46 ± 0.53 | 7.62 ± 0.54 | 13.74 ± 0.67 | 44/29/27 |  |
| Edge-only | 100.00 ± 0.00 | 100.00 ± 0.00 | 100.00 ± 0.00 | 11.06 ± 1.85 | 22.70 ± 3.22 | 17.23 ± 0.64 | 100/0/0 |  |
| Fog-only | 35.44 ± 7.46 | 25.14 ± 8.25 | 35.25 ± 7.42 | 2.99 ± 0.39 | 7.06 ± 0.35 | 3.18 ± 0.17 | 3/97/0 |  |
| Cloud-only | 29.58 ± 10.32 | 24.51 ± 8.27 | 29.49 ± 10.24 | 0.34 ± 0.09 | 4.40 ± 0.20 | 2.97 ± 0.55 | 3/2/95 |  |
| Carbon-greedy | 65.82 ± 18.59 | 77.03 ± 9.26 | 66.04 ± 18.33 | 0.28 ± 0.07 | 5.05 ± 0.34 | 5.11 ± 0.93 | 3/2/95 |  |
| EFT | 10.41 ± 2.29 | 1.26 ± 1.29 | 10.25 ± 2.25 | 1.96 ± 0.25 | 6.01 ± 0.23 | 1.29 ± 0.12 | 5/53/41 |  |
| Job-EFT | 4.25 ± 1.21 | 32.91 ± 2.26 | 4.76 ± 1.22 | 2.43 ± 0.27 | 6.49 ± 0.28 | 0.96 ± 0.12 | 4/66/30 |  |
| CA-EFT(m=1.0) | 7.77 ± 2.54 | 42.71 ± 5.41 | 8.39 ± 2.56 | 0.55 ± 0.14 | 4.70 ± 0.20 | 1.17 ± 0.13 | 4/10/86 |  |
| CA-EFT(m=0.6) | 3.15 ± 1.46 | 11.17 ± 7.07 | 3.29 ± 1.52 | 0.58 ± 0.15 | 4.72 ± 0.20 | 0.87 ± 0.09 | 4/11/86 |  |
| CA-EFT | 2.77 ± 1.51 | 5.64 ± 6.84 | 2.82 ± 1.59 | 0.74 ± 0.16 | 4.88 ± 0.18 | 0.80 ± 0.12 | 4/15/81 |  |
| CA-EFT(m=0.25) | 3.34 ± 1.58 | 3.15 ± 4.51 | 3.34 ± 1.62 | 0.80 ± 0.16 | 4.92 ± 0.17 | 0.80 ± 0.13 | 4/17/79 |  |
| MERSEM-Carbon | 18.10 ± 3.70 | 51.42 ± 4.59 | 18.69 ± 3.68 | 0.46 ± 0.10 | 4.70 ± 0.23 | 3.64 ± 0.57 | 4/5/90 |  |
| MERSEM-Balanced | 12.71 ± 3.01 | 45.38 ± 5.60 | 13.31 ± 3.02 | 0.51 ± 0.10 | 4.66 ± 0.21 | 2.20 ± 0.62 | 5/6/89 |  |
| MERSEM-SLA | 6.66 ± 1.93 | 33.55 ± 3.53 | 7.13 ± 1.92 | 1.82 ± 0.51 | 5.90 ± 0.41 | 1.31 ± 0.26 | 4/45/51 |  |
| MERSEM-Balanced-Oracle | 10.68 ± 2.88 | 45.31 ± 6.46 | 11.30 ± 2.91 | 0.49 ± 0.09 | 4.61 ± 0.21 | 2.25 ± 0.65 | 4/7/89 |  |
| PACE-joblevel | 1.55 ± 0.58 | 50.95 ± 6.89 | 2.44 ± 0.58 | 0.33 ± 0.08 | 4.50 ± 0.20 | 0.86 ± 0.04 | 3/3/94 | 0.54 |
| PACE(w=0.25) | 5.71 ± 1.82 | 28.24 ± 7.45 | 6.12 ± 1.84 | 0.32 ± 0.08 | 4.48 ± 0.23 | 1.31 ± 0.24 | 3/3/94 | 0.54 |
| PACE(w=0.5) | 1.89 ± 0.61 | 25.96 ± 6.75 | 2.32 ± 0.68 | 0.34 ± 0.09 | 4.50 ± 0.23 | 0.86 ± 0.04 | 3/3/94 | 0.56 |
| PACE(w=0.75) | 1.00 ± 0.34 | 23.28 ± 6.92 | 1.40 ± 0.41 | 0.37 ± 0.10 | 4.51 ± 0.22 | 0.85 ± 0.03 | 3/4/93 | 0.56 |
| PACE(w=0.9) | 0.94 ± 0.39 | 23.14 ± 6.87 | 1.33 ± 0.47 | 0.39 ± 0.10 | 4.52 ± 0.20 | 0.84 ± 0.04 | 3/5/92 | 0.56 |
| PACE(w=1.0) | 1.03 ± 0.61 | 22.61 ± 6.34 | 1.41 ± 0.69 | 0.41 ± 0.11 | 4.53 ± 0.20 | 0.85 ± 0.03 | 3/5/92 | 0.55 |
| PACE+shield(w=0.5) | 1.83 ± 1.00 | 17.49 ± 6.79 | 2.11 ± 1.08 | 0.45 ± 0.11 | 4.60 ± 0.20 | 0.83 ± 0.10 | 3/7/89 | 0.57 |
| PACE+shield(w=0.75) | 1.52 ± 0.99 | 8.72 ± 6.48 | 1.65 ± 1.07 | 0.54 ± 0.12 | 4.66 ± 0.19 | 0.77 ± 0.08 | 3/10/87 | 0.58 |
| PACE+shield(w=0.9) | 1.62 ± 0.91 | 6.37 ± 6.19 | 1.70 ± 0.98 | 0.57 ± 0.12 | 4.68 ± 0.18 | 0.82 ± 0.08 | 3/11/86 | 0.55 |
| PACE+shield(w=1.0) | 1.81 ± 1.07 | 6.01 ± 6.31 | 1.89 ± 1.14 | 0.55 ± 0.12 | 4.66 ± 0.18 | 0.87 ± 0.10 | 3/10/86 | 0.54 |
| PACE-target5% | 3.16 ± 0.80 | 27.72 ± 7.48 | 3.59 ± 0.84 | 0.33 ± 0.08 | 4.49 ± 0.23 | 0.90 ± 0.04 | 3/3/93 | 0.55 |
| PACE+shield-target5% | 1.98 ± 0.85 | 19.86 ± 5.09 | 2.29 ± 0.91 | 0.43 ± 0.11 | 4.58 ± 0.20 | 0.86 ± 0.05 | 3/7/90 | 0.59 |
| PACE+shield-target2% | 1.80 ± 0.91 | 16.16 ± 6.18 | 2.05 ± 0.97 | 0.47 ± 0.13 | 4.61 ± 0.19 | 0.83 ± 0.06 | 3/8/89 | 0.55 |

**Paired comparison (Wilcoxon signed-rank over seeds).** Negative Δ = PACE better.

| PACE variant | vs | Δ SLA A+B (pp) | p | Δ carbon dyn | p |
|---|---|---|---|---|---|
| PACE(w=0.9) | MERSEM-Balanced | -11.98 | 0.00195 | -22.3% | 0.00195 |
| PACE(w=0.9) | MERSEM-SLA | -5.81 | 0.00195 | -78.4% | 0.00195 |
| PACE(w=0.9) | MERSEM-Balanced-Oracle | -9.97 | 0.00195 | -19.3% | 0.00195 |
| PACE(w=0.9) | CA-EFT | -1.49 | 0.00977 | -46.9% | 0.00195 |
| PACE(w=0.9) | EFT | -8.92 | 0.00195 | -79.9% | 0.00195 |
| PACE+shield(w=0.9) | MERSEM-Balanced | -11.61 | 0.00195 | +12.4% | 0.00391 |
| PACE+shield(w=0.9) | MERSEM-SLA | -5.43 | 0.00195 | -68.7% | 0.00195 |
| PACE+shield(w=0.9) | MERSEM-Balanced-Oracle | -9.60 | 0.00195 | +16.7% | 0.00195 |
| PACE+shield(w=0.9) | CA-EFT | -1.12 | 0.00195 | -23.1% | 0.00195 |
| PACE+shield(w=0.9) | EFT | -8.55 | 0.00195 | -70.9% | 0.00195 |
| PACE+shield(w=1.0) | MERSEM-Balanced | -11.42 | 0.00195 | +7.6% | 0.232 |
| PACE+shield(w=1.0) | MERSEM-SLA | -5.25 | 0.00195 | -70.0% | 0.00195 |
| PACE+shield(w=1.0) | MERSEM-Balanced-Oracle | -9.41 | 0.00195 | +11.7% | 0.0488 |
| PACE+shield(w=1.0) | CA-EFT | -0.93 | 0.00195 | -26.4% | 0.00195 |
| PACE+shield(w=1.0) | EFT | -8.36 | 0.00195 | -72.2% | 0.00195 |
| PACE+shield-target5% | MERSEM-Balanced | -11.01 | 0.00195 | -14.7% | 0.0371 |
| PACE+shield-target5% | MERSEM-SLA | -4.84 | 0.00195 | -76.2% | 0.00195 |
| PACE+shield-target5% | MERSEM-Balanced-Oracle | -9.00 | 0.00195 | -11.5% | 0.0371 |
| PACE+shield-target5% | CA-EFT | -0.52 | 0.25 | -41.7% | 0.00195 |
| PACE+shield-target5% | EFT | -7.95 | 0.00195 | -77.9% | 0.00195 |

**Pareto hypervolume (testbed nominal, x = sla_AB; minimise SLA% and carbon; ref = 1.05 x worst point; higher is better):** PACE (one policy, w sweep): 1172, PACE + shield (w sweep): 1156, CA-EFT (margin sweep): 1131, MERSEM (base paper): 1083


**Pareto hypervolume (testbed nominal, x = sla_B; minimise SLA% and carbon; ref = 1.05 x worst point; higher is better):** PACE (one policy, w sweep): 931.1, PACE + shield (w sweep): 1105, CA-EFT (margin sweep): 1125, MERSEM (base paper): 780.3


### E1 — city nominal (10 paired seeds, mean ± 95% CI)

| Method | SLA A % | SLA B % | SLA A+B % | Carbon dyn (g) | Carbon total (g) | p95 alert latency (s) | Work edge/fog/cloud | Decision (ms) |
|---|---|---|---|---|---|---|---|---|
| Random | 42.24 ± 4.15 | 42.38 ± 3.57 | 42.24 ± 4.12 | 6.46 ± 0.84 | 18.21 ± 1.00 | 8.63 ± 0.70 | 33/30/37 |  |
| Edge-only | 100.00 ± 0.00 | 99.60 ± 0.53 | 100.00 ± 0.00 | 25.09 ± 3.43 | 51.79 ± 6.51 | 16.63 ± 0.28 | 100/0/0 |  |
| Fog-only | 50.25 ± 10.16 | 29.45 ± 7.48 | 50.06 ± 10.12 | 7.68 ± 0.89 | 19.48 ± 1.04 | 2.97 ± 0.16 | 6/94/0 |  |
| Cloud-only | 25.07 ± 5.66 | 11.59 ± 4.56 | 24.94 ± 5.63 | 1.22 ± 0.21 | 12.89 ± 0.51 | 2.56 ± 0.14 | 6/4/90 |  |
| Carbon-greedy | 68.48 ± 6.95 | 76.01 ± 9.82 | 68.55 ± 6.93 | 1.02 ± 0.17 | 15.33 ± 1.36 | 4.33 ± 0.15 | 5/5/90 |  |
| EFT | 8.13 ± 2.04 | 0.33 ± 0.46 | 8.05 ± 2.02 | 5.10 ± 0.54 | 16.74 ± 0.70 | 1.18 ± 0.10 | 8/53/39 |  |
| Job-EFT | 5.86 ± 1.40 | 38.42 ± 5.45 | 6.16 ± 1.38 | 6.31 ± 0.56 | 18.02 ± 0.82 | 1.08 ± 0.14 | 6/68/25 |  |
| CA-EFT(m=1.0) | 11.74 ± 1.74 | 37.33 ± 4.10 | 11.98 ± 1.74 | 1.30 ± 0.23 | 13.32 ± 0.60 | 1.35 ± 0.06 | 6/9/86 |  |
| CA-EFT(m=0.6) | 3.76 ± 0.73 | 7.22 ± 3.33 | 3.79 ± 0.74 | 1.50 ± 0.24 | 13.45 ± 0.59 | 0.91 ± 0.05 | 6/9/86 |  |
| CA-EFT | 2.81 ± 0.51 | 2.34 ± 2.40 | 2.80 ± 0.51 | 2.15 ± 0.29 | 14.07 ± 0.58 | 0.79 ± 0.04 | 6/15/79 |  |
| CA-EFT(m=0.25) | 2.57 ± 0.67 | 0.66 ± 0.93 | 2.55 ± 0.67 | 2.22 ± 0.31 | 14.08 ± 0.58 | 0.77 ± 0.05 | 6/16/78 |  |
| MERSEM-Carbon | 23.25 ± 3.22 | 60.46 ± 3.21 | 23.60 ± 3.20 | 1.78 ± 0.28 | 14.89 ± 0.67 | 3.76 ± 0.23 | 9/8/83 |  |
| MERSEM-Balanced | 17.53 ± 1.88 | 52.52 ± 3.34 | 17.86 ± 1.86 | 1.89 ± 0.31 | 14.45 ± 0.84 | 3.08 ± 0.25 | 9/10/81 |  |
| MERSEM-SLA | 10.33 ± 2.62 | 36.98 ± 5.73 | 10.57 ± 2.59 | 6.19 ± 0.64 | 17.88 ± 0.82 | 1.87 ± 0.36 | 7/65/28 |  |
| MERSEM-Balanced-Oracle | 15.84 ± 2.45 | 53.18 ± 4.36 | 16.18 ± 2.44 | 1.87 ± 0.31 | 14.67 ± 0.92 | 2.80 ± 0.33 | 8/10/81 |  |
| PACE-joblevel | 0.68 ± 0.36 | 66.70 ± 5.14 | 1.29 ± 0.36 | 1.13 ± 0.20 | 15.87 ± 2.32 | 0.81 ± 0.04 | 6/4/90 | 0.58 |
| PACE(w=0.25) | 4.86 ± 1.16 | 19.23 ± 4.08 | 4.99 ± 1.16 | 1.12 ± 0.20 | 16.00 ± 1.60 | 1.08 ± 0.15 | 6/5/89 | 0.55 |
| PACE(w=0.5) | 2.01 ± 0.51 | 16.16 ± 3.84 | 2.14 ± 0.51 | 1.17 ± 0.21 | 16.10 ± 1.63 | 0.84 ± 0.04 | 6/5/89 | 0.58 |
| PACE(w=0.75) | 1.02 ± 0.26 | 13.43 ± 4.13 | 1.13 ± 0.26 | 1.22 ± 0.22 | 15.43 ± 1.64 | 0.81 ± 0.03 | 6/5/89 | 0.58 |
| PACE(w=0.9) | 0.91 ± 0.19 | 12.12 ± 3.79 | 1.01 ± 0.20 | 1.25 ± 0.22 | 14.61 ± 1.41 | 0.80 ± 0.03 | 6/5/89 | 0.56 |
| PACE(w=1.0) | 0.90 ± 0.26 | 13.53 ± 3.12 | 1.01 ± 0.26 | 1.28 ± 0.23 | 14.12 ± 1.18 | 0.80 ± 0.03 | 6/6/89 | 0.57 |
| PACE+shield(w=0.5) | 1.33 ± 0.29 | 8.16 ± 3.65 | 1.40 ± 0.31 | 1.29 ± 0.22 | 16.03 ± 1.57 | 0.76 ± 0.02 | 6/7/88 | 0.59 |
| PACE+shield(w=0.75) | 0.99 ± 0.23 | 5.19 ± 2.51 | 1.03 ± 0.24 | 1.57 ± 0.24 | 15.80 ± 1.59 | 0.72 ± 0.01 | 6/9/85 | 0.60 |
| PACE+shield(w=0.9) | 0.99 ± 0.24 | 3.74 ± 2.64 | 1.01 ± 0.25 | 1.67 ± 0.25 | 15.10 ± 1.46 | 0.73 ± 0.01 | 6/10/84 | 0.57 |
| PACE+shield(w=1.0) | 1.07 ± 0.23 | 3.41 ± 2.49 | 1.09 ± 0.25 | 1.53 ± 0.25 | 14.38 ± 1.20 | 0.75 ± 0.02 | 6/9/85 | 0.58 |
| PACE-target5% | 3.20 ± 0.53 | 17.48 ± 3.84 | 3.33 ± 0.53 | 1.14 ± 0.20 | 16.02 ± 1.56 | 0.89 ± 0.04 | 6/5/89 | 0.60 |
| PACE+shield-target5% | 2.03 ± 0.38 | 12.24 ± 3.06 | 2.12 ± 0.39 | 1.22 ± 0.21 | 16.10 ± 1.51 | 0.84 ± 0.03 | 6/7/87 | 0.59 |
| PACE+shield-target2% | 1.64 ± 0.22 | 9.78 ± 2.74 | 1.71 ± 0.22 | 1.28 ± 0.22 | 16.03 ± 1.56 | 0.79 ± 0.03 | 6/7/87 | 0.57 |

**Paired comparison (Wilcoxon signed-rank over seeds).** Negative Δ = PACE better.

| PACE variant | vs | Δ SLA A+B (pp) | p | Δ carbon dyn | p |
|---|---|---|---|---|---|
| PACE(w=0.9) | MERSEM-Balanced | -16.84 | 0.00195 | -33.6% | 0.00195 |
| PACE(w=0.9) | MERSEM-SLA | -9.56 | 0.00195 | -79.7% | 0.00195 |
| PACE(w=0.9) | MERSEM-Balanced-Oracle | -15.17 | 0.00195 | -33.0% | 0.00195 |
| PACE(w=0.9) | CA-EFT | -1.79 | 0.00195 | -41.6% | 0.00195 |
| PACE(w=0.9) | EFT | -7.04 | 0.00195 | -75.4% | 0.00195 |
| PACE+shield(w=0.9) | MERSEM-Balanced | -16.84 | 0.00195 | -11.8% | 0.00391 |
| PACE+shield(w=0.9) | MERSEM-SLA | -9.56 | 0.00195 | -73.1% | 0.00195 |
| PACE+shield(w=0.9) | MERSEM-Balanced-Oracle | -15.17 | 0.00195 | -11.0% | 0.00391 |
| PACE+shield(w=0.9) | CA-EFT | -1.79 | 0.00195 | -22.4% | 0.00195 |
| PACE+shield(w=0.9) | EFT | -7.04 | 0.00195 | -67.3% | 0.00195 |
| PACE+shield(w=1.0) | MERSEM-Balanced | -16.77 | 0.00195 | -19.2% | 0.00195 |
| PACE+shield(w=1.0) | MERSEM-SLA | -9.48 | 0.00195 | -75.3% | 0.00195 |
| PACE+shield(w=1.0) | MERSEM-Balanced-Oracle | -15.10 | 0.00195 | -18.5% | 0.00195 |
| PACE+shield(w=1.0) | CA-EFT | -1.71 | 0.00195 | -28.9% | 0.00195 |
| PACE+shield(w=1.0) | EFT | -6.97 | 0.00195 | -70.1% | 0.00195 |
| PACE+shield-target5% | MERSEM-Balanced | -15.73 | 0.00195 | -35.2% | 0.00195 |
| PACE+shield-target5% | MERSEM-SLA | -8.45 | 0.00195 | -80.2% | 0.00195 |
| PACE+shield-target5% | MERSEM-Balanced-Oracle | -14.06 | 0.00195 | -34.7% | 0.00195 |
| PACE+shield-target5% | CA-EFT | -0.68 | 0.00977 | -43.0% | 0.00195 |
| PACE+shield-target5% | EFT | -5.93 | 0.00195 | -76.0% | 0.00195 |

**Pareto hypervolume (city nominal, x = sla_AB; minimise SLA% and carbon; ref = 1.05 x worst point; higher is better):** PACE (one policy, w sweep): 2626, PACE + shield (w sweep): 2612, CA-EFT (margin sweep): 2565, MERSEM (base paper): 2287


**Pareto hypervolume (city nominal, x = sla_B; minimise SLA% and carbon; ref = 1.05 x worst point; higher is better):** PACE (one policy, w sweep): 2335, PACE + shield (w sweep): 2539, CA-EFT (margin sweep): 2594, MERSEM (base paper): 1591


### E2 — load (class B/C jobs per s)

| load (class B/C jobs per s) | CA-EFT | EFT | MERSEM-Balanced | MERSEM-SLA | PACE(w=0.9) | PACE+shield(w=0.9) | PACE+shield-target5% |
|---|---|---|---|---|---|---|---|
| 0.0075 | 0.6% / 0.52g | 4.5% / 1.20g | 5.4% / 0.44g | 2.4% / 0.93g | 0.4% / 0.34g | 0.2% / 0.43g | 0.6% / 0.33g |
| 0.015 | 2.4% / 0.73g | 9.9% / 1.94g | 12.6% / 0.53g | 7.7% / 1.74g | 1.0% / 0.44g | 1.5% / 0.60g | 2.0% / 0.47g |
| 0.0225 | 4.5% / 0.95g | 17.4% / 2.70g | 22.8% / 0.65g | 14.1% / 2.58g | 1.9% / 0.59g | 2.5% / 0.77g | 3.4% / 0.63g |
| 0.03 | 7.2% / 1.20g | 26.0% / 3.34g | 26.3% / 0.82g | 23.5% / 2.96g | 3.0% / 0.74g | 4.8% / 0.99g | 4.3% / 0.86g |

### E3 — runtime-estimate noise sigma

| runtime-estimate noise sigma | CA-EFT | EFT | MERSEM-Balanced | MERSEM-SLA | PACE(w=0.9) | PACE+shield(w=0.9) | PACE+shield-target5% |
|---|---|---|---|---|---|---|---|
| 0.0 | 1.6% / 0.66g | 8.9% / 1.78g | 7.8% / 0.50g | 6.0% / 1.67g | 0.8% / 0.43g | 0.8% / 0.62g | 1.4% / 0.45g |
| 0.2 | 2.4% / 0.73g | 9.9% / 1.94g | 12.6% / 0.53g | 7.7% / 1.74g | 1.0% / 0.44g | 1.5% / 0.60g | 2.0% / 0.47g |
| 0.4 | 3.2% / 0.71g | 10.1% / 1.94g | 14.0% / 0.54g | 6.9% / 1.69g | 1.2% / 0.45g | 1.4% / 0.57g | 2.3% / 0.48g |

### E4

| Scenario | Method | SLA A+B % | Carbon dyn (g) |
|---|---|---|---|
| fog crash + stragglers | CA-EFT | 15.85 | 0.844 |
| fog crash + stragglers | EFT | 21.90 | 1.896 |
| fog crash + stragglers | MERSEM-Balanced | 26.38 | 0.589 |
| fog crash + stragglers | MERSEM-SLA | 21.01 | 1.333 |
| fog crash + stragglers | PACE(w=0.9) | 14.80 | 0.526 |
| fog crash + stragglers | PACE+shield(w=0.9) | 10.98 | 0.650 |
| fog crash + stragglers | PACE+shield-target5% | 14.38 | 0.624 |
| random failures | CA-EFT | 4.00 | 0.824 |
| random failures | EFT | 13.10 | 1.965 |
| random failures | MERSEM-Balanced | 18.61 | 0.719 |
| random failures | MERSEM-SLA | 11.97 | 1.819 |
| random failures | PACE(w=0.9) | 1.79 | 0.523 |
| random failures | PACE+shield(w=0.9) | 2.74 | 0.683 |
| random failures | PACE+shield-target5% | 3.26 | 0.601 |

### E5

| Scenario | Method | SLA A+B % | Carbon dyn (g) |
|---|---|---|---|
| rush hour (x2.5 for 15 min) | CA-EFT | 4.94 | 1.016 |
| rush hour (x2.5 for 15 min) | MERSEM-Balanced | 21.97 | 0.808 |
| rush hour (x2.5 for 15 min) | PACE+shield(w=0.5) | 2.79 | 0.741 |
| rush hour (x2.5 for 15 min) | PACE+shield-target2% | 3.31 | 0.760 |
| rush hour (x2.5 for 15 min) | PACE+shield-target5% | 3.35 | 0.712 |
