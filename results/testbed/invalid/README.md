# Runs excluded from the results (kept for transparency)

These runs were hit by an orchestrator bug, not by the schedulers' decisions:

- The HTTP client allowed at most 100 open connections, and every queued task holds one. Under heavy load
  (EFT moving 72 % of the work to the 1-core edge workers; the busy hour), new requests and the heartbeat
  waited for a free connection. The online network estimator counted that wait as network delay
  (corrections up to 25–50 s), and timed-out requests marked healthy nodes as down.
- Every task error marked its node down, so one reset connection or one evicted input (workers kept only
  400 outputs) re-ran all of that node's tasks, which caused more evictions and more false failures.

Signature: `node-down` / `task-failed` events and unfinished jobs in runs where no crash was injected.
The adaptive nominal runs of PACE, PACE+shield, MERSEM and CA-EFT have no such events and are valid.

Fixed in commit "Testbed robustness": unlimited connections, a failed task is retried instead of taking
its node down (only the heartbeat or a worker's "503 down" does), outputs kept by size with clean-up of
finished jobs, correction capped at 3 s, and the worker's crash emulation no longer breaks its process pool.
