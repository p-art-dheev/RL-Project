# E9 — sim-to-real fidelity (same job trace, calibrated simulator vs real AWS)

| run | jobs real/sim | SLA A+B real | SLA A+B sim | p95 alert real | p95 alert sim | KS(latency A) | KS(latency B) |
|---|---|---|---|---|---|---|---|
| adaptive/e8_ca-eft_s1 | 240/240 | 4.9% | 2.2% | 0.39s | 0.54s | 0.96 | 0.47 |
| adaptive/e8_ca-eft_s2 | 255/255 | 2.9% | 1.6% | 0.62s | 0.54s | 0.84 | 0.32 |
| adaptive/e8_ca-eft_s3 | 251/251 | 3.3% | 2.5% | 0.32s | 0.55s | 0.98 | 0.18 |
| adaptive/e8_eft_s1 | 240/240 | 17.8% | 0.0% | 2.68s | 0.15s | 0.99 | 0.71 |
| adaptive/e8_eft_s2 | 255/255 | 19.6% | 0.0% | 2.93s | 0.15s | 0.96 | 0.53 |
| adaptive/e8_eft_s3 | 251/251 | 5.9% | 1.3% | 0.34s | 0.16s | 0.94 | 0.32 |
| adaptive/e8_mersem_s1 | 240/240 | 17.3% | 6.7% | 1.57s | 0.54s | 0.56 | 0.35 |
| adaptive/e8_mersem_s2 | 255/255 | 6.1% | 3.7% | 0.95s | 0.54s | 0.40 | 0.21 |
| adaptive/e8_mersem_s3 | 251/251 | 4.6% | 2.5% | 0.74s | 0.53s | 0.42 | 0.23 |
| adaptive/e8_pace-shield_s1 | 240/240 | 4.0% | 0.4% | 0.41s | 0.53s | 0.93 | 0.47 |
| adaptive/e8_pace-shield_s2 | 255/255 | 8.6% | 0.4% | 2.02s | 0.53s | 0.69 | 0.21 |
| adaptive/e8_pace-shield_s3 | 251/251 | 5.9% | 1.7% | 0.78s | 0.53s | 0.88 | 0.23 |
| adaptive/e8_pace_s1 | 240/240 | 7.6% | 0.4% | 0.90s | 0.95s | 0.53 | 0.47 |
| adaptive/e8_pace_s2 | 255/255 | 1.2% | 0.4% | 0.68s | 0.53s | 0.54 | 0.21 |
| adaptive/e8_pace_s3 | 251/251 | 2.5% | 2.9% | 0.59s | 0.97s | 0.61 | 0.18 |
| adaptive_busy/e8_ca-eft_s1 | 272/272 | 8.9% | 7.7% | 0.44s | 0.71s | 0.92 | 0.23 |
| adaptive_busy/e8_ca-eft_s2 | 289/289 | 5.4% | 5.7% | 0.34s | 0.66s | 0.96 | 0.14 |
| adaptive_busy/e8_ca-eft_s3 | 274/274 | 4.4% | 3.2% | 0.31s | 0.57s | 0.98 | 0.16 |
| adaptive_busy/e8_mersem_s1 | 269/272 | 17.4% | 13.0% | 1.39s | 0.58s | 0.58 | 0.13 |
| adaptive_busy/e8_mersem_s2 | 289/289 | 11.5% | 8.8% | 0.75s | 0.60s | 0.44 | 0.29 |
| adaptive_busy/e8_mersem_s3 | 274/274 | 14.1% | 7.2% | 1.20s | 0.55s | 0.48 | 0.16 |
| adaptive_busy/e8_pace-shield_s1 | 266/272 | 6.5% | 6.5% | 0.47s | 0.54s | 0.88 | 0.23 |
| adaptive_busy/e8_pace-shield_s2 | 289/289 | 4.2% | 3.8% | 0.49s | 0.54s | 0.86 | 0.11 |
| adaptive_busy/e8_pace-shield_s3 | 274/274 | 3.2% | 2.4% | 0.55s | 0.53s | 0.88 | 0.12 |
| adaptive_busy/e8_pace_s1 | 272/272 | 8.9% | 5.7% | 0.87s | 0.56s | 0.64 | 0.23 |
| adaptive_busy/e8_pace_s2 | 289/289 | 5.4% | 3.8% | 0.65s | 0.54s | 0.65 | 0.11 |
| adaptive_busy/e8_pace_s3 | 274/274 | 5.6% | 3.6% | 0.78s | 0.96s | 0.59 | 0.12 |
| testbed/e8_ca-eft_s1 | 240/240 | 4.0% | 2.2% | 0.72s | 0.54s | 0.41 | 0.24 |
| testbed/e8_ca-eft_s2 | 255/255 | 35.1% | 1.6% | 2.30s | 0.54s | 0.90 | 0.37 |
| testbed/e8_ca-eft_s3 | 251/251 | 28.9% | 2.5% | 1.60s | 0.55s | 0.88 | 0.27 |
| testbed/e8_eft_s1 | 240/240 | 12.9% | 0.0% | 2.65s | 0.15s | 0.98 | 0.71 |
| testbed/e8_eft_s2 | 255/255 | 2.0% | 0.0% | 0.33s | 0.15s | 0.96 | 0.32 |
| testbed/e8_eft_s3 | 251/251 | 8.8% | 1.3% | 1.24s | 0.16s | 0.94 | 0.27 |
| testbed/e8_mersem_s1 | 240/240 | 10.2% | 6.7% | 1.02s | 0.54s | 0.55 | 0.29 |
| testbed/e8_mersem_s2 | 255/255 | 9.8% | 3.7% | 1.15s | 0.54s | 0.54 | 0.42 |
| testbed/e8_mersem_s3 | 251/251 | 10.9% | 2.5% | 1.13s | 0.53s | 0.41 | 0.23 |
| testbed/e8_pace-shield_s1 | 240/240 | 3.6% | 0.4% | 0.70s | 0.53s | 0.33 | 0.35 |
| testbed/e8_pace-shield_s2 | 255/255 | 10.6% | 0.4% | 1.25s | 0.53s | 0.76 | 0.37 |
| testbed/e8_pace-shield_s3 | 251/251 | 21.3% | 1.7% | 2.08s | 0.53s | 0.72 | 0.36 |
| testbed/e8_pace_s1 | 240/240 | 3.1% | 0.4% | 0.89s | 0.95s | 0.32 | 0.18 |
| testbed/e8_pace_s2 | 255/255 | 19.2% | 0.4% | 1.38s | 0.53s | 0.74 | 0.37 |
| testbed/e8_pace_s3 | 251/251 | 21.8% | 2.9% | 1.59s | 0.97s | 0.66 | 0.36 |

KS = Kolmogorov-Smirnov distance between real and simulated latency distributions (0 = identical).
