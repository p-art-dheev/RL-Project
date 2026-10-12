# PACE: Preference-conditioned, Adaptive, Carbon-aware Edge scheduler

*Working name, rename freely.*

**One-line pitch:** a deep RL scheduler that places each task of a DAG job across the edge, fog and cloud **online, in milliseconds**. One trained policy covers the whole SLA-vs-carbon trade-off, and a feedback controller keeps the policy on the operator's SLA target. We validate it on a **real geo-distributed AWS + laptop-edge testbed** against the 2026 MERSEM framework, which was only ever evaluated in simulation.

Status: design proposal (pre-implementation). Last updated 2026-10-12.

---

## 0. TL;DR

| Item | Decision |
|---|---|
| **Base paper (to beat)** | **MERSEM**: Ramicetty et al., *Sustainable Graph Analytics Workload Scheduling with Evolutionary RL in Edge-Cloud Systems*, arXiv:2605.13489 (May 2026). It is the only one of the three papers that covers edge–cloud, and it is the most recent. |
| **RL lineage we build on** | DeepRM (Mao et al., HotNets 2016): online RL scheduling and the "frozen-time" multi-action trick. DeepRM2 (Ye et al., 2018): behaviour-cloning warm start. |
| **Core gap we attack** | MERSEM is an *offline, per-15-min-epoch* metaheuristic. It needs a workload predictor and oracle knowledge of job sizes, places whole jobs on one VM, fixes the SLA/carbon weight in advance, ignores failures and contention, and is evaluated only in simulation. Its "RL" is a tabular Q-learner that picks a mutation rate, and it uses **1 step per episode**, which makes it effectively a contextual bandit. |
| **Our novelty (4 claims)** | **N1** online, event-driven, *task-level* DAG placement with a GNN + per-node scoring policy that handles a variable number of heterogeneous nodes. **N2** one *preference-conditioned* policy that learns the full SLA–carbon front, plus an online controller that tracks a contractual SLA target. **N3** carbon-aware *temporal deferral* and robustness to failures, bursts and wrong runtime estimates, trained in a simulator calibrated from AWS measurements with domain randomisation. **N4** real-system validation: the same scheduler code runs in the simulator and on a live AWS + edge testbed. |
| **Algorithm** | PPO with action masking and SMDP (elapsed-time) discounting, GNN encoder, BC warm start from a strong heuristic. |
| **Use case** | Smart-city traffic and safety analytics: camera alerts (tight deadline, privacy-restricted), road-graph GNN analytics (MERSEM's workload class) and deferrable batch analytics, running on edge laptops, a local fog box and two AWS regions with very different grid carbon intensity. |
| **Primary metrics** | SLA-violation rate, operational gCO₂ (total and per job), P95/P99 latency, Pareto hypervolume (MERSEM's own metric), decision latency, recovery after failure, $ cost. |
| **Compute** | Training runs locally on the HP Victus (RTX 3050 4 GB plus CPU parallel envs). **No GPU is needed on AWS.** |
| **AWS budget** | Expected **≈ $35–45 of the $100**: small instances, stopped when idle, budget alarms. |


## 0.1 Implementation status (2-day build, Oct 2026)

| Item | Status |
|---|---|
| Dataset parser (MERSEM's dataset), workload classes A/B/C, calibrated DES simulator | **Done** (`pace/`) |
| Baselines: Random, Edge/Fog/Cloud-only, EFT, Carbon-greedy, CA-EFT (tuned), Job-EFT, **MERSEM** (+Oracle) | **Done** |
| PACE: size-agnostic node-scoring policy, BC warm start, preference-conditioned PPO, masks, DEFER, PI SLA controller | **Done** (`pace/rl/`) |
| Real testbed: worker, orchestrator (same scheduler code), dashboard, AWS deploy, calibration, camera, failure injection | **Done** (`testbed/`), deployed by you |
| Experiments E1–E5 (sim), E8 (real AWS), E9 (sim-to-real) | Scripts done; E1–E5 run here, E8/E9 run on your laptop |
| GNN DAG encoder | **Simplified:** DAG structure enters through critical-path and descendant features; the GNN is future work |
| PPO-Lagrangian variant, DEGRADE action, spot-interruption handling | Not built (COULD tier) |
| Real carbon traces | Synthetic hourly profiles until the Electricity Maps CSVs are added (`--carbon data/carbon@2024`) |

Deviations from the plan below, chosen for the 2-day deadline:
- The fog tier is AWS Mumbai rather than a local LAN box.
- The edge is the laptop, emulated as a Pi-class camera box: 1 core, ×3 slowdown.
- Live runs use a time-compressed carbon clock (1 grid hour per minute) so that carbon dynamics are visible in a 10-minute demo.

**Reward as implemented (v2):** `r = −[(1−w)·carbon_task / (work_task · carbon_per_work_fog) + w·penalty_job]`, with a short discount (γ = 0.8). Each decision gets its own task's carbon plus the full deadline penalty of its job. v1 split the penalty across a job's tasks, which drowned the deadline signal for large DAGs and made the policy ignore `w`. We diagnosed this on the test split and fixed it.

---

## 1. Papers analysed and choice of base paper

| | DeepRM (2016) | DeepRM2 / DeepRM_Off (2018) | **MERSEM (2026)** |
|---|---|---|---|
| Setting | Single pooled cluster, 2 resources | Same as DeepRM | **Edge–fog–cloud**, 500 devices, 4 fog DCs, 1 cloud DC |
| Workload | Synthetic independent jobs | Synthetic independent jobs | **DAG jobs** (Rezaee/Adabi dataset), GNN jobs |
| Objective | Avg slowdown or JCT | Same | **SLA-violation rate + carbon** (weighted sum) |
| Method | REINFORCE, image state, MLP | + CNN, + behaviour cloning from SJF | NSGA-style EA + tabular Q-learning to choose the perturbation rate |
| Decision mode | **Online** | Online and offline | **Offline batch per 15-min epoch** using a workload predictor |
| Evaluation | Sim only | Sim only | Sim only (extended EdgeCloudSim) |

**Choice: MERSEM is the base paper to beat.** It defines our problem (edge–cloud, DAG, SLA + carbon), provides the system models (latency, power, carbon), the dataset, the metrics (SLA rate, gCO₂, PHV) and the baselines. DeepRM and DeepRM2 give the RL design lineage: we take online decision making from DeepRM and the BC warm start from DeepRM2. Beating DeepRM on its own toy cluster benchmark would not be relevant to edge–cloud.

> **Viva risk:** MERSEM is an arXiv preprint. Its layout is ACM conference format, but no venue is stated. Ask the professor whether a preprint is acceptable as the base paper (see §16).

---

## 2. Critical analysis: assumptions, limitations, weaknesses

### 2.1 MERSEM

| # | Assumption or weakness in MERSEM | Why it matters in the real world | How PACE addresses it |
|---|---|---|---|
| M1 | **Offline batch optimisation per 15-min epoch.** A predictor supplies the next epoch's jobs, and the EA runs for the whole epoch to produce a mapping. | Real arrivals are bursty. Jobs that were not predicted, or that arrive mid-epoch, have no plan. A safety alert cannot wait for an epoch boundary. | **Online, event-driven** decisions per ready task, about 1 ms inference (N1). |
| M2 | **Full knowledge** of job characteristics (MI, exec time), resources and carbon at every node. | Runtimes are estimates. Burstable instances (t3) silently lose CPU credits. Carbon forecasts have errors. | The policy observes *noisy estimates*, and noise, hidden throttling and forecast error are randomised during training (N3). |
| M3 | **Whole job on one VM**, no partitioning. Jobs on a VM run *sequentially*. Edge devices run one job at a time. | Real pipelines are split across tiers (decode at the edge, detect at the fog, aggregate in the cloud). Real VMs run concurrent containers that contend for CPU. | **Task-level** placement over the DAG, with processor-sharing and contention models calibrated on AWS (N1, N3). |
| M4 | Exec time = Σ MI / MIPS, i.e. **uniform speed scaling** across task types. | Heterogeneity is task-dependent: ARM Graviton vs x86 differ by workload (SIMD, memory bandwidth), which is the "unrelated machines" model. | A per-(task type × instance type) speed matrix *measured* on AWS. |
| M5 | Communication counts only the **entry task's input**, over **static** bandwidth (40/150/100 Mbps). | Intermediate data and results must move, the result must return to the device, and WAN bandwidth and RTT fluctuate. | Every DAG edge transfer and the result return are modelled. Bandwidth and RTT are measured and randomised. |
| M6 | **Weighted sum with a fixed w** (w_s + w_c = 1) of a *rate in [0,1]* and *grams of CO₂ (~25,000)*. Normalisation is unspecified. Only three operating points are reported. | There is no meaningful exchange rate between CO₂ and SLA misses. Operators sign SLAs as **constraints** ("≥ 95 % of alerts in < 1 s"). A fixed w overshoots or undershoots the SLA as load and carbon change. | One **preference-conditioned** policy covers all w, and an **online SLA controller** adapts w to meet a target ε (N2). Rewards are explicitly normalised. |
| M7 | The "RL" is a tabular Q-learner choosing among 5 perturbation strengths. The chosen config uses **1 step per episode**, which makes it essentially a contextual bandit. The RL never makes a scheduling decision. | The learned knowledge does not transfer: the EA must be re-run every epoch, at a compute and energy cost that is **not reported**. | The RL agent *is* the scheduler. We report the scheduler's decision latency, CPU-seconds and energy. |
| M8 | **No failures, stragglers, partitions or churn.** | Fog boxes reboot, links drop, spot instances get reclaimed. A plan computed for a 15-min epoch goes stale when a node dies. | Masking of dead nodes, re-placement of lost tasks, failure randomisation in training, and live failure injection on the testbed. |
| M9 | **No admission, deferral or priority classes.** All methods hit **40–45 % SLA violations at 1100 jobs/epoch** (their Fig. 5b), so MERSEM barely helps under overload. | Real platforms have classes (critical vs batch) and can *shift deferrable work in time* to low-carbon hours. | Per-class SLAs and a **DEFER action** for delay-tolerant work: temporal plus spatial carbon shifting (N3). |
| M10 | **Simulation only.** Carbon of edge, fog and cloud is modelled, and nothing is validated on real systems. | Sim-to-real gaps are typically large in networked systems. | **N4**: a real AWS + laptop testbed, with sim-to-real fidelity *measured* (E9). |
| M11 | Baselines are only metaheuristics (GWO, CSA, SSA, PSO-GA). There are **no simple strong heuristics** (EFT/HEFT, carbon-greedy) and **no learned online baselines**. | Without these you cannot tell whether a complex method is needed at all. | We include EFT, carbon-aware EFT, DeepRM-style RL and MERSEM itself. |
| M12 | Reproducibility gaps: population size, generation budget, crossover type and state bins are unspecified, and there is no code. The text says "about half a million jobs", but the dataset has **51,895 jobs** (1.30 M tasks); we checked. | It is hard to reproduce faithfully. | We re-implement from the paper, document every assumption, and first **check that our MERSEM reproduces their ranking over PSO-GA** before claiming to beat it. Ask the authors for code (§16). |

### 2.2 DeepRM and DeepRM2 (lineage, not base)

- The cluster is one resource pool: no machines, no fragmentation, no network, no geography. The fixed-width image state cannot represent many heterogeneous nodes.
- Durations are known exactly, jobs are independent (no DAGs), there is a single objective per trained model, and workloads are synthetic Bernoulli/Poisson.
- REINFORCE with a time-step baseline has high variance. DeepRM2's CNN + BC gives modest gains, and neither paper reports confidence intervals.
- What we reuse: online decision making with frozen time between multiple decisions at one instant (DeepRM §3.2), the slowdown metric (reported as a secondary metric), and the BC warm start (DeepRM2 §3.3).

### 2.3 What we found in the base paper's dataset (Zenodo 4667690, CC-BY-4.0)

We downloaded and inspected it:
- 51,895 jobs and 1,301,653 tasks. Tasks per job: p10/p50/p90/max = 7/16/62/80. Max parallel width is up to 20.
- Job-level deadline slack (deadline − submission): p10/p50/p90 = 237/294/387 time units, with no negative values. These are usable.
- Task rows include MI size (`CPUNeed_Claimed`), RAM, storage, immediate predecessors and successors, and baseline lengths on IoT/fog/cloud. The `*_Real` and `*_Predicted` columns are **zero** in the rows we sampled, so the dataset has no ground-truth estimate error and we inject it ourselves. Task-level deadline fields look inconsistent, so we use job-level deadlines.
- Format pitfalls: `TaskDetails.txt` is **UTF-16**, and the `ListOfResourceNeeds` field contains unquoted commas that break naive CSV parsing. The parser must anchor on the trailing list columns.

---

## 3. The real-world problem

**Scenario: a smart-city traffic and safety platform.** A municipality runs cameras at junctions (edge), a small server room at the municipal office or university (fog), and rents public cloud capacity. Three kinds of work share this infrastructure:

| Class | Example DAG | Deadline | Constraints | Real-world driver |
|---|---|---|---|---|
| **A. Safety alert** (latency-critical) | capture → resize → detect (YOLO-n) → track/rules (wrong-way, pedestrian in lane) → alert back to device | ~0.5–1.5 s | Some feeds are **privacy-restricted** (raw frames may not leave the city), so masking applies | A camera box cannot run detection at frame rate. A far cloud adds 150–250 ms of RTT. |
| **B. Graph analytics** (MERSEM's class) | fetch sensor window → build subgraph → GNN inference (GCN/GraphSAGE/GAT) → post-process | seconds | Memory-heavy | Congestion propagation and forecasting on the road graph |
| **C. Batch analytics** (delay-tolerant) | fan-out/fan-in DAGs (from the dataset), e.g. hourly statistics, re-indexing, small model refresh | minutes–hours | **Deferrable** | Can be moved in *space* (green region) **and time** (green hours) |

**Why the problem exists:**
1. **Latency vs carbon conflict.** If you are in India, the nearest compute (local fog, AWS Mumbai) runs on one of the most carbon-intensive grids. Clean grids (Stockholm, Oregon) are 120–250 ms away. Neither "run local" nor "run green" is right for everything.
2. **Dynamics.** Arrivals are bursty (rush hour, incidents), grid carbon intensity changes hourly, links fluctuate and nodes fail. A plan made 15 minutes ago is stale.
3. **Heterogeneity.** The edge, fog and cloud tiers, and x86 vs ARM machines, differ by task type, not by a single speed factor.
4. **Contracts.** Operators state SLAs as targets per class, not as a weight.

**Why RL fits:** decisions are frequent and repetitive (lots of data), the best action depends on state that is hard to model jointly (queues × carbon × network × DAG position), the objective is delayed (deadline outcome is known only at job end), and heuristics must be re-tuned by hand whenever the objective or conditions change. We still include a **strong hand-tuned heuristic** (carbon-aware EFT) so the RL has to *earn* its place.

---

## 4. Method: PACE and the novelty claims

```
                 ┌────────────── Orchestrator (fog box) ──────────────┐
 job arrives ──▶ │ DAG tracker ─▶ ready task ─▶ Scheduler.place()      │ ──▶ worker on edge / fog / cloud
 (edge device)   │      ▲                       │  PACE policy (ms)    │        (Docker task executors)
                 │      │ completion, telemetry │  │  + masks/shield   │
                 │      └───────────────────────┤  └─ SLA controller(w)│ ◀── heartbeats, CPU util, queue
                 │ carbon feed (trace/API) ─────┘                      │
                 └─────────────────────────────────────────────────────┘
 The same Scheduler interface is used by the simulator and the real testbed, so identical code is evaluated in both.
```

**N1. Online, task-level, DAG-aware placement with a size-agnostic policy.**
The policy scores each candidate node with a shared network over (task embedding, node features, global features), followed by a softmax over the valid nodes. It therefore works for 5 nodes or 500, survives node failures via masking, and generalises to unseen topologies. This is unlike DeepRM's fixed image and unlike MERSEM's per-epoch genome. A 2-layer GNN over the job DAG gives the task critical-path and descendant context.

**N2. One preference-conditioned policy plus an online SLA-target controller.**
Train π(a | s, w), with w sampled per episode, so a single network covers the whole SLA–carbon front; MERSEM needs a separate optimisation per w. At deployment, a PI controller (a dual-ascent analogue of a Lagrange multiplier) adjusts w so that the observed SLA-violation rate tracks the operator's target ε while carbon is minimised. A fixed-w method cannot hold a target when load and carbon drift.

**N3. Temporal deferral and robustness by design.**
A DEFER action lets delay-tolerant tasks wait for lower-carbon hours within a bounded slack (temporal shifting, which MERSEM lacks). The training environment randomises runtime-estimate noise, burstable-CPU throttling, bandwidth/RTT, carbon-forecast error, failures and topology size. Action masks enforce memory, privacy and liveness, and a watchdog falls back to the heuristic if inference fails.

**N4. Calibrated sim-to-real validation.**
The simulator is parameterised from AWS profiling (runtime distributions per task × instance type, contention slowdown curves, measured RTT and bandwidth). The same experiments are then run on a real testbed, and the sim–real gap is reported (E9).

**Honest positioning (say this in the viva):** each ingredient has precedents. GNN DAG scheduling: Decima (Mao et al., SIGCOMM 2019). DRL dependent-task offloading: e.g. Wang et al., IEEE TC 2021. Preference-conditioned multi-objective RL: Abels et al. 2019, Yang et al. 2019. Constrained RL / PPO-Lagrangian: Ray et al. 2019, Stooke et al. 2020. Carbon-aware temporal shifting: Wiesner et al. 2021, "Let's Wait Awhile". Our contribution is **the combination for carbon + SLA edge–cloud DAG scheduling, which directly fixes the base paper's limitations M1–M11, plus real-system evidence**. Before final write-up, do a focused literature search (2023–2026, "carbon-aware DRL edge cloud DAG offloading") and avoid the word "first" unless that search supports it.

---

## 5. RL formulation

### 5.1 Decision process (semi-MDP)
- **Decision epochs** t_k: a task becomes *ready* (all parents done), a deferred task's timer fires, or a node failure orphans tasks. Several ready tasks at the same instant are decided sequentially with time frozen (DeepRM trick), so the action space stays linear in the number of nodes.
- **Discounting** uses elapsed time: G_k = Σ_{k'≥k} γ^{(t_{k'} − t_k)/τ} r_{k'}, because decisions are irregularly spaced.

### 5.2 Observation s_k
| Group | Features (all normalised) |
|---|---|
| **Task** | log est. work (MI or profiled ref-seconds), estimate-uncertainty bucket, memory, class one-hot, privacy flag, **slack** = deadline − now − est. remaining critical path, DAG depth, #descendants, remaining-CP fraction, bytes to fetch from each parent location |
| **Job DAG (GNN)** | per-DAG-node: est. work, status {done, running, ready, pending}, tier where placed; 2 layers of message passing (≈64-d), producing a task embedding + mean-pooled job embedding |
| **Per node n** (variable count) | tier, **task-type-specific speed factor** (profiled), free cores, est. queue wait (s), free memory, CPU util, carbon intensity CI_n now and forecast (+1 h, +3 h, with noise), marginal W per core (power model), **est. transfer time** from parents' locations (bytes/BW + RTT), alive flag, recent failure count, burst-credit proxy (t3), warm/cold flag |
| **Global** | time-of-day sin/cos, arrival-rate EWMA per class, recent SLA-violation rate per class, **preference w** |

### 5.3 Action a_k
`a ∈ {node_1 … node_N} ∪ {DEFER}` with **masks**:
- the node is dead or partitioned, or lacks memory;
- privacy: a restricted task cannot go outside the city (cloud masked);
- an edge device runs only its *own* jobs (as in MERSEM);
- DEFER is allowed only for class C, and only if slack after the deferral is ≥ 1.5 × est. remaining CP and the task has been deferred fewer than K times (prevents starvation);
- *(stretch)* DEGRADE: run a lighter model variant (YOLO-n vs -s) under overload, with an accuracy penalty.

### 5.4 Reward between events k and k+1
```
r_k = −(1 − w) · Ĉ_k  −  w · Ŝ_k
Ĉ_k = [ Σ_n E^dyn_n(t_k, t_{k+1}) · CI_n(t)  +  E^tx_k · CI_tx ] / C_ref          (operational gCO2, normalised)
Ŝ_k = Σ_{jobs j completing in (t_k, t_{k+1}]}  ρ_class(j) · 1[L_j > D_j] · (1 + min(1, (L_j − D_j)/D_j)) / S_ref
```
- C_ref is the mean per-job carbon of a cloud-only policy, and S_ref is the expected completions per event. Both make w meaningful, which fixes M6.
- The tardiness term gives gradient beyond the binary miss. ρ_class weights critical classes.
- Optional dense shaping: −β·w·(#jobs whose slack < 0)·Δt. Ablate it.
- Idle power is reported in totals (for comparability with MERSEM) but excluded from the reward, because the scheduler cannot change it while nodes stay on.

### 5.5 Online SLA controller (deployment)
Every window of W completed class-A jobs: `e = SLA_rate_window − ε;  w ← clip(w + K_p·e + K_i·Σe, 0, 1)`. Stretch goal: one controller per class.

### 5.6 Learning algorithm
- **PPO** (clip 0.2, GAE 0.95, lr 3e-4, entropy 0.01 → 0.001) with **masked logits**, 8–16 parallel envs, roughly 2–5 M decisions.
- **Network:** GNN encoder (2 × 64) → node-scoring MLP (3 × 128) shared across nodes → logits. A DEFER head on the task and global features. A critic on the pooled embeddings. About 60–100 K parameters. We use plain PyTorch message passing (no PyG dependency).
- **Warm start:** behaviour cloning on carbon-aware EFT decisions (DeepRM2 idea), then PPO fine-tuning. The ablation reports the convergence speed-up.
- **Curriculum:** low → high load, then failures switched on.
- **Domain randomisation:** topology size (5–30 nodes in testbed-like envs, up to MERSEM scale), runtime noise σ ∈ [0, 0.4], bandwidth ±50 %, RTT jitter, carbon traces from different zones and years, failure rate, burst intensity.
- **Splits:** carbon 2023 for train and 2024 for test; dataset jobs in the first 70 % of the timeline for train and the last 30 % for test; held-out topologies.
- **Stretch:** PPO-Lagrangian with a separate cost critic, as an alternative to N2, compared directly.

---

## 6. Environment and workload

### 6.1 Simulator ("calibrated twin")
- A custom Python discrete-event simulator (heapq) with a Gymnasium wrapper. It models processor sharing per node with a contention slowdown curve, the memory limit, link transfers with RTT + bytes/BW, failures, and the carbon and power models (MERSEM Eq. 8–12 plus a PUE factor).
- **MERSEM-scale config** for E1–E2: 1 cloud DC (20 servers, 88 VMs), 4 fog DCs (5 servers, 20 VMs each), 500 edge devices (half 4 × 2000 MIPS phones, half 6 × 2400 MIPS cameras, 3 W idle and 12 W peak), links 40/150/100 Mbps, 15-min epochs. These values are copied from MERSEM §6.1.
- **Testbed-mirror config** for E8–E9: the exact real topology with measured parameters.

### 6.2 Data sources
| Need | Source | Notes |
|---|---|---|
| DAG jobs | **Rezaee & Adabi, Zenodo 4667690** (the dataset MERSEM uses) | CC-BY-4.0. Already inspected (§2.3). |
| Arrival dynamics | Dataset timestamps, modulated by a diurnal and flash-crowd process. Optional: Azure Functions 2019 trace shape. | For burst scenarios |
| Carbon intensity | **Electricity Maps Data Portal**: free hourly CSVs (2021–2024, ODbL) for e.g. IN-WE (Mumbai), SE-SE3 (Stockholm), US-MIDA-PJM (N. Virginia), US-NW-BPAT (Oregon). The UK Carbon Intensity API offers free live data and forecasts if we need a *live* feed. | Needs a free account (you). Verify zone codes on the portal. Location-based accounting, as in the Green Software Foundation SCI. |
| Task runtimes, contention, heterogeneity | **Profiled on AWS** per (task type × instance type), plus k-concurrent runs to fit contention curves | Profiling run, ~6 h |
| Network | **Measured** RTT (ping) and bandwidth (iperf3) between laptop, fog and regions over a day | Feeds the twin and randomisation ranges |
| Power models | Cloud Carbon Footprint coefficients (min/max W per vCPU by microarchitecture, PUE). RAPL on the laptop if running Linux. | AWS has no per-VM power meter. Say so honestly. |
| Vision workload | Laptop webcam (live) + a public traffic video for repeatable runs (e.g. UA-DETRAC; check its licence) | YOLO-n via ONNX Runtime CPU. Ultralytics is AGPL; a MobileNet-SSD alternative is Apache-2.0. |
| Graph workload | Cora / CiteSeer / PubMed with GCN / GraphSAGE / GAT (the same as MERSEM §6.5). Optional road graph METR-LA. | Pre-trained small models, inference only |

---

## 7. Real testbed on AWS ($100 budget)

### 7.1 Topology
| Tier | Real hardware | Role in the story |
|---|---|---|
| **Edge** | HP Victus (webcam; worker container limited to 1–2 cores to emulate a camera box) + teammates' laptops / phones as cameras | Real camera, real Wi-Fi |
| **Fog** | One teammate laptop or desktop on the same LAN/hotspot (the "municipal server room"). It also hosts the **orchestrator**, so edge decisions need no WAN round trip. | Close, but on a carbon-heavy local grid |
| **Cloud – near** | AWS region close to you. With a normal account: **ap-south-1 Mumbai**. With Learner Lab: **us-east-1**. 1 × c7i.large (x86) + 1 × t3.medium (burstable) | Mid latency, high carbon |
| **Cloud – green** | **eu-north-1 Stockholm** (normal account) or **us-west-2 Oregon** (Learner Lab). 1 × c7g.large (Graviton/ARM) + 1 × t3.medium | High latency, low carbon, and ARM heterogeneity |

- **Connectivity:** a Tailscale or WireGuard mesh, so laptops behind NAT and the EC2 instances reach each other directly. Fallback: workers *pull* tasks over outbound HTTPS from a tiny relay on a t4g.small.
- **Software on every node:** Docker image `pace-worker` (task executors + telemetry: CPU util, queue, heartbeat). The orchestrator is FastAPI/asyncio and writes events to Parquet/SQLite. Deploy and teardown are scripted with boto3 or Terraform, and every resource is tagged `project=pace`.
- **Fault injection:** `docker stop` or `ec2 stop` of a node, `tc netem` for delay/loss/bandwidth caps, a CPU hog for stragglers, and a carbon-spike event in the replayed trace.
- **Clock skew:** latency is always measured at the orchestrator, or as a round trip at the origin device, so the nodes do not need synchronised clocks.

### 7.2 Carbon accounting on the testbed (be explicit in the report)
`E_node = Σ_t P(u_t)·Δt · PUE`, where P comes from the CCF per-vCPU min/max coefficients and the *measured* CPU utilisation u_t. Then `gCO₂ = E · CI(zone, t)`, with CI taken from the replayed Electricity Maps hourly trace for that region's grid zone. In demos the trace is time-compressed and the compression is shown on screen. This is **location-based** accounting. AWS's renewable purchases are **market-based** accounting and are deliberately not used; we state that.

### 7.3 Budget (approximate on-demand prices, re-check on the AWS pricing page)
| Item | Rate | Hours | Cost |
|---|---|---|---|
| 1 c7i.large + 1 c7g.large + 2 t3.medium (+ optional t4g.small relay) | ≈ $0.26–0.29/h | ~70 h total (profiling 6, development 30, experiments ~25, rehearsals and demo ~10) | ≈ $20 |
| Public IPv4 ($0.005/h each) + EBS gp3 8 GB × 5 | — | — | ≈ $3–5 |
| Inter-region transfer ($0.02/GB) + internet egress (first 100 GB/month free) | frames downscaled to ~15 KB | — | < $5 |
| Live A/B demo (two mirrored worker pools, ~3 h) | ≈ $0.6/h | 3 | ≈ $2 |
| **Expected total** | | | **≈ $30–40, leaving ~$60 buffer** |

**Guardrails:** AWS Budgets alerts at $20/$40/$60/$80; a `make down` teardown script; stop instances whenever they are not in use; never leave instances running overnight; no GPU instances. *Note:* a stopped instance still pays for EBS, and for any Elastic IP.

**Training costs $0 on AWS.** It runs on the Victus: the CPU runs the parallel simulator envs and the RTX 3050 (4 GB) handles the PPO updates, which is plenty for a ~100 K-parameter model. Expect a few hours per full run. Keep the laptop plugged in and cooled, because thermal throttling skews timing.

---

## 8. Edge cases: how each is modelled, handled and tested

| Edge case | Modelled in sim | Handled by PACE | Tested by |
|---|---|---|---|
| Resource contention / co-location interference | Processor sharing + contention curve fitted on AWS (k concurrent tasks) | Queue-wait and util features; learns to spread load | E3, E8 |
| Overloaded node / queue explosion | Queue caps, memory limits | Masks at the cap; DEFER for class C; class priority via ρ | E2 (100→1100 jobs/epoch), burst scenario |
| Changing workloads (diurnal, flash crowd, class-mix shift) | NHPP + bursts + mix drift | Arrival-rate EWMA features; SLA controller re-tunes w | E3, E5 |
| SLA violations (per class) | Deadlines from the dataset; class A/B/C | Slack features, tardiness reward, SLA-target controller | All; E5 specifically |
| Heterogeneous resources (tier, x86 vs ARM, burstable t3) | Task-type × instance speed matrix; hidden burst credits | Per-node speed features; robustness to hidden throttling | E6, E8 |
| Task dependencies (DAG) and data transfer | Full DAG, transfer on every edge, result return | GNN embedding, transfer-time features | All |
| Node failure / crash | Poisson failures; queued and running tasks lost | Mask the dead node, re-place orphaned tasks, fallback heuristic | E4, live demo |
| Network partition (edge cut off from cloud) | Link-down events | Cloud masked, so tasks run on local tiers | E4 |
| Straggler / slow node | Random slow-down factor | Learns from queue-wait vs expected; avoids it | E4 |
| Spot interruption (2-min notice) | Optional event | Drain + re-place (stretch) | Stretch |
| Inaccurate runtime estimates | Estimate noise σ ∈ [0, 0.4] (dataset lacks real values) | Trained under noise; uncertainty feature | E3 |
| Carbon spike / forecast error | Noisy forecast; replayed real traces | DEFER and spatial shift; forecast features | E3, demo |
| Cold start (first task on an idle node) | Extra start delay | Warm/cold feature | E8 |
| Privacy / data residency | Restricted flag | Hard mask (never violated) | Unit tests + E8 |
| Starvation of deferred work | Deferral counter | Bounded deferrals + slack rule | Unit tests |
| Scheduler failure or out-of-distribution state | Inference exception, NaN, invalid action | Watchdog falls back to carbon-aware EFT and logs it | Fault test |
| Empty system / single node / huge DAG (80 tasks) | Edge configs | Size-agnostic policy, masked padding | Unit tests |

---

## 9. Baselines

| Baseline | Why include it |
|---|---|
| Random, Round-robin | Sanity floor |
| Edge-only (local), Cloud-only (greenest region) | Extremes of the latency–carbon trade-off |
| **EFT** (earliest finish time, online HEFT-style) | Strong latency heuristic |
| **Carbon-greedy** (lowest CI node that fits) | Strong carbon heuristic |
| **Carbon-aware EFT (CA-EFT)**: lowest-carbon node whose estimated finish meets the deadline, else EFT | **Strongest hand-crafted baseline**, and the BC teacher. If PACE cannot beat it, we say so. |
| **MERSEM-Oracle**: exact runtimes and perfect knowledge of the next epoch's arrivals | Upper bound for the batch approach, on MERSEM's home turf |
| **MERSEM-Realistic**: the same predictor information as everyone else (EWMA forecast, noisy estimates), rolling epoch, greedy fallback for unplanned arrivals | Fair real-world comparison |
| PSO-GA (one of MERSEM's own baselines) | To check that our MERSEM re-implementation reproduces their ranking |
| DeepRM-adapted (REINFORCE, flat MLP, fixed node slots) | RL lineage baseline |

**Fairness rules:** every method gets the same information (except the oracle variant), the same normalised objective, the same carbon and power model, and the same traces and seeds. MERSEM gets the same wall-clock budget per epoch as in its paper, scaled. We also run **PACE restricted to job-level placement**, to separate *learning* gains from *granularity* gains (an examiner will ask about this).

---

## 10. Metrics

- **SLA-violation rate** per class and overall: fraction of jobs with L_j > D_j. This is MERSEM's primary metric.
- **Operational carbon**: total gCO₂ (idle + dynamic, comparable with MERSEM), gCO₂ per job, and the split across tiers.
- **Latency**: mean, P50/P95/P99 end-to-end. Mean job slowdown (DeepRM's metric).
- **Pareto hypervolume (PHV)** over (SLA rate, gCO₂) with a fixed reference point. This is MERSEM's metric: PACE sweeps w, MERSEM uses its population.
- **Scheduler overhead**: decision latency (ms), CPU-seconds per 1000 decisions, and estimated scheduler energy.
- **Robustness**: SLA rate during the failure window and time to recover to the pre-failure SLA.
- **SLA-target tracking error**: |observed SLA rate − ε| over time.
- **Cost**: AWS $ per 1000 jobs on the testbed.
- **Sim-to-real fidelity**: KS distance between simulated and real latency CDFs, and relative error in gCO₂/job and SLA rate.
- **Statistics**: ≥ 10 seeds in simulation and ≥ 5 runs per method on the testbed, mean ± 95 % CI. Runs are paired on identical traces and tested with a Wilcoxon signed-rank test. Testbed runs are **interleaved** (ABCDE ABCDE …), so drift in real network conditions does not favour any one method.

---

## 11. Experiments

| ID | Question | Setup | Expected result (a hypothesis, not a promise) |
|---|---|---|---|
| **E1** | Do we beat MERSEM on *its own* setup? | MERSEM-scale sim, 500 jobs/epoch, static conditions | Comparable to MERSEM-Oracle, better than MERSEM-Realistic on SLA at equal or lower carbon. PHV ≥ MERSEM. |
| **E2** | Scalability (mirrors MERSEM Fig. 5–6) | jobs/epoch 100 → 1100; edge devices 300 → 900; fog DCs 2 → 8 | Smaller SLA degradation under overload, thanks to deferral and priority |
| **E3** | Realistic dynamics | estimate noise σ ∈ {0, 0.2, 0.4}, bursts, bandwidth jitter, carbon-forecast error | The gap over MERSEM *widens* as realism increases |
| **E4** | Failures | fog crash, edge–cloud partition, straggler | Lower SLA in the failure window, recovery in seconds vs the next epoch for MERSEM |
| **E5** | SLA-target tracking | ε ∈ {5 %, 10 %, 20 %} under a load ramp; fixed-w vs controller | The controller holds ε and minimises carbon, while fixed-w overshoots or undershoots |
| **E6** | Generalisation | unseen topologies, DAG shapes, carbon zones/year | Small zero-shot degradation |
| **E7** | Overhead | decision latency, CPU-s | About 1 ms per decision vs MERSEM's full-epoch search |
| **E8** | **Real testbed** | PACE, MERSEM-Realistic, CA-EFT, EFT, Cloud-only. Scenarios: normal, burst, fog failure. 5 interleaved runs × 20 min each. | Same ranking as in simulation |
| **E9** | Sim-to-real gap | Replay the E8 traces in the testbed-mirror sim, with and without calibration | Calibration closes most of the gap (report KS) |

**Ablations:** (A1) no GNN (flat features); (A2) job-level placement only; (A3) fixed w, no controller; (A4) no DEFER / no carbon forecast; (A5) no BC warm start (convergence curve); (A6) no domain randomisation (sim-to-real gap); (A7) no estimate-noise training.

If MERSEM-Oracle beats PACE on static E1, **report it**. Our claim is about realistic online conditions (E3–E5, E8), and that is the claim that matters in practice.

---

## 12. Live demo (about 10 minutes)

**Dashboard** (single web page with FastAPI + WebSocket and Plotly/Leaflet; Streamlit as a fallback):
- a map of nodes (laptop edge, fog, two AWS regions) with live load, carbon intensity and RTT;
- animated task flows;
- per-scheduler gauges: SLA % vs target, cumulative gCO₂, P95 latency;
- the live webcam with detection boxes and per-alert latency;
- a **decision explainer** for every placement: the top-3 node scores with their transfer, queue and carbon terms. This addresses DeepRM's own admission that RL decisions are hard to explain.

**Script:**
1. **Setup (1 min).** Show the topology, and the real latency vs carbon tension between the near region and the green region.
2. **A/B run (3 min).** The *same* job stream is mirrored to two identical worker pools, one scheduled by MERSEM-Realistic (or CA-EFT) and one by PACE. The counters diverge live.
3. **Carbon spike (1 min).** A time-compressed CI spike in the near region: batch work shifts to the green region or is deferred, and the alerts stay local.
4. **Rush hour (1 min).** Add camera streams: PACE protects class A and defers class C, while the baseline's SLA collapses.
5. **Fog failure (1 min).** Kill the fog node: PACE re-places tasks within seconds, and the SLA dips and recovers.
6. **Professor's knob (1 min).** Move the SLA target slider from 90 % to 99 %: the controller raises w, the SLA tightens and carbon rises. This shows the trade-off is tunable at runtime with no retraining.
7. **Results (2 min).** The pre-computed E1–E9 plots: Pareto front vs MERSEM, CIs, ablations.

**Backup:** a recorded video of the full demo, plus a "sim-replay" mode of the dashboard that needs no network (for when university Wi-Fi blocks UDP or ports).

---

## 13. Scope, timeline, team split

**MUST:** calibrated simulator; PACE (GNN + PPO + masks + preference conditioning); all heuristics + MERSEM re-implementation; E1–E5, E7; testbed with laptop edge, fog and 2 AWS regions; E8 with ≥ 4 methods; dashboard + live demo with failure injection.
**SHOULD:** DEFER action, SLA controller (E5), E6, E9, ablations A1–A7.
**COULD:** DEGRADE action, spot-interruption handling, PPO-Lagrangian variant, online fine-tuning on the testbed.

Suggested 10-week plan (adjust to your deadline):
| Weeks | Track 1: Sim & RL | Track 2: Testbed & infra | Track 3: Baselines & eval |
|---|---|---|---|
| 1 | Repo, dataset parser, DES skeleton | AWS budget alarms, Docker worker, Tailscale mesh | Heuristics (EFT, CA-EFT, carbon-greedy) |
| 2–3 | Gym env, MERSEM-scale config, unit tests | Profiling runs (runtimes, contention, RTT/BW) | MERSEM + PSO-GA re-implementation; reproduce their ranking |
| 4–5 | PACE network, BC warm start, PPO training | Orchestrator + same Scheduler interface; fault injection | E1–E2 |
| 6–7 | Domain randomisation, DEFER, controller | Calibrate the twin from profiles; end-to-end testbed run | E3–E7 |
| 8 | Ablations | **E8 real runs**, E9 | Statistics, plots |
| 9 | Fixes | Dashboard + A/B mirroring | Report draft |
| 10 | — | Demo rehearsals × 3, recorded backup | Viva prep |

---

## 14. Risks and mitigations

| Risk | Mitigation |
|---|---|
| RL fails to beat CA-EFT | BC warm start (starts near the heuristic); reward and feature iteration; honest reporting; a hybrid "RL + shield" is still a contribution |
| Large sim-to-real gap | Calibration from profiling, domain randomisation, and E9 quantifies the gap |
| AWS budget overrun | Small instances, alarms, teardown script, training done locally |
| Learner Lab limits (2 regions, ≤ 9 instances per region, nano–large sizes, 4 h sessions) | The topology already fits: us-east-1 + us-west-2, with the fog on a local machine |
| Demo-day network problems | Recorded backup, offline sim-replay mode, phone hotspot |
| MERSEM re-implementation is unfaithful | Follow the paper's hyperparameters, document the gaps, reproduce their ranking vs PSO-GA, ask the authors for code |
| Timeline slip | MUST/SHOULD/COULD tiers; sim results alone already beat the base paper's evaluation |

---

## 15. Viva preparation: likely questions

1. **Why RL and not a heuristic?** Trade-offs depend on state, conditions are non-stationary, and the objective can change at runtime. We include CA-EFT and show where RL helps (dynamics, failures, tunability) and where it does not.
2. **Isn't this just Decima?** Decima is a single-cluster Spark scheduler with no network, carbon or SLA constraints. We borrow its node-scoring and DAG-encoding *idea*; our contributions are N2–N4 in a geo-distributed setting.
3. **Is comparing online with offline fair?** We give MERSEM an oracle variant (best case) and a realistic variant, give everyone the same information, and run PACE at job-level granularity as a control.
4. **How do you measure carbon on AWS?** Measured utilisation × CCF power coefficients × PUE × location-based grid intensity. AWS exposes no per-VM power. This is the same model class MERSEM uses.
5. **AWS buys renewables, so isn't the carbon zero?** That is market-based accounting. Scheduling decisions affect the physical grid, so carbon-aware computing research uses location-based accounting.
6. **How do you know the simulator is right?** Calibration from real profiles, plus E9 measuring the sim–real gap.
7. **What stops a catastrophic action?** Hard masks (memory, liveness, privacy), bounded deferral, and a watchdog fallback.
8. **What about the carbon cost of training?** We measure the training energy on the laptop and report the break-even time against the savings.
9. **Why is the testbed so small?** Budget. Simulation gives scale and statistical power; the testbed gives validity. MERSEM had no testbed at all.

---

## 16. What we need from you

**Questions (they change the design):**
1. **What kind of AWS credit is the $100?** A normal account with promotional credits, or **AWS Academy Learner Lab**? Learner Lab limits you to us-east-1/us-west-2, ≤ 9 instances per region, roughly nano–large sizes and 4-hour sessions, and it rotates credentials. When do the credits expire?
2. **Deadline and team size?** And is a written report or paper expected, and in what format?
3. **Location (city/country)?** This picks the near region and the grid zone; I have assumed India and Mumbai.
4. **Hardware:** Victus CPU model and OS (Windows, WSL2 or Linux)? How many other laptops or phones can act as edge cameras or the fog box? Any Raspberry Pi or Jetson?
5. **Professor's constraints:** is an arXiv preprint (MERSEM) acceptable as the base paper? Is the smart-city use case OK, or is another domain preferred (e.g. healthcare monitoring)?
6. **Scope:** do you agree with the MUST/SHOULD/COULD tiers?

**Actions on your side:**
- Create a free **Electricity Maps Data Portal** account and download the hourly 2023 + 2024 CSVs for the zones in §6.2. Commit them under `data/carbon/` or share them with me.
- Set up **AWS Budgets alerts** now ($20/$40/$60/$80).
- *(Optional, high value)* Email the MERSEM authors and ask for their code and simulator parameters (population size, generations, normalisation).
- **AWS credentials for this cloud session:** never paste keys into chat. Add them in the environment settings (session title bar → environment → Edit → secrets/env vars) as `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (and `AWS_SESSION_TOKEN` for Learner Lab). With Learner Lab the credentials expire with each session, so it is simpler to run the deploy scripts from your laptop.
- On the Victus: install Docker, plus the NVIDIA driver + CUDA PyTorch (Linux or WSL2 recommended).

---

## References
- H. Mao, M. Alizadeh, I. Menache, S. Kandula. *Resource Management with Deep Reinforcement Learning.* HotNets 2016.
- Y. Ye et al. *A New Approach for Resource Scheduling with Deep Reinforcement Learning.* arXiv:1806.08122, 2018.
- P. Ramicetty et al. *Sustainable Graph Analytics Workload Scheduling with Evolutionary Reinforcement Learning in Edge-Cloud Systems (MERSEM).* arXiv:2605.13489, 2026.
- S. A. Ali Rezaee, S. Adabi. *Jobs (DAG workflow) and tasks dataset…* Zenodo 10.5281/zenodo.4667690, CC-BY-4.0.
- H. Mao et al. *Learning Scheduling Algorithms for Data Processing Clusters (Decima).* SIGCOMM 2019.
- J. Wang et al. *Dependent Task Offloading for Edge Computing based on Deep Reinforcement Learning.* IEEE Trans. Computers, 2021.
- A. Abels et al. *Dynamic Weights in Multi-Objective Deep RL.* ICML 2019. R. Yang et al. *A Generalized Algorithm for Multi-Objective RL and Policy Adaptation.* NeurIPS 2019.
- A. Ray, J. Achiam, D. Amodei. *Benchmarking Safe Exploration in Deep RL.* 2019. A. Stooke et al. *Responsive Safety in RL by PID Lagrangian Methods.* ICML 2020.
- P. Wiesner et al. *Let's Wait Awhile: How Temporal Workload Shifting Can Reduce Carbon Emissions in the Cloud.* Middleware 2021.
- C. Sonmez et al. *EdgeCloudSim.* FMEC 2017.
- Electricity Maps Data Portal (hourly carbon intensity, ODbL). Cloud Carbon Footprint methodology (power coefficients, PUE).
