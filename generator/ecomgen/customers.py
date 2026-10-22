"""Customer acquisition and repeat-purchase simulation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .reference import random_postcodes, weights

FIRST_NAMES = ["Oliver", "Amelia", "George", "Isla", "Harry", "Ava", "Noah", "Mia", "Jack", "Ivy",
               "Leo", "Lily", "Arthur", "Grace", "Muhammad", "Freya", "Oscar", "Sophia", "Charlie", "Emily",
               "Jacob", "Ella", "Thomas", "Poppy", "Alfie", "Evie", "Henry", "Isabella", "Theo", "Florence",
               "Aisha", "Priya", "Ravi", "Zara", "Callum", "Niamh", "Ciaran", "Eilidh", "Rhys", "Seren",
               "Daniel", "Chloe", "James", "Sarah", "David", "Laura", "Michael", "Rachel", "Paul", "Helen"]
LAST_NAMES = ["Smith", "Jones", "Williams", "Taylor", "Brown", "Davies", "Evans", "Wilson", "Thomas", "Johnson",
              "Roberts", "Robinson", "Thompson", "Wright", "Walker", "White", "Edwards", "Hughes", "Green", "Hall",
              "Lewis", "Harris", "Clarke", "Patel", "Jackson", "Wood", "Turner", "Martin", "Cooper", "Hill",
              "Ward", "Morris", "Moore", "Clark", "Lee", "King", "Baker", "Harrison", "Morgan", "Allen",
              "Khan", "Ali", "Campbell", "Stewart", "Murray", "Kelly", "O'Neill", "Doherty", "Begum", "Singh"]
EMAIL_DOMAINS = ["example.co.uk", "example.com", "example.net", "example.org"]   # reserved, never real


def simulate_customers(rng, params, scenario, cal, campaigns, day_camp, areas):
    """Return (customers, events). One event = one purchase attempt by a customer on a day."""
    tiers = params["tiers"]
    has_camp = day_camp >= 0
    lift = np.ones(cal.n)
    lift[has_camp] = campaigns["acquisition_lift"].to_numpy()[day_camp[has_camp]]

    # 1. New customers per day: trend × seasonality × campaign lift, with Poisson noise
    lam = params["acquisition"]["new_per_day"] * params["scale"] * cal.season * cal.growth * lift
    acq_day = np.repeat(np.arange(cal.n), rng.poisson(lam))
    n = len(acq_day)

    # 2. Who they are
    tier = rng.choice(len(tiers["names"]), n, p=weights(tiers["share"]))
    camp = day_camp[acq_day]
    via_campaign = (camp >= 0) & (rng.random(n) < (lift[acq_day] - 1) / lift[acq_day])
    acq_campaign = np.where(via_campaign, camp, -1)

    ch = params["channel"]
    ch_names = np.array([c["name"] for c in ch], dtype=object)
    acq_channel = rng.choice(ch_names, n, p=weights([c["acquire"] for c in ch]))
    for i in np.unique(acq_campaign[via_campaign]):
        m = acq_campaign == i
        acq_channel[m] = rng.choice(np.array(campaigns["channels"].iat[i], dtype=object), m.sum())

    sc, dv = params["sales_channel"], params["devices"]
    area = rng.choice(areas["postcode_area"].to_numpy(dtype=object), n, p=areas["weight"].to_numpy())
    first = rng.choice(FIRST_NAMES, n)
    last = rng.choice(LAST_NAMES, n)
    email = [f"{f}.{l}{k}@{dom}".lower().replace("'", "")
             for f, l, k, dom in zip(first, last, rng.integers(1, 999, n), rng.choice(EMAIL_DOMAINS, n))]
    age_days = (np.clip(rng.normal(42, 14, n), 18, 85) * 365.25).astype(np.int64)
    dob = np.datetime64(cal.start) - age_days.astype("timedelta64[D]")

    customers = pd.DataFrame({
        "cust": np.arange(n),
        "acq_day": acq_day,
        "tier": tier,
        "acq_channel": acq_channel,
        "acq_campaign": acq_campaign,
        "sales_pref": rng.choice(np.array(sc["names"], dtype=object), n, p=weights(sc["share"])),
        "web_dev": rng.choice(np.array(dv["web"], dtype=object), n, p=weights(dv["web_share"])),
        "app_dev": rng.choice(np.array(dv["app"], dtype=object), n, p=weights(dv["app_share"])),
        "area": area,
        "postcode": random_postcodes(rng, area),
        "first_name": first,
        "last_name": last,
        "email": np.where(rng.random(n) < 0.03, None, np.array(email, dtype=object)),
        "dob": np.where(rng.random(n) < 0.85, dob, np.datetime64("NaT")),
        "opt_in": rng.random(n) < 0.6,
        "is_test": np.zeros(n, dtype=bool),
    })

    # 3. Behaviour multipliers for particular acquisition cohorts
    churn_mult, gap_mult = np.ones(n), np.ones(n)
    for co in scenario.get("cohort_override", []):
        m = (acq_day >= cal.idx(co["acquired_from"])) & (acq_day <= cal.idx(co["acquired_to"]))
        churn_mult[m] *= co.get("churn_mult", 1.0)
        gap_mult[m] *= co.get("gap_mult", 1.0)

    events = _repeat_purchases(rng, params, scenario, cal, campaigns, acq_day, tier, churn_mult, gap_mult)
    return customers, events


def _repeat_purchases(rng, params, scenario, cal, campaigns, acq_day, tier, churn_mult, gap_mult):
    """Walk each customer forward in time: after every order they either churn or come back later."""
    tiers = params["tiers"]
    churn = tiers["churn_prob"]
    gap_mean = tiers["mean_gap_days"]
    shape = tiers["gap_shape"]
    tier_index = {name: i for i, name in enumerate(tiers["names"])}

    # Date-based changes in behaviour for some tiers (e.g. after a policy change)
    shifts = [(cal.idx(s["start"]), {tier_index[t] for t in s["tiers"]}, s.get("churn_mult", 1.0), s.get("gap_mult", 1.0))
              for s in scenario.get("behaviour_shift", [])]
    # Campaigns that pull a customer's next order forward into the campaign window
    pull = [(cal.idx(c.start_date), cal.idx(c.end_date), c.pull_forward_prob, c.pull_forward_days)
            for c in campaigns.itertuples() if c.pull_forward_prob > 0]

    season = cal.season.tolist()
    season_max = max(season)
    last_day = cal.n - 1
    rand, gamma = rng.random, rng.gamma

    ev_cust, ev_day, ev_seq = [], [], []
    for i, (t, k, cm, gm) in enumerate(zip(acq_day.tolist(), tier.tolist(), churn_mult.tolist(), gap_mult.tolist())):
        seq = 0
        ev_cust.append(i); ev_day.append(t); ev_seq.append(seq)
        while True:
            p, g = churn[k] * cm, gap_mean[k] * gm
            for start, ts, c_mult, g_mult in shifts:
                if t >= start and k in ts:
                    p, g = p * c_mult, g * g_mult
            if rand() < min(p, 0.97):
                break

            # Next order date: gamma gap, then thinned so busy seasons get more orders
            nxt = t
            while True:
                nxt += max(1, int(gamma(shape, g / shape)))
                if nxt > last_day or rand() * season_max < season[nxt]:
                    break
            if nxt > last_day:
                break

            for start, end, prob, days in pull:
                if t < start and end < nxt <= end + days and rand() < prob:
                    nxt = start + int(rand() * (end - start + 1))
                    break

            seq += 1
            ev_cust.append(i); ev_day.append(nxt); ev_seq.append(seq)
            t = nxt

    return pd.DataFrame({"cust": ev_cust, "day": ev_day, "seq": ev_seq})
