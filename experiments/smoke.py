"""Quick check that the installation works (about 30 s, no AWS needed).

  python -m experiments.smoke

Runs 10 simulated minutes with three schedulers (CA-EFT, MERSEM, PACE + shield) and checks
that every package the testbed needs can be imported.
"""
from __future__ import annotations

import importlib
import time


def main():
    print("1/2  checking packages ...")
    for mod in ("numpy", "torch", "matplotlib", "scipy", "aiohttp", "boto3", "cv2"):
        m = importlib.import_module(mod)
        print(f"     ok  {mod:10s} {getattr(m, '__version__', '')}")

    import torch

    from pace.config import Workload, testbed_topology
    from pace.rl.agent import PACE
    from pace.sched.heuristics import CAEFT
    from pace.sched.mersem import MERSEM
    from pace.sim.core import Simulator

    torch.set_num_threads(1)
    print("2/2  simulating 10 minutes of the Coimbatore / Mumbai / Stockholm system ...")
    for sched in (CAEFT(), MERSEM(0.5, gens=5), PACE("models/pace.pt", w=0.9, shield=True)):
        wl = Workload(split="test", horizon=600, start_hour=10, rate_a=0.25, rate_bc=0.015)
        t0 = time.time()
        r = Simulator(testbed_topology(), wl, seed=3).run(sched)
        print(f"     {sched.name:20s} jobs={r['jobs']:4d}  SLA violations={100 * r['sla_AB']:5.1f}%  "
              f"carbon={r['carbon_dyn']:.3f} g  ({time.time() - t0:.1f} s)")
    print("\nSetup OK. Next: AWS access (docs/RUNBOOK.md section 1).")


if __name__ == "__main__":
    main()
