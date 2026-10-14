"""PACE testbed worker: executes real tasks on an edge device, fog or cloud node.

Runs on every EC2 instance and on the laptop (edge). Pure Python + numpy (+ OpenCV
for the vision task if installed). The orchestrator sends a task as soon as it is placed;
the worker fetches its inputs straight away and runs at most `cores` tasks at once, starting
waiting tasks in class-priority order (A alerts > B analytics > C batch), so data transfers
overlap with computation as in the scheduler's model.

Endpoints (all require header X-Token: $PACE_TOKEN):
  POST /run         execute a task (fetch inputs, wait for a core by priority, compute, store output)
  GET  /blob/{key}  download a stored task output (used by downstream tasks)
  POST /gc          drop the stored outputs of finished jobs ({"prefix": run-job-})
  GET  /status      liveness + load
  GET  /calibrate   measure this node's speed for each task type
  POST /echo        upload-bandwidth probe;  GET /bytes/{n} download probe
  GET  /probe?url=  measure fetch time from another worker (inter-region RTT/bandwidth)
  POST /admin/crash?secs=N   emulate a crash: kill running tasks, refuse work for N s

  PACE_TOKEN=secret PACE_NAME=bom-c7i PACE_CORES=2 python testbed/worker.py --port 8000
  Edge emulation on a laptop: PACE_CORES=1 PACE_SLOWDOWN=3 (Raspberry-Pi-class camera box)
"""
from __future__ import annotations

import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import argparse  # noqa: E402
import asyncio  # noqa: E402
import base64  # noqa: E402
import collections  # noqa: E402
import heapq  # noqa: E402
import time  # noqa: E402
from concurrent.futures import ProcessPoolExecutor  # noqa: E402

from aiohttp import ClientSession, ClientTimeout, web  # noqa: E402

TOKEN = os.environ.get("PACE_TOKEN", "pace-demo")
NAME = os.environ.get("PACE_NAME", os.uname().nodename if hasattr(os, "uname") else "worker")
CORES = int(os.environ.get("PACE_CORES", str(os.cpu_count() or 1)))
SLOWDOWN = float(os.environ.get("PACE_SLOWDOWN", "1.0"))
BLOB_MB = float(os.environ.get("PACE_BLOB_MB", "500"))  # task outputs kept in memory for downstream tasks
ITERS_PER_UNIT = int(os.environ.get("PACE_ITERS", "3500"))  # ~1 s per work unit on a c7i-class vCPU
MAT = 160

_A = None


def _mat():
    global _A
    if _A is None:
        import numpy as np
        rng = np.random.default_rng(0)
        _A = rng.standard_normal((MAT, MAT)) / MAT ** 0.5
    return _A


def _generic(work: float) -> float:
    import numpy as np
    a = _mat()
    x = np.eye(MAT)
    n = max(1, int(round(work * ITERS_PER_UNIT * SLOWDOWN)))
    t0 = time.perf_counter()
    for _ in range(n):
        x = a @ x
        x /= np.abs(x).max() + 1e-9
    return time.perf_counter() - t0


_HOG = None


def _vision(frame: bytes | None, work: float) -> tuple[float, int]:
    """HOG pedestrian detection on a JPEG frame (real camera workload)."""
    global _HOG
    try:
        import cv2
        import numpy as np
        if _HOG is None:  # one-off start-up of this worker process, not part of the task's time
            cv2.setNumThreads(1)  # one task per core: OpenCV would otherwise use every core of the host
            _HOG = cv2.HOGDescriptor()
            _HOG.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        t0 = time.perf_counter()
        if frame:
            img = cv2.imdecode(np.frombuffer(frame, np.uint8), cv2.IMREAD_GRAYSCALE)
        else:
            img = (np.random.default_rng(1).random((240, 320)) * 255).astype(np.uint8)
        boxes = 0
        for _ in range(max(1, int(round(SLOWDOWN)))):
            rects, _w = _HOG.detectMultiScale(img, winStride=(8, 8), padding=(8, 8), scale=1.05)
            boxes = len(rects)
        return time.perf_counter() - t0, boxes
    except (ImportError, AttributeError):  # no OpenCV, or OpenCV 5 (HOG removed): CPU kernel instead
        return _generic(work), 0


