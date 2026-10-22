"""Generate the synthetic UK e-commerce RAW dataset as Parquet files.

Run from the repo root:
    python generator/generate.py --scale 0.0125   # ~100k rows: quick test (Day 3)
    python generator/generate.py                  # full ~8M rows (Day 4)

Same seed + same scale = identical data, every time.
"""

from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from ecomgen import config, customers, marketing, orders, output, reference, returns, sessions

HERE = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scale", type=float, help="volume multiplier (default from params.toml)")
    ap.add_argument("--seed", type=int, help="random seed (default from params.toml)")
    ap.add_argument("--out", type=Path, default=config.REPO_ROOT / "data" / "raw", help="output folder")
    args = ap.parse_args()

    params = config.load_params(HERE / "params.toml")
    if args.scale is not None:
        params["scale"] = args.scale
    if args.seed is not None:
        params["seed"] = args.seed
    scenario, hooks = config.load_scenario()

    print(f"seed={params['seed']}  scale={params['scale']}  out={args.out}")
    print("sealed scenario: " + ("loaded" if scenario else "not found, generating the baseline business only"))
    t0 = time.perf_counter()

    def step(msg: str) -> None:
        print(f"  [{time.perf_counter() - t0:6.1f}s] {msg}")

    rng = np.random.default_rng(params["seed"])
    cal = config.Calendar(params)
    areas = reference.load_postcode_areas(HERE / "seeds" / "postcode_areas.csv")
    products = reference.build_products(rng, params, scenario, cal)
    campaigns = reference.build_campaigns(params, scenario, cal)
    day_camp = reference.daily_campaign(cal, campaigns)
    step(f"reference data: {len(products):,} products, {len(campaigns)} campaigns")

    cust, events = customers.simulate_customers(rng, params, scenario, cal, campaigns, day_camp, areas)
    step(f"simulated {len(cust):,} customers, {len(events):,} purchase events (incl. warm-up)")

    ords, lines, abandoned, demand, abandoned_ev = orders.build_orders(
        rng, params, scenario, cal, cust, events, campaigns, day_camp, products, areas)
    step(f"orders: {len(ords):,} orders, {len(lines):,} lines")

    ctx = SimpleNamespace(rng=rng, params=params, scenario=scenario, cal=cal, areas=areas,
                          products=products, customers=cust, orders=ords, lines=lines)
    if hooks and hasattr(hooks, "before_sessions"):
        hooks.before_sessions(rng, ctx)
        cust, ords, lines = ctx.customers, ctx.orders, ctx.lines

    rets = returns.build_returns(rng, params, scenario, cal, ords, lines, products)
    step(f"returns: {len(rets):,}")

    known = sessions.build_known_sessions(rng, params, cal, cust, ords, abandoned, campaigns, day_camp, areas)
    lam = sessions.anonymous_rates(params, cal, demand, known)
    spend = marketing.build_spend(rng, params, cal, campaigns, ords, lines, products)
    step(f"known sessions: {len(known):,}; marketing spend rows: {len(spend):,}")

    tables, cust_id, _ = output.assemble(rng, cal, cust, events, abandoned_ev, ords, lines, rets,
                                         products, campaigns, spend, areas)
    # The order references the session it was placed in
    conv = known[known["o"] >= 0]
    sid = np.full(len(ords), None, dtype=object)
    sid[conv["o"].to_numpy()] = conv["session_id"].to_numpy()
    tables["orders"]["session_id"] = sid
    tables["orders"] = tables["orders"].sort_values("order_id").reset_index(drop=True)

    if hooks and hasattr(hooks, "before_write"):
        tables = hooks.before_write(rng, tables, ctx)

    # Write: start from an empty folder so old files never mix with new ones
    if args.out.exists():
        shutil.rmtree(args.out)
    counts = {name: output.write_table(df, args.out / name, name) for name, df in tables.items()}

    known["_month"] = output._month_label(known["start"].to_numpy())
    n_sessions = 0
    for month in np.unique(cal.month_index[cal.first:]):
        label = str(np.datetime64("1970-01", "M") + month).replace("-", "_")
        part = known[known["_month"] == label].drop(columns="_month")
        anon = sessions.anonymous_month(rng, params, cal, lam, month, campaigns, day_camp, areas)
        df = output.sessions_raw(pd.concat([part, anon], ignore_index=True), cust_id)
        df["_month"] = label
        n_sessions += output.write_table(df, args.out / "sessions", "sessions")
    counts["sessions"] = n_sessions
    step("written")

    print("\nRows written:")
    for name, n in counts.items():
        print(f"  {name:<16}{n:>12,}")
    print(f"  {'TOTAL':<16}{sum(counts.values()):>12,}")


if __name__ == "__main__":
    main()
