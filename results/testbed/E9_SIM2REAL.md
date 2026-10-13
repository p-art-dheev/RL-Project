# E9 — sim-to-real fidelity (same job trace, calibrated simulator vs real AWS)

| run | jobs real/sim | SLA A+B real | SLA A+B sim | p95 alert real | p95 alert sim | KS(latency A) | KS(latency B) |
|---|---|---|---|---|---|---|---|
| testbed/e8_ca-eft_s1 | 240/240 | 4.0% | 3.1% | 0.72s | 0.43s | 0.52 | 0.18 |
| testbed/e8_ca-eft_s2 | 255/255 | 35.1% | 2.0% | 2.30s | 0.45s | 0.97 | 0.26 |
| testbed/e8_ca-eft_s3 | 251/251 | 28.9% | 2.5% | 1.60s | 0.45s | 0.96 | 0.23 |
| testbed/e8_eft_s1 | 240/240 | 12.9% | 2.7% | 2.65s | 0.16s | 0.95 | 0.65 |
| testbed/e8_eft_s2 | 255/255 | 2.0% | 0.4% | 0.33s | 0.10s | 0.98 | 0.26 |
| testbed/e8_eft_s3 | 251/251 | 8.8% | 1.3% | 1.24s | 0.10s | 0.98 | 0.27 |
| testbed/e8_mersem_s1 | 240/240 | 10.2% | 6.2% | 1.02s | 0.46s | 0.52 | 0.29 |
| testbed/e8_mersem_s2 | 255/255 | 9.8% | 3.7% | 1.15s | 0.46s | 0.60 | 0.26 |
| testbed/e8_mersem_s3 | 251/251 | 10.9% | 4.2% | 1.13s | 0.45s | 0.45 | 0.14 |
| testbed/e8_pace-shield_s1 | 240/240 | 3.6% | 1.8% | 0.70s | 0.44s | 0.57 | 0.18 |
| testbed/e8_pace-shield_s2 | 255/255 | 10.6% | 0.8% | 1.25s | 0.44s | 0.83 | 0.26 |
| testbed/e8_pace-shield_s3 | 251/251 | 21.3% | 2.5% | 2.08s | 0.45s | 0.78 | 0.32 |
| testbed/e8_pace_s1 | 240/240 | 3.1% | 1.3% | 0.89s | 0.87s | 0.55 | 0.18 |
| testbed/e8_pace_s2 | 255/255 | 19.2% | 0.8% | 1.38s | 0.84s | 0.50 | 0.21 |
| testbed/e8_pace_s3 | 251/251 | 21.8% | 2.5% | 1.59s | 0.87s | 0.47 | 0.32 |

KS = Kolmogorov-Smirnov distance between real and simulated latency distributions (0 = identical).
