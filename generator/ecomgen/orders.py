"""Turn purchase events into orders and order lines: channel, basket, prices, delivery, checkout."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .reference import channel_in_campaign, random_postcodes, weights


def active_matrix(products: pd.DataFrame, months: np.ndarray) -> np.ndarray:
    """Bool matrix [month, product]: was the product on sale at some point in that month?"""
    launch = pd.to_datetime(products["launched_on"]).to_numpy("datetime64[D]")
    disc = (pd.to_datetime(products["discontinued_on"]).fillna(pd.Timestamp("2100-01-01"))
            .to_numpy("datetime64[D]"))
    base = np.datetime64("1970-01", "M")
    m_start = (base + months).astype("datetime64[D]")
    m_end = (base + months + 1).astype("datetime64[D]") - np.timedelta64(1, "D")
    return (launch[None, :] <= m_end[:, None]) & (disc[None, :] > m_start[:, None])


def _line_discount(camp: np.ndarray, category: np.ndarray, campaigns: pd.DataFrame) -> np.ndarray:
    pct = np.zeros(len(camp))
    for i in np.unique(camp[camp >= 0]):
        m = camp == i
        cats = campaigns["categories"].iat[i]
        if cats:
            m &= np.isin(category, cats)
        pct[m] = campaigns["discount"].iat[i]
    return pct


def build_orders(rng, params, scenario, cal, cust, events, campaigns, day_camp, products, areas):
    """Return (orders, lines, abandoned, demand, abandoned_event_ids)."""
    oc = params["orders"]
    ev = events[events["day"] >= cal.first]          # warm-up events shape the customer base but aren't written
    ev_id = ev.index.to_numpy()
    c = ev["cust"].to_numpy()
    d = ev["day"].to_numpy()
    first = ev["seq"].to_numpy() == 0
    n = len(ev)

    # --- When -----------------------------------------------------------------------
    hour = rng.choice(24, n, p=weights(params["seasonality"]["hour"]))
    secs = hour * 3600 + rng.integers(0, 3600, n)
    ts = cal.dates[d].astype("datetime64[s]") + secs.astype("timedelta64[s]")

    # --- Where they bought, on what device, via which marketing channel --------------
    sc = params["sales_channel"]
    sales = np.where(rng.random(n) < sc["loyalty"], cust["sales_pref"].to_numpy()[c],
                     rng.choice(np.array(sc["names"], dtype=object), n, p=weights(sc["share"])))
    mkt = sales == "marketplace"

    dv = params["devices"]
    loyal = rng.random(n) < dv["loyalty"]
    web_dev = np.where(loyal, cust["web_dev"].to_numpy()[c],
                       rng.choice(np.array(dv["web"], dtype=object), n, p=weights(dv["web_share"])))
    app_dev = np.where(loyal, cust["app_dev"].to_numpy()[c],
                       rng.choice(np.array(dv["app"], dtype=object), n, p=weights(dv["app_share"])))
    device = np.where(sales == "web", web_dev, np.where(sales == "app", app_dev, None))

    ch = params["channel"]
    ch_names = np.array([x["name"] for x in ch], dtype=object)
    channel = np.where(first, cust["acq_channel"].to_numpy()[c],
                       rng.choice(ch_names, n, p=weights([x["repeat"] for x in ch])))
    channel = np.where(mkt, "Marketplace", channel)

    # --- Campaigns: who uses a promo code -------------------------------------------
    camp = np.where(mkt, -1, day_camp[d])
    has = camp >= 0
    ci = np.maximum(camp, 0)
    in_ch = channel_in_campaign(camp, channel, campaigns)
    uptake = np.where(has, campaigns["uptake"].to_numpy()[ci], 0.0)
    acquired_by_it = first & has & (cust["acq_campaign"].to_numpy()[c] == camp)
    use_promo = has & (campaigns["discount"].to_numpy()[ci] > 0) & (
        acquired_by_it | (rng.random(n) < np.where(in_ch, uptake, uptake * oc["offsite_promo_uptake"])))
    codes = campaigns["code"].to_numpy(dtype=object)
    promo = np.where(use_promo, codes[ci], None)
    session_campaign = np.where(has & in_ch, codes[ci], None)
    camp_used = np.where(use_promo, camp, -1)

    # --- Delivery address ---------------------------------------------------------------
    same = rng.random(n) < oc["same_delivery_address"]
    other_area = rng.choice(areas["postcode_area"].to_numpy(dtype=object), n, p=areas["weight"].to_numpy())
    area = np.where(same, cust["area"].to_numpy()[c], other_area)
    postcode = np.where(same, cust["postcode"].to_numpy()[c], random_postcodes(rng, other_area))

    # --- Basket: number of lines, which products, quantities ----------------------------
    tier = cust["tier"].to_numpy()[c]
    n_lines = np.minimum(1 + rng.poisson(np.array(params["tiers"]["mean_lines"])[tier] - 1), oc["max_lines"])
    lo = np.repeat(np.arange(n), n_lines)                 # line → order

    month = cal.month_index[d]
    months = np.unique(month)
    act = active_matrix(products, months)
    mpos = np.searchsorted(months, month)                 # order → row of `act`
    pop = products["popularity"].to_numpy()
    prod = np.empty(len(lo), dtype=np.int64)
    line_mpos = mpos[lo]
    for k in range(len(months)):
        sel = np.flatnonzero(line_mpos == k)
        if len(sel):
            p = pop * act[k]
            prod[sel] = rng.choice(len(pop), len(sel), p=p / p.sum())
    qty = rng.choice(oc["quantity"], len(lo), p=weights(oc["quantity_share"]))

    # --- Prices: today's list price deflated back to the order date ---------------------
    price_factor = (1 + oc["annual_price_inflation"]) ** (-(cal.n - 1 - d) / 365.25)
    list_price = products["list_price"].to_numpy()
    cost_now = products["unit_cost"].to_numpy()
    category = products["category"].to_numpy(dtype=object)
    unit_price = np.round(list_price[prod] * price_factor[lo], 2)
    unit_cost = np.round(cost_now[prod] * price_factor[lo], 2)
    discount = np.round(qty * unit_price * _line_discount(camp_used[lo], category[prod], campaigns), 2)

    # --- Delivery charge, and customers topping up to reach free delivery ----------------
    policies = sorted(params["shipping_policy"] + scenario.get("shipping_policy", []), key=lambda p: p["start"])
    pol = np.searchsorted(np.array([cal.idx(p["start"]) for p in policies]), d, side="right") - 1
    thr = np.array([p["threshold"] for p in policies])[pol]
    fee = np.array([p["fee"] for p in policies])[pol]
    pad_window = np.array([p["pad_window"] for p in policies])[pol]
    pad_prob = np.array([p["pad_prob"] for p in policies])[pol]

    basket = np.bincount(lo, qty * unit_price - discount, minlength=n)
    pad = ~mkt & (basket >= thr - pad_window) & (basket < thr) & (rng.random(n) < pad_prob)
    pad_ok = np.isin(category, oc["pad_categories"])
    extra_o, extra_p = [], []
    for o in np.flatnonzero(pad):
        need = thr[o] - basket[o] + 0.01
        price_o = list_price * price_factor[o]
        ok = pad_ok & act[mpos[o]] & (price_o >= need) & (price_o <= need + 15)
        if ok.any():
            p = pop * ok
            extra_o.append(o)
            extra_p.append(rng.choice(len(pop), p=p / p.sum()))
    if extra_o:
        eo, ep = np.array(extra_o), np.array(extra_p)
        lo = np.concatenate([lo, eo])
        prod = np.concatenate([prod, ep])
        qty = np.concatenate([qty, np.ones(len(eo), dtype=qty.dtype)])
        unit_price = np.concatenate([unit_price, np.round(list_price[ep] * price_factor[eo], 2)])
        unit_cost = np.concatenate([unit_cost, np.round(cost_now[ep] * price_factor[eo], 2)])
        discount = np.concatenate([discount, np.zeros(len(eo))])
        order = np.argsort(lo, kind="stable")             # keep each order's lines together
        lo, prod, qty, unit_price, unit_cost, discount = (a[order] for a in (lo, prod, qty, unit_price, unit_cost, discount))
        basket = np.bincount(lo, qty * unit_price - discount, minlength=n)

    shipping = np.where(mkt, 0.0, np.where(basket < thr, fee, 0.0))
    for s in scenario.get("shipping_surcharge", []):
        shipping = shipping + np.where(~mkt & (area == s["postcode_area"]) & (d >= cal.idx(s["start"])), s["amount"], 0.0)

    # --- Checkout: some baskets are abandoned at checkout --------------------------------
    abandon = np.zeros(n, dtype=bool)
    median_basket = np.median(basket[~mkt]) if (~mkt).any() else 0.0
    for s in scenario.get("conversion_shock", []):
        m = ~mkt & (d >= cal.idx(s["start"]))
        if "end" in s:
            m &= d <= cal.idx(s["end"])
        if "device" in s:
            m &= device == s["device"]
        if "postcode_area" in s:
            m &= area == s["postcode_area"]
        p = np.full(n, s["abandon_prob"])
        if s.get("small_basket_bias"):
            p = np.where(basket < median_basket, np.minimum(p * 1.4, 1.0), p * 0.6)
        abandon |= m & (rng.random(n) < p)

    # --- Payment and status ---------------------------------------------------------------
    pm = params["payment"]
    methods = np.array(pm["methods"], dtype=object)
    payment = np.where(device == "ios_app", rng.choice(methods, n, p=weights(pm["ios_share"])),
                       rng.choice(methods, n, p=weights(pm["share"])))
    payment = np.where(mkt, "marketplace", payment)
    status = np.where(rng.random(n) < oc["cancel_rate"], "Cancelled", "Completed")

    # Everything that reached checkout on web/app drives traffic volume, even if abandoned
    demand = pd.DataFrame({"day": d[~mkt], "device": device[~mkt]})
    abandoned = pd.DataFrame({"cust": c[abandon], "ts": ts[abandon], "device": device[abandon],
                              "channel": channel[abandon], "campaign_code": session_campaign[abandon]})

    keep = ~abandon
    new_o = np.cumsum(keep) - 1
    orders = pd.DataFrame({
        "o": np.arange(keep.sum()), "cust": c[keep], "day": d[keep], "ts": ts[keep],
        "sales_channel": sales[keep], "device": device[keep], "channel": channel[keep],
        "campaign_code": session_campaign[keep], "promo_code": promo[keep],
        "area": area[keep], "postcode": postcode[keep], "shipping_fee": np.round(shipping[keep], 2),
        "payment_method": payment[keep], "status": status[keep], "is_test": np.zeros(keep.sum(), dtype=bool),
    })
    lk = keep[lo]
    lines = pd.DataFrame({"o": new_o[lo[lk]], "prod": prod[lk], "quantity": qty[lk],
                          "unit_price": unit_price[lk], "discount_amount": discount[lk], "unit_cost": unit_cost[lk]})
    return orders, lines, abandoned, demand, ev_id[abandon]
