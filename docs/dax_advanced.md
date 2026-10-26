# DAX, Day 10: RFM, campaign ROI and attribution, calculation group, field parameters

Everything below was written directly into the PBIP model files. Open `pbip/UK_Ecommerce.pbip` and it's there.

## What was added

| Object | Type | What it does |
|---|---|---|
| **Customer RFM** | Calculated table (one row per customer) | Recency, Frequency, Monetary over the 12 months to the data end date; R/F/M scores 1–5; **RFM Segment**. Related to `fact_order_line` and `fact_returns`, so a segment slicer filters sales. |
| **Time Intelligence** | Calculation group | Current · MTD · QTD · YTD · Fiscal YTD · PY · PY YTD · YoY · YoY % · Rolling 12M, for **any** measure |
| **Metric Selector** | Field parameter | Switch a visual between 12 measures (Net Revenue, Orders, Margin %, Conversion…) |
| **Dimension Selector** | Field parameter | Switch a visual's breakdown: Region, Category, Marketing Channel, Campaign Type, Age Band, RFM Segment |
| Measures, **RFM** folder | RFM Customers · RFM Revenue 12M · RFM Revenue Share % · Avg Recency Days | |
| Measures, **Marketing** folder | ROAS · Campaign ROI % · Cost per New Customer · Net Revenue (Acquisition Channel) | |

The model setting **Discourage implicit measures** is now on (required by calculation groups): report visuals use measures only, not auto-summed columns.

### RFM rules
- **Population:** customers with ≥1 completed order in the last 12 months (51,517, the same as *Active Customers (12M)*). Everyone else is *Inactive (no order in 12M)*.
- **R** and **M**: quintiles (1–5) over that population. **F**: order-count bands (1, 2, 3, 4, 5+), because most customers order once, so frequency quintiles would be meaningless.
- **Segments:** Champions (R≥4, F≥3) · Loyal (R≥3, F≥2) · Promising (R≥4, F=1) · Needs Attention (R=3, F=1) · At Risk (R≤2, F≥2) · About to Sleep (R=2, F=1) · Lost (R=1, F=1).

### Attribution: two views
- **Last non-direct click** (default): `Net Revenue` sliced by `dim_channel` / `dim_campaign`.
- **Acquisition channel** (first-touch, customer lifetime): `Net Revenue (Acquisition Channel)` credits all of a customer's revenue to the channel that brought them in. Put both side by side by channel: the gap shows which channels *acquire* customers and which *close* sales.

### Calculation group: one detail worth knowing
`PY`, `PY YTD`, `YoY` and `YoY %` only compare the part of the period **that has data**: data stops on 30 Sep 2026, so "2026 vs 2025" compares Jan–Sep with Jan–Sep, not Jan–Sep with all of 2025. That's a common bug in real reports.

## Step 1: Open
Close Desktop if open (don't save), then open `pbip/UK_Ecommerce.pbip`. The calculated table and the field parameters compute on open (~30 s).
If you see an error (e.g. "circular dependency" or a TMDL line error), send me the exact message.

## Step 2: Check visuals (scratch page, delete afterwards if you like)

**A. RFM segments**: Table: `Customer RFM[RFM Segment]`, `[RFM Customers]`, `[RFM Revenue 12M]`, `[RFM Revenue Share %]`.

**B. Campaign ROI**: Table: `dim_campaign[CAMPAIGN_CODE]`, `[Net Revenue]`, `[Gross Margin]`, `[Marketing Spend]`, `[ROAS]`, `[Campaign ROI %]`.

**C. Time intelligence**: Matrix: rows `dim_date[YEAR]` then `dim_date[MONTH_NAME]`, columns `Time Intelligence[Time Calculation]`, values `[Net Revenue]`.

**D. Field parameters**: a slicer on `Metric Selector`, a slicer on `Dimension Selector`, and a clustered bar chart with axis = `Dimension Selector` and values = `Metric Selector`. Click around: the chart changes measure and breakdown.

**E. Attribution**: Table: `dim_channel[CHANNEL_NAME]`, `[Net Revenue]`, `[Net Revenue (Acquisition Channel)]`.

## Step 3: Validate (expected values from Snowflake MARTS)

| Visual | Check | Expected |
|---|---|---|
| A | Champions · customers / revenue 12M / share | **4,043 / £1,682,200 / 25.4%** |
| A | Loyal | **6,972 / £1,562,228** |
| A | Promising | **12,711 / £955,021** |
| A | Needs Attention · At Risk · About to Sleep · Lost | **7,200 · 2,883 · 8,264 · 9,444** |
| A | Inactive (no order in 12M) | **99,584** customers |
| A | Total RFM Customers | **51,517** |
| B | JAN25 · revenue / margin / spend / ROAS / ROI | **£121,075 / £39,519 / £24,507 / 4.94x / 61.3%** |
| B | BF25 · revenue / margin / spend / ROAS / ROI | **£179,292 / £52,174 / £43,664 / 4.11x / 19.5%** |
| C | 2026 · September · Current / PY / YoY % | **£544,907 / £468,771 / 16.2%** |
| C | 2026 · September · YTD / PY YTD | **£4,713,964 / £3,948,165** |
| C | 2026 (year row) · YoY % | **19.4%** (Jan–Sep vs Jan–Sep) |
| C | 2026 · March · Fiscal YTD | **£6,015,600** (FY2026 = Apr 2025–Mar 2026) |
| E | Paid Search · last-click / acquisition channel | **£3,524,149 / £4,389,448** |

**Insights already visible:** Champions are **7.8%** of active customers but **25%** of revenue; Paid Search acquires more value (£4.39M lifetime) than it gets credit for on a last-click basis (£3.52M).

## Step 4: Commit
Save in Desktop, then commit on a branch, PR and merge as usual. `git diff` shows the new tables as `.tmdl` files: the calculation group and field parameters are readable text, which is exactly what reviewers want to see in a PR.
