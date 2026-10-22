"""Reference data: postcode areas, the product range and the campaign calendar."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

UNIT_LETTERS = np.array(list("ABDEFGHJLNPQRSTUWXYZ"))  # letters real postcodes use in the last part

SUBCATEGORY_NOUNS = {
    "Womenswear": ["Midi Dress", "Linen Shirt", "Knit Jumper", "Wide-Leg Trousers", "Wrap Skirt", "Denim Jacket"],
    "Menswear": ["Oxford Shirt", "Chino Trousers", "Crew Jumper", "Overshirt", "Polo Shirt", "Rain Jacket"],
    "Footwear": ["Leather Trainers", "Chelsea Boots", "Running Shoes", "Loafers", "Sandals"],
    "Accessories": ["Leather Belt", "Wool Scarf", "Crossbody Bag", "Beanie", "Sunglasses"],
    "Kitchen": ["Chef's Knife", "Cast Iron Pan", "Mixing Bowl Set", "Coffee Grinder", "Storage Jars"],
    "Bedding": ["Duvet Cover Set", "Pillow Pair", "Throw Blanket", "Fitted Sheet"],
    "Decor": ["Ceramic Vase", "Wall Mirror", "Scented Candle", "Photo Frame", "Cushion Cover"],
    "Furniture": ["Side Table", "Bookcase", "Accent Chair", "Bedside Table"],
    "Lighting": ["Table Lamp", "Floor Lamp", "Pendant Shade", "LED Strip"],
    "Audio": ["Wireless Earbuds", "Bluetooth Speaker", "Over-Ear Headphones", "Soundbar"],
    "Phones & Accessories": ["Phone Case", "USB-C Charger", "Power Bank", "Screen Protector"],
    "Smart Home": ["Smart Plug", "Video Doorbell", "Smart Bulb", "Indoor Camera"],
    "Computing": ["Wireless Mouse", "Mechanical Keyboard", "USB Hub", "Laptop Stand", "Webcam"],
    "Gaming": ["Gaming Headset", "Controller", "Gaming Mouse", "Capture Card"],
    "Skincare": ["Daily Moisturiser", "Vitamin C Serum", "Gentle Cleanser", "SPF 50 Fluid"],
    "Haircare": ["Repair Shampoo", "Hair Mask", "Styling Cream", "Hair Dryer"],
    "Fragrance": ["Eau de Parfum", "Eau de Toilette", "Body Mist"],
    "Makeup": ["Matte Lipstick", "Foundation", "Mascara", "Eyeshadow Palette"],
    "Fiction": ["Novel", "Thriller", "Short Stories"],
    "Non-fiction": ["Biography", "History", "Popular Science"],
    "Children's Books": ["Picture Book", "Activity Book", "Early Reader"],
    "Cookery": ["Cookbook", "Baking Book"],
    "Clothing": ["Kids Hoodie", "Kids Pyjamas", "School Polo", "Baby Bodysuit Set"],
    "Toys": ["Building Set", "Plush Toy", "Puzzle", "Craft Kit", "Board Game"],
    "Nursery": ["Baby Monitor", "Changing Bag", "Bottle Set", "Cot Mobile"],
}
ADJECTIVES = ["Classic", "Essential", "Premium", "Everyday", "Studio", "Heritage",
              "Urban", "Pure", "Signature", "Compact", "Nordic", "Coastal"]
BRAND_START = ["Ash", "Bram", "Cal", "Dun", "Elm", "Fen", "Gil", "Hart", "Ivy", "Kes",
               "Lark", "Mor", "Nor", "Oak", "Pem", "Quill", "Rook", "Sel", "Tor", "Wren"]
BRAND_END = ["by", "ford", "wick", "ton", "mere", "dale", "worth", "field", "ley", "stone"]


def weights(x) -> np.ndarray:
    w = np.asarray(x, dtype=float)
    return w / w.sum()


# --- Postcodes ------------------------------------------------------------------

def load_postcode_areas(path: Path) -> pd.DataFrame:
    areas = pd.read_csv(path)
    areas["weight"] = weights(areas["population_k"])
    return areas


def random_postcodes(rng: np.random.Generator, areas: np.ndarray) -> np.ndarray:
    """Build plausible full postcodes (e.g. 'M14 5RT') inside the given postcode areas."""
    n = len(areas)
    district = rng.integers(1, 21, n).astype(str)
    sector = rng.integers(0, 10, n).astype(str)
    unit = np.char.add(UNIT_LETTERS[rng.integers(0, 20, n)], UNIT_LETTERS[rng.integers(0, 20, n)])
    outward = np.char.add(np.asarray(areas).astype(str), district)
    return np.char.add(np.char.add(outward, " "), np.char.add(sector, unit)).astype(object)


# --- Products --------------------------------------------------------------------

def _random_date(rng: np.random.Generator, lo: date, hi: date) -> date:
    return lo + timedelta(days=int(rng.integers(0, max((hi - lo).days, 1))))


def build_products(rng, params: dict, scenario: dict, cal) -> pd.DataFrame:
    cfg, cats = params["products"], params["category"]
    n = cfg["count"]
    cat_of = rng.choice(len(cats), n, p=weights([c["share"] for c in cats]))

    names = [a + b for a in BRAND_START for b in BRAND_END]
    picked = rng.choice(len(names), len(cats) * cfg["brands_per_category"], replace=False)
    brands = np.array(names)[picked].reshape(len(cats), -1)

    rows = []
    for i in range(n):
        c = cats[cat_of[i]]
        sub = str(rng.choice(c["subcategories"]))
        brand = str(rng.choice(brands[cat_of[i]]))
        name = f"{brand} {rng.choice(ADJECTIVES)} {rng.choice(SUBCATEGORY_NOUNS[sub])}"
        list_price = max(2.99, float(np.floor(rng.lognormal(np.log(c["price_median"]), c["price_sigma"]))) + 0.99)
        vat = 0.0 if sub in c.get("zero_vat_subcategories", []) else c["vat_rate"]
        unit_cost = round(list_price / (1 + vat) * (1 - c["margin"]) * rng.normal(1, 0.08), 2)

        if rng.random() < cfg["launched_before_share"]:
            launched = _random_date(rng, date(2017, 1, 1), cal.sim_start)
        else:
            launched = _random_date(rng, cal.sim_start, cal.end - timedelta(days=90))
        discontinued = None
        earliest = max(launched + timedelta(days=365), cal.sim_start + timedelta(days=90))
        if rng.random() < cfg["discontinued_share"] and earliest < cal.end - timedelta(days=30):
            discontinued = _random_date(rng, earliest, cal.end - timedelta(days=30))

        rows.append(dict(product_id=10001 + i, sku=f"P-{10001 + i}", product_name=name,
                         category=c["name"], subcategory=sub, brand=brand,
                         list_price=list_price, unit_cost=unit_cost, vat_rate=vat,
                         launched_on=launched, discontinued_on=discontinued))
    products = pd.DataFrame(rows)

    exponent = cfg["popularity_exponent"]
    products["popularity"] = (rng.permutation(n) + 1.0) ** -exponent

    # Named products the scenario needs (specific SKU, price, popularity rank)
    for ov in scenario.get("product_override", []):
        i = products.index[products["sku"] == ov["sku"]][0]
        for key, value in ov.items():
            if key in products.columns and key != "sku":
                products.at[i, key] = value
        if ov.get("active_throughout"):
            products.at[i, "discontinued_on"] = None
        if "popularity_rank" in ov:
            products.at[i, "popularity"] = ov["popularity_rank"] ** -exponent
    return products


# --- Campaigns -------------------------------------------------------------------

def black_friday(year: int) -> date:
    """The day after the fourth Thursday of November."""
    nov1 = date(year, 11, 1)
    first_thursday = nov1 + timedelta(days=(3 - nov1.weekday()) % 7)
    return first_thursday + timedelta(days=22)


TEMPLATE_ONLY_KEYS = {"start", "anchor", "offset_days", "months", "day", "days"}


def build_campaigns(params: dict, scenario: dict, cal) -> pd.DataFrame:
    rows = []
    for year in range(cal.start.year, cal.end.year + 1):
        for t in params["campaign_template"]:
            if "months" in t:
                starts = [(date(year, m, t["day"]), m) for m in t["months"]]
            elif t.get("anchor") == "black_friday":
                starts = [(black_friday(year) + timedelta(days=t["offset_days"]), None)]
            else:
                mm, dd = map(int, t["start"].split("-"))
                starts = [(date(year, mm, dd), None)]

            for start, month in starts:
                end = start + timedelta(days=t["days"] - 1)
                if start < cal.start or end > cal.end:
                    continue
                fill = dict(yy=f"{year % 100:02d}", yyyy=year, mm=f"{month or 0:02d}", mon=start.strftime("%b"))
                row = {k: v for k, v in t.items() if k not in TEMPLATE_ONLY_KEYS}
                row.update(code=t["code"].format(**fill), name=t["name"].format(**fill),
                           start_date=start, end_date=end)
                row.setdefault("categories", [])
                row.setdefault("pull_forward_prob", 0.0)
                row.setdefault("pull_forward_days", 0)
                rows.append(row)

    overrides = {o["code"]: o for o in scenario.get("campaign_override", [])}
    for row in rows:
        row.update({k: v for k, v in overrides.get(row["code"], {}).items() if k != "code"})

    campaigns = pd.DataFrame(rows).sort_values("start_date", kind="stable").reset_index(drop=True)
    campaigns.insert(0, "campaign_id", np.arange(1, len(campaigns) + 1))
    return campaigns


def daily_campaign(cal, campaigns: pd.DataFrame) -> np.ndarray:
    """For each day, the index of the live campaign (biggest discount wins overlaps), or -1."""
    best = np.full(cal.n, -1)
    disc = campaigns["discount"].to_numpy()
    lift = campaigns["acquisition_lift"].to_numpy()
    for i, (s, e) in enumerate(zip(campaigns["start_date"], campaigns["end_date"])):
        for d in range(cal.idx(s), cal.idx(e) + 1):
            j = best[d]
            if j < 0 or (disc[i], lift[i]) > (disc[j], lift[j]):
                best[d] = i
    return best


def channel_in_campaign(camp: np.ndarray, channel: np.ndarray, campaigns: pd.DataFrame) -> np.ndarray:
    """True where the row's marketing channel is one of its campaign's channels."""
    out = np.zeros(len(camp), dtype=bool)
    for i in np.unique(camp[camp >= 0]):
        m = camp == i
        out[m] = np.isin(channel[m], campaigns["channels"].iat[i])
    return out
