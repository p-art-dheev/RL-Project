"""Grid carbon-intensity traces (gCO2eq/kWh, location-based).

Two sources:
  * "synthetic" (default): hourly profiles built from approximate public annual means
    with a daily shape (solar dip at midday, evening peak) and AR(1) noise.
    Every result produced with this source must be labelled SYNTHETIC CARBON.
  * a directory of Electricity Maps Data Portal hourly CSVs, one file per zone,
    named <ZONE>*.csv (e.g. IN-WE_2024_hourly.csv); "dir@2024" selects a year
    (train on one year, test on another). The column whose name contains
    "Carbon Intensity" and "(LCA)" (or "direct" as a fallback) is used.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

# Approximate annual means (gCO2eq/kWh). Sources to cite: Electricity Maps zone pages;
# CEA CO2 baseline database (India ~0.7 t/MWh). Replace with real CSVs when available.
SYNTH = {
    "IN-SO": dict(mean=560.0, solar=0.20, evening=0.06, noise=0.03),
    "IN-WE": dict(mean=680.0, solar=0.12, evening=0.05, noise=0.03),
    "SE-SE3": dict(mean=35.0, solar=0.10, evening=0.15, noise=0.12),
}


class CarbonTrace:
    """Hourly carbon intensity per zone, indexed by local hour since t=0."""

    def __init__(self, zones, source: str = "synthetic", hours: int = 24 * 14, seed: int = 0):
        self.source = source
        self.series: dict[str, np.ndarray] = {}
        rng = np.random.default_rng(seed)
        if source != "synthetic":
            directory, _, year = source.partition("@")  # e.g. "data/carbon@2024" picks the 2024 files
            for z in zones:
                files = sorted(f for f in Path(directory).glob(f"{z}*.csv") if year in f.name)
                if not files:
                    raise FileNotFoundError(f"no CSV for zone {z} in {source}")
                self.series[z] = _read_em_csv(files[0])
        else:
            for z in zones:
                p = SYNTH[z]
                h = np.arange(hours)
                hod = h % 24
                solar = np.clip(np.sin((hod - 6) / 12 * math.pi), 0, None)
                evening = np.exp(-0.5 * ((hod - 20) / 2.0) ** 2)
                noise = np.zeros(hours)
                for i in range(1, hours):
                    noise[i] = 0.8 * noise[i - 1] + rng.normal(0, p["noise"])
                day = rng.normal(0, p["noise"] * 2, hours // 24 + 1).repeat(24)[:hours]  # weather days
                self.series[z] = p["mean"] * (1 - p["solar"] * solar + p["evening"] * evening) * (1 + noise + day)
        self.offset = 0

    def set_start(self, hour_index: int) -> None:
        self.offset = hour_index

    def at(self, zone: str, t: float) -> float:
        s = self.series[zone]
        return float(s[(self.offset + int(t // 3600)) % len(s)])

    def forecast(self, zone: str, t: float, ahead_h: float, rng=None, err: float = 0.05) -> float:
        v = self.at(zone, t + ahead_h * 3600)
        if rng is not None and err > 0:
            v *= 1 + rng.normal(0, err * max(ahead_h, 0.5))
        return v

    def mean(self, zone: str) -> float:
        return float(np.mean(self.series[zone]))


def _read_em_csv(path: Path) -> np.ndarray:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    cols = [c for c in rows[0] if "Carbon Intensity" in c or "carbon_intensity" in c.lower()]
    col = next((c for c in cols if "LCA" in c or "lifecycle" in c.lower()), None) or next(
        (c for c in cols if "direct" in c.lower()), cols[0])
    return np.array([float(r[col]) for r in rows if r[col] not in ("", None)], dtype=float)
