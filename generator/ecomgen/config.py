"""Parameters, the optional sealed scenario, and the simulation calendar."""

from __future__ import annotations

import importlib.util
import tomllib
from datetime import date
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
SEALED_DIR = REPO_ROOT / "sealed"


def load_params(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_scenario() -> tuple[dict, object | None]:
    """Return (scenario, hooks module) from sealed/, or ({}, None) if it isn't there."""
    scenario_path = SEALED_DIR / "scenario.toml"
    hooks_path = SEALED_DIR / "hooks.py"
    scenario = load_params(scenario_path) if scenario_path.exists() else {}
    hooks = None
    if hooks_path.exists():
        spec = importlib.util.spec_from_file_location("sealed_hooks", hooks_path)
        hooks = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hooks)
    return scenario, hooks


class Calendar:
    """Day-indexed calendar. Day 0 is the warm-up start; `first` is the first day written out."""

    def __init__(self, params: dict):
        cal, season = params["calendar"], params["seasonality"]
        self.sim_start: date = cal["warmup_start"]
        self.start: date = cal["start"]
        self.end: date = cal["end"]

        self.dates = np.arange(np.datetime64(self.sim_start), np.datetime64(self.end) + 1)
        self.n = len(self.dates)
        self.first = self.idx(self.start)

        months = self.dates.astype("datetime64[M]")
        self.month_index = months.astype(np.int64)                 # months since 1970-01
        month = self.month_index % 12                               # 0 = January
        weekday = (self.dates.astype(np.int64) + 3) % 7             # 1970-01-01 was a Thursday; 0 = Monday
        dom = (self.dates - months.astype("datetime64[D]")).astype(np.int64) + 1

        s = np.array(season["month"])[month] * np.array(season["weekday"])[weekday]
        s = np.where((month == 11) & (dom == 25), s * 0.3, s)                      # Christmas Day
        s = np.where((month == 11) & ((dom == 24) | (dom == 26)), s * 0.6, s)      # Christmas Eve / Boxing Day
        self.season = s

        years_from_start = (np.arange(self.n) - self.first) / 365.25
        self.growth = (1 + params["acquisition"]["annual_growth"]) ** years_from_start

    def idx(self, d: date) -> int:
        return (d - self.sim_start).days
