"""Sanity-check generated RAW Parquet files: row counts, unique keys, joins, and a few headline rates.

Run from the repo root:
    python generator/validate.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from ecomgen.config import REPO_ROOT


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=REPO_ROOT / "data" / "raw")
    args = ap.parse_args()

    def load(name, columns=None):
        return pd.read_parquet(args.data / name, columns=columns)

    print("Row counts")
    total = 0
    for folder in sorted(p for p in args.data.iterdir() if p.is_dir()):
        n = sum(pq.ParquetFile(f).metadata.num_rows for f in folder.glob("*.parquet"))
        files = len(list(folder.glob("*.parquet")))
        total += n
        print(f"  {folder.name:<16}{n:>12,}   ({files} file{'s' if files > 1 else ''})")
    print(f"  {'TOTAL':<16}{total:>12,}\n")

    customers = load("customers")
    orders = load("orders")
    lines = load("order_lines", ["order_id"])
    returns = load("returns")
    sessions = load("sessions", ["session_id", "session_start_ts", "converted", "customer_id"])
    line_ids = load("order_lines", ["order_line_id"])["order_line_id"]

    checks = [
        ("customers.customer_id is unique", customers["customer_id"].is_unique),
        ("orders.order_id is unique", orders["order_id"].is_unique),
        ("returns.return_id is unique", returns["return_id"].is_unique),
        ("sessions.session_id is unique", sessions["session_id"].is_unique),
        ("every order has a known customer", orders["customer_id"].isin(customers["customer_id"]).all()),
        ("every order line has an order", lines["order_id"].isin(orders["order_id"]).all()),
        ("every order has at least one line", orders["order_id"].isin(lines["order_id"]).all()),
        ("every return points at an order line", returns["order_line_id"].isin(line_ids).all()),
        ("every web/app order points at a session",
         orders.loc[orders["sales_channel"] != "marketplace", "session_id"].isin(sessions["session_id"]).all()),
        ("marketplace orders have no session", orders.loc[orders["sales_channel"] == "marketplace", "session_id"].isna().all()),
    ]
    print("Checks")
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")

    web_orders = (orders["sales_channel"] != "marketplace").sum()
    print("\nHeadline rates")
    print(f"  sessions from {sessions['session_start_ts'].min():%Y-%m-%d} to {sessions['session_start_ts'].max():%Y-%m-%d}")
    print(f"  conversion rate (converted sessions / sessions): {sessions['converted'].mean():.2%}")
    print(f"  converted sessions vs web/app orders:            {sessions['converted'].sum():,} vs {web_orders:,}")
    print(f"  logged-in share of sessions:                     {sessions['customer_id'].notna().mean():.1%}")
    print(f"  order lines per order:                           {len(lines) / len(orders):.2f}")
    print(f"  orders per customer:                             {len(orders) / len(customers):.2f}")
    print(f"  returned lines / order lines:                    {len(returns) / len(lines):.1%}")


if __name__ == "__main__":
    main()
