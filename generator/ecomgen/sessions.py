"""Web and app sessions: converting visits, research visits, abandoned checkouts and anonymous browsing."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .reference import channel_in_campaign, weights

DEVICES = np.array(["desktop", "mobile_web", "ios_app", "android_app"], dtype=object)
DEVICE_INDEX = {d: i for i, d in enumerate(DEVICES)}


def session_ids(rng, n: int) -> np.ndarray:
    return np.array([f"{x:016x}" for x in rng.integers(0, 2**62, n).tolist()], dtype=object)


def _day(ts: np.ndarray, cal) -> np.ndarray:
    return (ts.astype("datetime64[D]") - np.datetime64(cal.sim_start)).astype(np.int64)


def _campaign_codes(rng, day, channel, cal, campaigns, day_camp, share):
    """Tag a session with the live campaign's code if it came through one of the campaign's channels."""
    camp = np.where((day >= 0) & (day < cal.n), day_camp[np.clip(day, 0, cal.n - 1)], -1)
    tagged = channel_in_campaign(camp, channel, campaigns) & (rng.random(len(day)) < share)
    return np.where(tagged, campaigns["code"].to_numpy(dtype=object)[np.maximum(camp, 0)], None)


def _landing(rng, campaign_code, s):
    pages = rng.choice(np.array(s["landing_pages"], dtype=object), len(campaign_code), p=weights(s["landing_share"]))
    return np.where(pd.notna(campaign_code), "promo", pages)


def build_known_sessions(rng, params, cal, customers, orders, abandoned, campaigns, day_camp, areas):
    """Sessions tied to a known customer journey. `o` links converting sessions to their order."""
    s = params["sessions"]
    web = orders[orders["sales_channel"] != "marketplace"]
    parts = []

    # 1. The session in which each web/app order was placed
    n = len(web)
    conv_start = web["ts"].to_numpy() - rng.integers(120, 2400, n).astype("timedelta64[s]")
    parts.append(pd.DataFrame({
        "start": np.maximum(conv_start, np.datetime64(cal.start, "s")),   # keep every order's session in range
        "cust": web["cust"].to_numpy(), "true_cust": web["cust"].to_numpy(),
        "device": web["device"].to_numpy(dtype=object), "channel": web["channel"].to_numpy(dtype=object),
        "campaign_code": web["campaign_code"].to_numpy(dtype=object),
        "pageviews": 4 + rng.poisson(4, n), "added_to_basket": True, "converted": True,
        "o": web["o"].to_numpy(), "kind": "converting",
    }))

    # 2. Earlier research visits by the same (real) customers
    base = web[~web["is_test"]]
    rep = np.repeat(np.arange(len(base)), rng.poisson(s["prior_per_order"], len(base)))
    m = len(rep)
    start = base["ts"].to_numpy()[rep] - rng.uniform(3600, s["prior_max_days"] * 86400, m).astype("timedelta64[s]")
    true_cust = base["cust"].to_numpy()[rep]
    channel = rng.choice(np.array([c["name"] for c in params["channel"]], dtype=object), m,
                         p=weights([c["browse"] for c in params["channel"]]))
    parts.append(pd.DataFrame({
        "start": start,
        "cust": np.where(rng.random(m) < s["logged_in_share"], true_cust, -1), "true_cust": true_cust,
        "device": np.where(rng.random(m) < 0.7, base["device"].to_numpy(dtype=object)[rep], rng.choice(DEVICES, m)),
        "channel": channel,
        "campaign_code": _campaign_codes(rng, _day(start, cal), channel, cal, campaigns, day_camp, s["campaign_click_share"]),
        "pageviews": 1 + rng.poisson(3, m), "added_to_basket": rng.random(m) < s["prior_basket_rate"],
        "converted": False, "o": -1, "kind": "prior",
    }))

    # 3. Checkouts that were started but not completed
    k = len(abandoned)
    parts.append(pd.DataFrame({
        "start": abandoned["ts"].to_numpy() - rng.integers(120, 2400, k).astype("timedelta64[s]"),
        "cust": abandoned["cust"].to_numpy(), "true_cust": abandoned["cust"].to_numpy(),
        "device": abandoned["device"].to_numpy(dtype=object), "channel": abandoned["channel"].to_numpy(dtype=object),
        "campaign_code": abandoned["campaign_code"].to_numpy(dtype=object),
        "pageviews": 5 + rng.poisson(3, k), "added_to_basket": True, "converted": False,
        "o": -1, "kind": "abandoned",
    }))

    known = pd.concat(parts, ignore_index=True)
    known = known[known["start"] >= np.datetime64(cal.start)].reset_index(drop=True)
    known["landing_page_type"] = _landing(rng, known["campaign_code"].to_numpy(dtype=object), s)

    # IP-derived postcode area: usually the customer's home area
    home = customers["area"].to_numpy(dtype=object)[known["true_cust"].to_numpy()]
    rand_area = rng.choice(areas["postcode_area"].to_numpy(dtype=object), len(known), p=areas["weight"].to_numpy())
    known["postcode_area"] = np.where(rng.random(len(known)) < s["ip_area_accuracy"], home, rand_area)
    known["session_id"] = session_ids(rng, len(known))
    return known.drop(columns="true_cust")


def anonymous_rates(params, cal, demand, known) -> np.ndarray:
    """Expected anonymous sessions per [day, device], so that conversion lands on the device baseline."""
    cr = np.array([params["conversion_rate"][d] for d in DEVICES])
    dem = np.zeros((cal.n, len(DEVICES)))
    np.add.at(dem, (demand["day"].to_numpy(), demand["device"].map(DEVICE_INDEX).to_numpy()), 1)
    prior = known[known["kind"] == "prior"]
    pri = np.zeros_like(dem)
    np.add.at(pri, (_day(prior["start"].to_numpy(), cal), prior["device"].map(DEVICE_INDEX).to_numpy()), 1)

    kernel = np.ones(7) / 7                                 # smooth day-to-day noise
    dem = np.apply_along_axis(lambda x: np.convolve(x, kernel, "same"), 0, dem)
    pri = np.apply_along_axis(lambda x: np.convolve(x, kernel, "same"), 0, pri)
    lam = np.maximum(0.0, dem / cr - dem - pri)
    lam[: cal.first] = 0
    return lam


def anonymous_month(rng, params, cal, lam, month, campaigns, day_camp, areas) -> pd.DataFrame:
    """Anonymous browsing sessions for one calendar month (generated month by month to save memory)."""
    s = params["sessions"]
    days = np.flatnonzero((cal.month_index == month) & (np.arange(cal.n) >= cal.first))
    counts = rng.poisson(lam[days]).ravel()                 # row-major: day, then device
    day = np.repeat(np.repeat(days, len(DEVICES)), counts)
    dev = np.repeat(np.tile(np.arange(len(DEVICES)), len(days)), counts)
    n = len(day)

    hour = rng.choice(24, n, p=weights(params["seasonality"]["hour"]))
    start = cal.dates[day].astype("datetime64[s]") + (hour * 3600 + rng.integers(0, 3600, n)).astype("timedelta64[s]")
    channel = rng.choice(np.array([c["name"] for c in params["channel"]], dtype=object), n,
                         p=weights([c["browse"] for c in params["channel"]]))
    campaign_code = _campaign_codes(rng, day, channel, cal, campaigns, day_camp, s["campaign_click_share"])
    return pd.DataFrame({
        "start": start, "cust": -1, "device": DEVICES[dev], "channel": channel, "campaign_code": campaign_code,
        "pageviews": 1 + rng.poisson(2, n), "added_to_basket": rng.random(n) < s["browse_basket_rate"],
        "converted": False, "o": -1, "kind": "anonymous",
        "landing_page_type": _landing(rng, campaign_code, s),
        "postcode_area": rng.choice(areas["postcode_area"].to_numpy(dtype=object), n, p=areas["weight"].to_numpy()),
        "session_id": session_ids(rng, n),
    })