def execute(typ: str, work: float, frame: bytes | None) -> tuple[float, int]:
    if typ == "vision" and work >= 0.1:
        return _vision(frame, work)
    return _generic(work), 0


class PrioGate:
    """At most `n` tasks compute at once; waiting tasks start by (priority, arrival)."""

    def __init__(self, n: int):
        self.free = n
        self.waiting: list = []
        self.seq = 0

    async def acquire(self, prio: int) -> None:
        if self.free > 0 and not self.waiting:
            self.free -= 1
            return
        fut = asyncio.get_running_loop().create_future()
        self.seq += 1
        heapq.heappush(self.waiting, (prio, self.seq, fut))
        try:
            await fut
        except asyncio.CancelledError:
            if fut.done() and not fut.cancelled():  # the core was handed over just before cancelling
                self.release()
            raise

    def release(self) -> None:
        while self.waiting:
            _p, _s, fut = heapq.heappop(self.waiting)
            if not fut.done():
                fut.set_result(None)  # hand the core straight to the next task
                return
        self.free += 1


class Worker:
    def __init__(self):
        self.pool = ProcessPoolExecutor(CORES)
        self.gate = PrioGate(CORES)
        self.blobs: collections.OrderedDict[str, bytes] = collections.OrderedDict()
        self.blob_bytes = 0
        self.inflight = 0
        self.down_until = 0.0
        self.started = time.time()
        self.session: ClientSession | None = None
        self.done = 0

    async def http(self) -> ClientSession:
        if self.session is None:
            self.session = ClientSession(timeout=ClientTimeout(total=60), headers={"X-Token": TOKEN})
        return self.session

    def store(self, key: str, data: bytes) -> None:
        old = self.blobs.pop(key, None)
        self.blob_bytes += len(data) - (len(old) if old is not None else 0)
        self.blobs[key] = data
        while self.blob_bytes > BLOB_MB * 1e6 and len(self.blobs) > 1:  # oldest first; /gc frees finished jobs
            _k, v = self.blobs.popitem(last=False)
            self.blob_bytes -= len(v)

    async def gc(self, req: web.Request) -> web.Response:
        prefix = (await req.json()).get("prefix", "")
        keys = [k for k in self.blobs if prefix and k.startswith(prefix)]
        for k in keys:
            self.blob_bytes -= len(self.blobs.pop(k))
        return web.json_response({"freed": len(keys)})

    async def run(self, req: web.Request) -> web.Response:
        if time.time() < self.down_until:
            return web.json_response({"error": "down"}, status=503)
        body = await req.json()
        self.inflight += 1
        try:
            t0 = time.perf_counter()
            frame = base64.b64decode(body["frame"]) if body.get("frame") else None
            inline_bytes = sum(len(base64.b64decode(x)) for x in body.get("inline", []))
            s = await self.http()
            fetched = 0

            async def fetch(url):
                async with s.get(url) as r:
                    r.raise_for_status()
                    return await r.read()

            try:
                datas = await asyncio.gather(*[fetch(u) for u in body.get("inputs", [])])
            except Exception as e:  # noqa: BLE001 - an input is missing or its node unreachable: not this node's fault
                return web.json_response({"error": f"input: {e}"[:200]}, status=424)
            fetched = sum(len(d) for d in datas)
            for d in datas:
                if body.get("typ") == "vision" and d[:2] == b"\xff\xd8":
                    frame = d
            t_fetch = time.perf_counter() - t0
            await self.gate.acquire(int(body.get("prio", 1)))
            t_queue = time.perf_counter() - t0 - t_fetch
            try:
                if time.time() < self.down_until:
                    return web.json_response({"error": "down"}, status=503)
                loop = asyncio.get_running_loop()
                t_exec, boxes = await loop.run_in_executor(self.pool, execute, body.get("typ", "generic"),
                                                           float(body.get("work", 0.0)), frame)
            finally:
                self.gate.release()
            if time.time() < self.down_until:
                return web.json_response({"error": "crashed"}, status=503)
            out = frame if (body.get("typ") == "vision" and frame and body.get("pass_frame")) else \
                os.urandom(int(float(body.get("out_mb", 0.0)) * 1e6))
            self.store(body["key"], out)
            self.done += 1
            return web.json_response({"node": NAME, "t_fetch": t_fetch, "t_queue": t_queue, "t_exec": t_exec,
                                      "boxes": boxes, "in_bytes": fetched + inline_bytes, "out_bytes": len(out)})
        finally:
            self.inflight -= 1

    async def blob(self, req: web.Request) -> web.Response:
        data = self.blobs.get(req.match_info["key"])
        if data is None:
            return web.json_response({"error": "missing"}, status=404)
        return web.Response(body=data, content_type="application/octet-stream")

    async def status(self, req: web.Request) -> web.Response:
        down = time.time() < self.down_until
        try:
            load1 = os.getloadavg()[0]
        except (AttributeError, OSError):
            load1 = -1.0
        return web.json_response({"name": NAME, "cores": CORES, "inflight": self.inflight,
                                  "waiting": len(self.gate.waiting), "done": self.done,
                                  "load1": load1, "up_s": time.time() - self.started, "down": down,
                                  "slowdown": SLOWDOWN}, status=503 if down else 200)

    async def calibrate(self, req: web.Request) -> web.Response:
        loop = asyncio.get_running_loop()
        reps = int(req.query.get("reps", "3"))
        g = sorted([(await loop.run_in_executor(self.pool, execute, "generic", 1.0, None))[0] for _ in range(reps)])
        v = sorted([(await loop.run_in_executor(self.pool, execute, "vision", 1.0, None))[0] for _ in range(reps)])
        return web.json_response({"name": NAME, "generic_s_per_unit": g[len(g) // 2], "vision_s": v[len(v) // 2],
                                  "cores": CORES})

    async def echo(self, req: web.Request) -> web.Response:
        data = await req.read()
        return web.json_response({"bytes": len(data)})

    async def bytes_(self, req: web.Request) -> web.Response:
        return web.Response(body=os.urandom(int(req.match_info["n"])))

    async def probe(self, req: web.Request) -> web.Response:
        url = req.query["url"]
        s = await self.http()
        out = {}
        for n in (1000, 2_000_000):
            t0 = time.perf_counter()
            async with s.get(f"{url}/bytes/{n}") as r:
                await r.read()
            out[str(n)] = time.perf_counter() - t0
        return web.json_response(out)

    async def crash(self, req: web.Request) -> web.Response:
        secs = float(req.query.get("secs", "60"))
        self.down_until = time.time() + secs
        old, self.pool = self.pool, ProcessPoolExecutor(CORES)  # fresh workers for after the outage
        procs = list((getattr(old, "_processes", None) or {}).values())  # read before shutdown clears it
        old.shutdown(wait=False, cancel_futures=True)
        for p in procs:  # kill the running tasks
            p.terminate()
        return web.json_response({"down_for": secs})


@web.middleware
async def auth(request, handler):
    if request.headers.get("X-Token") != TOKEN:
        return web.json_response({"error": "unauthorized"}, status=401)
    return await handler(request)


def make_app() -> web.Application:
    w = Worker()
    app = web.Application(middlewares=[auth], client_max_size=64 * 1024 ** 2)
    app.add_routes([web.post("/run", w.run), web.get("/blob/{key}", w.blob), web.get("/status", w.status),
                    web.get("/calibrate", w.calibrate), web.post("/echo", w.echo), web.get("/bytes/{n}", w.bytes_),
                    web.get("/probe", w.probe), web.post("/admin/crash", w.crash), web.post("/gc", w.gc)])
    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PACE_PORT", "8000")))
    a = ap.parse_args()
    web.run_app(make_app(), port=a.port, access_log=None)
