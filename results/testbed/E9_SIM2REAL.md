# E9 — sim-to-real fidelity (same job trace, calibrated simulator vs real AWS)

| run | jobs real/sim | SLA A+B real | SLA A+B sim | p95 alert real | p95 alert sim | KS(latency A) | KS(latency B) |
|---|---|---|---|---|---|---|---|
| adaptive/e8_ca-eft_s1 | 240/240 | 4.9% | 3.1% | 0.39s | 0.43s | 0.94 | 0.35 |
| adaptive/e8_ca-eft_s2 | 255/255 | 2.9% | 2.0% | 0.62s | 0.45s | 0.67 | 0.16 |
| adaptive/e8_ca-eft_s3 | 251/251 | 3.3% | 2.5% | 0.32s | 0.45s | 0.97 | 0.14 |
| adaptive/e8_eft_s1 | 230/240 | 44.3% | 2.7% | 4.54s | 0.16s | 0.95 | 0.77 |
| adaptive/e8_eft_s2 | 248/255 | 56.8% | 0.4% | 4.88s | 0.10s | 0.99 | 0.87 |
| adaptive/e8_eft_s3 | 248/251 | 61.5% | 1.3% | 3.75s | 0.10s | 0.98 | 0.77 |
| adaptive/e8_mersem_s1 | 240/240 | 17.3% | 6.2% | 1.57s | 0.46s | 0.52 | 0.24 |
| adaptive/e8_mersem_s2 | 255/255 | 6.1% | 3.7% | 0.95s | 0.46s | 0.53 | 0.21 |
| adaptive/e8_mersem_s3 | 251/251 | 4.6% | 4.2% | 0.74s | 0.45s | 0.46 | 0.23 |
| adaptive/e8_pace-shield_s1 | 240/240 | 4.0% | 1.8% | 0.41s | 0.44s | 0.87 | 0.35 |
| adaptive/e8_pace-shield_s2 | 255/255 | 8.6% | 0.8% | 2.02s | 0.44s | 0.40 | 0.21 |
| adaptive/e8_pace-shield_s3 | 251/251 | 5.9% | 2.5% | 0.78s | 0.45s | 0.78 | 0.14 |
| adaptive/e8_pace_s1 | 240/240 | 7.6% | 1.3% | 0.90s | 0.87s | 0.59 | 0.35 |
| adaptive/e8_pace_s2 | 255/255 | 1.2% | 0.8% | 0.68s | 0.84s | 0.30 | 0.21 |
| adaptive/e8_pace_s3 | 251/251 | 2.5% | 2.5% | 0.59s | 0.87s | 0.43 | 0.14 |
| adaptive_busy/e8_ca-eft_s1 | 248/272 | 67.1% | 9.7% | 5.24s | 0.69s | 0.66 | 0.86 |
| adaptive_busy/e8_ca-eft_s2 | 270/289 | 9.0% | 5.4% | 0.71s | 0.66s | 0.81 | 0.22 |
| adaptive_busy/e8_ca-eft_s3 | 241/274 | 71.7% | 4.8% | 11.07s | 0.44s | 0.77 | 1.00 |
| adaptive_busy/e8_mersem_s1 | 231/272 | 27.0% | 14.2% | 3.24s | 1.11s | 0.61 | 0.33 |
| adaptive_busy/e8_mersem_s2 | 289/289 | 12.3% | 9.2% | 1.41s | 0.47s | 0.42 | 0.20 |
| adaptive_busy/e8_mersem_s3 | 224/274 | 58.2% | 9.2% | 14.44s | 0.46s | 0.59 | 0.62 |
| adaptive_busy/e8_pace-shield_s1 | 247/272 | 22.6% | 6.9% | 3.22s | 0.44s | 0.55 | 0.37 |
| adaptive_busy/e8_pace-shield_s2 | 272/289 | 11.2% | 4.6% | 1.79s | 0.44s | 0.74 | 0.29 |
| adaptive_busy/e8_pace-shield_s3 | 240/274 | 33.3% | 2.8% | 3.49s | 0.44s | 0.54 | 0.61 |
| adaptive_busy/e8_pace_s1 | 240/272 | 19.1% | 6.5% | 3.18s | 0.86s | 0.57 | 0.51 |
| adaptive_busy/e8_pace_s2 | 274/289 | 12.6% | 5.0% | 1.66s | 0.84s | 0.49 | 0.23 |
| adaptive_busy/e8_pace_s3 | 240/274 | 37.1% | 3.6% | 20.46s | 0.87s | 0.37 | 0.45 |
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
