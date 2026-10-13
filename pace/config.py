"""Topology and workload configuration.

The default topology mirrors the real testbed:
  edge  : camera boxes / gateways in Coimbatore (CBE), grid zone IN-SO
  fog   : AWS ap-south-1 Mumbai (BOM), grid zone IN-WE   -- near, carbon-heavy
  cloud : AWS eu-north-1 Stockholm (ARN), grid zone SE-SE3 -- far, very low carbon

All numbers marked (calib) are placeholders that `testbed/calibrate.py` replaces with
measurements from the real nodes (RTT, bandwidth, per-task-type speed).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

EDGE, FOG, CLOUD = 0, 1, 2
TIER_NAMES = ("edge", "fog", "cloud")
TASK_TYPES = ("generic", "vision")

# Power coefficients per vCPU (W), after the Cloud Carbon Footprint methodology:
# x86 averages ~0.74 W idle / 3.5 W max per vCPU; Graviton ~0.47 / 1.69.
POWER = {"x86": (0.74, 3.5), "arm": (0.47, 1.69)}
CLOUD_PUE = 1.135  # CCF value for AWS


@dataclass
class NodeSpec:
    name: str
    tier: int
    loc: str
    zone: str
    cores: int
    speed: dict  # task type -> speed relative to 1 reference core (c7i vCPU) (calib)
    idle_w: float  # whole-node idle power (W)
    max_w: float  # whole-node max power (W)
    pue: float = 1.0
    arch: str = "x86"
    owner: str | None = None  # edge device that owns this node (edge tier)
    mem_gb: float = 4.0
    url: str | None = None  # testbed endpoint
    contention: float = 0.15  # extra compute time per task when all cores are busy (2 SMT threads ~0.8) (calib)


def cloud_node(name, tier, loc, zone, arch="x86", vcpu=2, speed=None, mem=4.0) -> NodeSpec:
    lo, hi = POWER[arch]
    sp = speed or ({"generic": 1.0, "vision": 1.0} if arch == "x86" else {"generic": 0.85, "vision": 0.6})
    return NodeSpec(name, tier, loc, zone, vcpu, dict(sp), lo * vcpu, hi * vcpu, CLOUD_PUE, arch, None, mem)


def edge_node(name, loc="CBE", zone="IN-SO") -> NodeSpec:
    # Raspberry-Pi-class camera box: 1 task at a time (as in MERSEM), ~0.3x a cloud vCPU.
    return NodeSpec(name, EDGE, loc, zone, 1, {"generic": 0.3, "vision": 0.3}, 2.0, 6.0, 1.0, "arm", name, 2.0)


@dataclass
class Topology:
    nodes: list
    # (loc_a, loc_b) -> (rtt seconds, bandwidth Mbps); symmetric. (calib)
    net: dict = field(default_factory=lambda: {
        ("CBE", "BOM"): (0.035, 20.0),
        ("CBE", "ARN"): (0.160, 15.0),
        ("BOM", "ARN"): (0.120, 200.0),
    })
    lan: tuple = (0.001, 500.0)
    country: dict = field(default_factory=lambda: {"CBE": "IN", "BOM": "IN", "ARN": "SE"})
    ctrl_loc: str | None = None  # where the orchestrator runs (real testbed: the laptop); None = no control RTT

    def link(self, a: str, b: str) -> tuple:
        if a == b:
            return self.lan
        return self.net.get((a, b)) or self.net[(b, a)]


def testbed_topology(n_edge: int = 2) -> Topology:
    nodes = [edge_node(f"edge{i}") for i in range(n_edge)]
    nodes += [
        cloud_node("bom-c7i", FOG, "BOM", "IN-WE", "x86"),
        cloud_node("bom-t4g", FOG, "BOM", "IN-WE", "arm"),
        cloud_node("arn-c7i", CLOUD, "ARN", "SE-SE3", "x86"),
        cloud_node("arn-t4g", CLOUD, "ARN", "SE-SE3", "arm"),
    ]
    return Topology(nodes)


def city_topology(n_edge: int = 8, n_fog: int = 3, n_cloud: int = 4) -> Topology:
    nodes = [edge_node(f"edge{i}") for i in range(n_edge)]
    for i in range(n_fog):
        nodes.append(cloud_node(f"bom{i}", FOG, "BOM", "IN-WE", "x86" if i % 2 == 0 else "arm"))
    for i in range(n_cloud):
        nodes.append(cloud_node(f"arn{i}", CLOUD, "ARN", "SE-SE3", "x86" if i % 2 == 0 else "arm"))
    return Topology(nodes)


@dataclass
class Workload:
    split: str = "train"  # dataset split: first 70% of jobs (train) / last 30% (test)
    horizon: float = 3600.0  # seconds of arrivals per episode (then drain)
    start_hour: float | None = None  # local hour of day at t=0 (None = random)
    rate_a: float = 0.25  # class-A (camera alert) jobs/s per camera
    rate_bc: float = 0.06  # class-B/C (dataset DAG) jobs/s in total
    frac_b: float = 0.6  # share of dataset jobs that are class B (rest C)
    privacy_a: float = 0.3  # share of camera feeds that may not leave the country
    deadline_a: float = 1.0  # s
    beta_b: float = 2.0  # class-B deadline = beta * dataset_slack_ratio * critical path + 2 s
    deadline_c: tuple = (1800.0, 7200.0)  # class-C deadline range (s), deferrable
    work_scale: float = 1.0  # multiplies dataset task work
    data_scale: float = 1.0  # multiplies dataset edge data sizes
    est_noise: float = 0.2  # sigma of log-normal runtime-estimate error
    diurnal: bool = True
    bursts: list = field(default_factory=list)  # [(t_start, duration, multiplier), ...]
    failures: list = field(default_factory=list)  # [(t, node_name, downtime), ...]
    fail_rate: float = 0.0  # random failures per server-node per hour
    straggle_rate: float = 0.0  # random slow-down episodes per node per hour
    carbon_source: str = "synthetic"  # or a directory of Electricity Maps CSVs
    priority: bool = True  # class-priority node queues (A > B > C); False = FIFO (ablation)


def randomized(base_topo: Topology, wl: Workload, rng, twin: bool = False) -> tuple[Topology, Workload]:
    """Domain randomisation used during training.

    twin=True keeps base_topo's nodes (the calibrated digital twin of the real testbed, from
    testbed/nodes.json) and jitters the measured speeds around their calibrated values."""
    if twin:
        topo = copy.deepcopy(base_topo)
        for n in topo.nodes:
            n.speed = {k: v * float(rng.uniform(0.5, 2.0) if (n.tier == EDGE and k == "vision") else rng.uniform(0.7, 1.4))
                       for k, v in n.speed.items()}
            n.contention = max(0.0, n.contention + float(rng.uniform(-0.15, 0.15)))
    else:
        topo = city_topology(int(rng.integers(2, 7)), int(rng.integers(1, 4)), int(rng.integers(1, 4)))
        for n in topo.nodes:
            if n.tier != EDGE:
                n.speed = {k: v * float(rng.uniform(0.8, 1.2)) for k, v in n.speed.items()}
    topo.net = {k: (rtt * float(rng.uniform(0.7, 1.5)), bw * float(rng.uniform(0.5, 1.5)))
                for k, (rtt, bw) in base_topo.net.items()}
    w = copy.deepcopy(wl)
    n_srv = sum(1 for n in topo.nodes if n.tier != EDGE)
    w.rate_a = float(rng.uniform(0.1, 0.4))
    w.rate_bc = float(rng.uniform(0.002, 0.008)) * n_srv  # nominal ~0.004 per server
    w.est_noise = float(rng.uniform(0.0, 0.4))
    w.fail_rate = float(rng.choice([0.0, 0.0, 0.5, 1.0]))
    w.straggle_rate = float(rng.choice([0.0, 0.5, 1.0]))
    w.horizon = 1800.0
    w.work_scale = float(rng.choice([0.2, 0.2, 0.5, 1.0] if twin else [1.0, 1.0, 0.5, 0.2]))  # testbed runs use 0.2
    w.data_scale = w.work_scale
    w.rate_bc /= w.work_scale  # keep utilisation comparable
    if rng.random() < 0.3:
        w.bursts = [(float(rng.uniform(200, 1200)), float(rng.uniform(120, 400)), float(rng.uniform(1.5, 3.0)))]
    return topo, w
