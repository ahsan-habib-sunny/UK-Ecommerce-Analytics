"""Daily marketing spend: always-on budgets, campaign budgets and affiliate commission."""

from __future__ import annotations

import numpy as np
import pandas as pd


def build_spend(rng, params, cal, campaigns, orders, lines, products) -> pd.DataFrame:
    mk = params["marketing"]
    scale = params["scale"]
    days = np.arange(cal.first, cal.n)
    parts = []

    # Always-on budgets follow business growth and seasonality
    for channel, daily in mk["always_on"].items():
        spend = daily * scale * cal.growth[days] * cal.season[days] * rng.normal(1, 0.1, len(days))
        parts.append(pd.DataFrame({"day": days, "campaign_code": None, "channel": channel, "spend": spend}))

    # Campaign budgets, split across the campaign's channels
    email_share = mk["campaign_email_share"]
    for c in campaigns.itertuples():
        cdays = np.arange(cal.idx(c.start_date), cal.idx(c.end_date) + 1)
        paid = [ch for ch in c.channels if ch != "Email"]
        split = {ch: (1 - email_share) / len(paid) for ch in paid} if paid else {}
        if "Email" in c.channels:
            split["Email"] = email_share if paid else 1.0
        for ch, share in split.items():
            spend = c.spend_per_day * share * scale * rng.normal(1, 0.1, len(cdays))
            parts.append(pd.DataFrame({"day": cdays, "campaign_code": c.code, "channel": ch, "spend": spend}))

    # Affiliates are paid commission on the net revenue they drive
    o = lines["o"].to_numpy()
    vat = products["vat_rate"].to_numpy()[lines["prod"].to_numpy()]
    net = (lines["quantity"] * lines["unit_price"] - lines["discount_amount"]).to_numpy() / (1 + vat)
    order_net = np.bincount(o, net, minlength=len(orders))
    aff = ((orders["channel"] == "Affiliate") & (orders["status"] == "Completed") & ~orders["is_test"]).to_numpy()
    day_rev = np.bincount(orders["day"].to_numpy()[aff], order_net[aff], minlength=cal.n)[days]
    parts.append(pd.DataFrame({"day": days, "campaign_code": None, "channel": "Affiliate",
                               "spend": day_rev * mk["affiliate_commission"]}))

    spend = pd.concat(parts, ignore_index=True)
    spend = spend[spend["spend"] > 0].reset_index(drop=True)
    cpc = spend["channel"].map(mk["cpc"]).to_numpy()
    ctr = spend["channel"].map(mk["ctr"]).to_numpy()
    clicks = np.round(spend["spend"].to_numpy() / cpc * rng.normal(1, 0.1, len(spend))).clip(0)
    spend["clicks"] = clicks.astype(np.int64)
    spend["impressions"] = np.round(clicks / ctr).astype(np.int64)
    spend["spend"] = spend["spend"].round(2)
    return spend
