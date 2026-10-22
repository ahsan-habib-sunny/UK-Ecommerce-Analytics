"""Returns: which order lines come back, when, why, and for how much."""

from __future__ import annotations

import numpy as np
import pandas as pd


def build_returns(rng, params, scenario, cal, orders, lines, products):
    rc = params["returns"]
    cats = {c["name"]: c for c in params["category"]}

    o = lines["o"].to_numpy()
    eligible = (orders["status"].to_numpy()[o] == "Completed") & ~orders["is_test"].to_numpy()[o]
    prod = lines["prod"].to_numpy()
    category = products["category"].to_numpy(dtype=object)[prod]
    sku = products["sku"].to_numpy(dtype=object)[prod]
    order_day = orders["day"].to_numpy()[o]

    rate = pd.Series(category).map({k: v["return_rate"] for k, v in cats.items()}).to_numpy(dtype=float)
    for ov in scenario.get("return_override", []):
        rate = np.where((sku == ov["sku"]) & (order_day >= cal.idx(ov["start"])), ov["return_rate"], rate)

    idx = np.flatnonzero(eligible & (rng.random(len(o)) < rate))
    qty = lines["quantity"].to_numpy()[idx]
    partial = (qty > 1) & (rng.random(len(idx)) < rc["partial_share"])
    q_ret = np.where(partial, rng.integers(1, np.maximum(qty, 2)), qty)

    # Reason: drawn from the category's usual mix, unless an override says otherwise
    reason = np.empty(len(idx), dtype=object)
    for name, c in cats.items():
        m = category[idx] == name
        reason[m] = rng.choice(list(c["reasons"]), m.sum(), p=np.array(list(c["reasons"].values())) / sum(c["reasons"].values()))
    for ov in scenario.get("return_override", []):
        m = (sku[idx] == ov["sku"]) & (order_day[idx] >= cal.idx(ov["start"])) & (rng.random(len(idx)) < ov["reason_share"])
        reason[m] = ov["reason"]

    # Timing: dispatch + delivery + customer delay, inside the return window
    lo_d, hi_d = rc["dispatch_days"]
    lag = rng.integers(lo_d, hi_d + 1, len(idx)) + 1 + np.minimum(rng.gamma(2.0, 4.0, len(idx)), 25).astype(int)
    return_day = order_day[idx] + np.minimum(lag, rc["window_days"])

    unit_price = lines["unit_price"].to_numpy()[idx]
    disc = lines["discount_amount"].to_numpy()[idx]
    returns = pd.DataFrame({
        "line": idx, "day": return_day, "quantity_returned": q_ret, "reason_code": reason,
        "refund_amount": np.round(q_ret * (unit_price - disc / qty), 2),
    })
    return returns[returns["day"] <= cal.n - 1].reset_index(drop=True)   # not yet back by the data end date
