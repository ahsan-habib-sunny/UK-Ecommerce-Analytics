"""Assign source-system IDs, shape the RAW tables, and write Parquet."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PARQUET = dict(index=False, engine="pyarrow", compression="snappy",
               coerce_timestamps="us", allow_truncated_timestamps=True)
TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def _dates(values) -> np.ndarray:
    """datetime64 → Python date objects (NaT → None), so Parquet stores a DATE, not a TIMESTAMP."""
    return np.asarray(values).astype("datetime64[D]").astype(object)


def _month_label(ts) -> pd.Series:
    return pd.Series(np.asarray(ts).astype("datetime64[M]").astype(str)).str.replace("-", "_")


def assemble(rng, cal, customers, events, abandoned_events, orders, lines, returns, products, campaigns, spend, areas):
    """Return (tables, customer_id_by_index, order_id_by_index). Columns starting with '_' are helpers, not written."""
    # Customers: only people who completed at least one purchase exist in the CRM
    live = events.drop(index=abandoned_events)
    first_day = (pd.concat([live[["cust", "day"]], orders[["cust", "day"]]])
                 .groupby("cust")["day"].min())
    idx, fd = first_day.index.to_numpy(), first_day.to_numpy()
    # Registered the evening before the first order, or up to four months earlier
    lag = np.where(rng.random(len(fd)) < 0.4, rng.integers(1, 121, len(fd)) * 86400, 0) + rng.integers(60, 6 * 3600, len(fd))
    registered = cal.dates[fd].astype("datetime64[s]") - lag.astype("timedelta64[s]")
    # Anyone whose first order is inside the data registered inside it too, so "registered before
    # the start date" identifies exactly the customers whose history is cut off (cohort "Pre-2023")
    registered = np.where(fd >= cal.first, np.maximum(registered, np.datetime64(cal.start, "s")), registered)
    order = np.argsort(registered, kind="stable")
    cust_id = np.full(len(customers), -1, dtype=np.int64)
    cust_id[idx[order]] = 100001 + np.arange(len(idx))

    c = customers.iloc[idx[order]]
    customers_raw = pd.DataFrame({
        "customer_id": cust_id[idx[order]], "email": c["email"].to_numpy(dtype=object),
        "first_name": c["first_name"].to_numpy(dtype=object), "last_name": c["last_name"].to_numpy(dtype=object),
        "postcode": c["postcode"].to_numpy(dtype=object), "registered_at": registered[order],
        "date_of_birth": _dates(c["dob"].to_numpy()), "marketing_opt_in": c["opt_in"].to_numpy(),
    })

    # Orders: IDs follow time order, as an OMS would issue them
    ts = orders["ts"].to_numpy()
    order_id = np.empty(len(orders), dtype=np.int64)
    order_id[np.argsort(ts, kind="stable")] = 1_000_001 + np.arange(len(orders))
    orders_raw = pd.DataFrame({
        "order_id": order_id, "customer_id": cust_id[orders["cust"].to_numpy()], "order_ts": ts,
        "sales_channel": orders["sales_channel"].to_numpy(dtype=object), "session_id": None,
        "delivery_postcode": orders["postcode"].to_numpy(dtype=object),
        "promo_code": orders["promo_code"].to_numpy(dtype=object), "shipping_fee": orders["shipping_fee"].to_numpy(),
        "payment_method": orders["payment_method"].to_numpy(dtype=object), "status": orders["status"].to_numpy(dtype=object),
        "_month": _month_label(ts),
    })

    lo = lines["o"].to_numpy()
    line_order = np.lexsort((np.arange(len(lines)), order_id[lo]))
    line_id = np.empty(len(lines), dtype=np.int64)
    line_id[line_order] = 1 + np.arange(len(lines))
    lines_raw = pd.DataFrame({
        "order_line_id": line_id, "order_id": order_id[lo],
        "product_id": products["product_id"].to_numpy()[lines["prod"].to_numpy()],
        "quantity": lines["quantity"].to_numpy(), "unit_price": lines["unit_price"].to_numpy(),
        "discount_amount": lines["discount_amount"].to_numpy(), "unit_cost": lines["unit_cost"].to_numpy(),
        "_month": _month_label(ts[lo]),
    }).iloc[line_order].reset_index(drop=True)

    rl = returns["line"].to_numpy()
    rday = cal.dates[returns["day"].to_numpy()]
    returns_raw = pd.DataFrame({
        "return_id": 0, "order_line_id": line_id[rl], "return_date": _dates(rday),
        "quantity_returned": returns["quantity_returned"].to_numpy(),
        "reason_code": returns["reason_code"].to_numpy(dtype=object), "refund_amount": returns["refund_amount"].to_numpy(),
        "_month": _month_label(rday), "_order_date": _dates(ts[lo[rl]]),
    }).sort_values(["return_date", "order_line_id"], kind="stable").reset_index(drop=True)
    returns_raw["return_id"] = 1 + np.arange(len(returns_raw))

    products_raw = products.drop(columns="popularity")

    campaigns_raw = pd.DataFrame({
        "campaign_id": campaigns["campaign_id"], "campaign_code": campaigns["code"],
        "campaign_name": campaigns["name"], "campaign_type": campaigns["type"],
        "start_date": campaigns["start_date"], "end_date": campaigns["end_date"],
        "discount_pct": campaigns["discount"],
    })

    sdays = cal.dates[spend["day"].to_numpy()]
    spend_raw = pd.DataFrame({
        "spend_date": _dates(sdays), "campaign_code": spend["campaign_code"].to_numpy(dtype=object),
        "channel": spend["channel"].to_numpy(dtype=object), "spend": spend["spend"].to_numpy(),
        "impressions": spend["impressions"].to_numpy(), "clicks": spend["clicks"].to_numpy(),
        "_month": _month_label(sdays),
    }).sort_values(["spend_date", "channel"], kind="stable").reset_index(drop=True)

    tables = {
        "customers": customers_raw, "products": products_raw, "orders": orders_raw,
        "order_lines": lines_raw, "returns": returns_raw, "campaigns": campaigns_raw,
        "marketing_spend": spend_raw, "postcode_areas": areas[["postcode_area", "area_name", "region", "country"]],
    }
    return tables, cust_id, order_id


def sessions_raw(sessions: pd.DataFrame, cust_id: np.ndarray) -> pd.DataFrame:
    cust = sessions["cust"].to_numpy()
    ids = np.where(cust >= 0, cust_id[np.maximum(cust, 0)], -1)
    return pd.DataFrame({
        "session_id": sessions["session_id"].to_numpy(dtype=object),
        "session_start_ts": sessions["start"].to_numpy(),
        "customer_id": pd.Series(ids).where(ids > 0).astype("Int64").to_numpy(),   # NULL = anonymous
        "device": sessions["device"].to_numpy(dtype=object), "channel": sessions["channel"].to_numpy(dtype=object),
        "campaign_code": sessions["campaign_code"].to_numpy(dtype=object),
        "landing_page_type": sessions["landing_page_type"].to_numpy(dtype=object),
        "postcode_area": sessions["postcode_area"].to_numpy(dtype=object),
        "pageviews": sessions["pageviews"].to_numpy(), "added_to_basket": sessions["added_to_basket"].to_numpy(dtype=bool),
        "converted": sessions["converted"].to_numpy(dtype=bool),
    }).sort_values("session_start_ts", kind="stable")


def write_table(df: pd.DataFrame, folder: Path, name: str) -> int:
    """Write one table: a file per month if it has a `_month` helper column, else a single file."""
    folder.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    for col in ("order_ts", "registered_at"):            # source systems send these as text
        if col in df.columns and pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime(TS_FORMAT)
    cols = [c for c in df.columns if not c.startswith("_")]
    if "_month" in df.columns:
        for month, part in df.groupby("_month", sort=True):
            part[cols].to_parquet(folder / f"{name}_{month}.parquet", **PARQUET)
    else:
        df[cols].to_parquet(folder / f"{name}.parquet", **PARQUET)
    return len(df)
