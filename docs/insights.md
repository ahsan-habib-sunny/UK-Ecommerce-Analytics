# Insights: seven stories in the data

The generator planted seven business stories with parameters kept in a sealed folder, so the analysis had to *find* them rather than know them. Each is shown below with what the report shows, the numbers (measured in Snowflake MARTS) and the recommended action. Six are business problems; one is a data-quality trap in the source data.

| # | Story | Headline number | Where it shows |
|---|---|---|---|
| S1 | Spring sale that "worked" | ROAS 1.2× looks positive; margin ROI **−77%** | Marketing: campaign scorecard |
| S2 | Faulty earbuds | Return rate **5.8% → 31.7%**, 90% "faulty" | Sales & Products: return reasons, Top 10 |
| S3 | Northern Ireland delivery surcharge | NI conversion **−28%**, rest of UK flat | Web Funnel: conversion by region |
| S4 | Black Friday 2024 cohort | Month-3 retention **4.6%** vs 10–14% | Customers: cohort heat-map |
| S5 | iOS checkout bug | iOS conversion **4.5% → 1.8%** for 3 weeks | Web Funnel: conversion by device |
| S6 | Free-delivery threshold raised | £40–60 baskets **16.6% → 5.0%** of orders | Sales & Products / AOV |
| S7 | "London boom" week (data-quality trap) | **1,500 fake orders** from 25 test accounts | Executive: orders by month; found by profiling |

---

### S1. The campaign that "worked": SPRING25 (10–23 Mar 2025, 30% off)

| | 4 weeks before | During | 2 weeks after |
|---|---|---|---|
| Orders per day | 155 | **288 (+86%)** | 127 (−18%) |
| Margin % | 40.6% | **30.7%** | 40.9% |

- Attributed revenue **£102,376** on **£85,481** spend, so **ROAS 1.20×**. On revenue, it looks like it paid back.
- Attributed gross margin **£19,444**, so **Campaign ROI −77%**. On profit, it lost about £66k.
- Orders fell **below** baseline afterwards: part of the "uplift" was demand pulled forward from customers who would have bought anyway.
- **Action:** judge promotions on **margin-based ROI net of pull-forward**, not ROAS. A 30% discount on a ~40% margin business needs a very large incremental volume to pay back.

### S2. The faulty earbuds: P-10421 "Aero Pro Wireless Earbuds"

| Orders placed | Units sold | Units returned | Return rate |
|---|---|---|---|
| Before 1 Jun 2025 | 10,284 | 597 | **5.8%** |
| From 1 Jun 2025 | 6,787 | 2,151 | **31.7%** |

- It is the **#2 product by net revenue**, so the problem is big enough to move the Electronics return rate.
- **90%** of its returns since June have the reason **"Faulty or damaged"**: a product-quality problem, not sizing or expectations. The step change lines up with a supplier change.
- **Action:** quality hold on the current batch, a supplier claim, and a review of the stock received since June.

### S3. The Northern Ireland surcharge (from 15 Jan 2025, +£4.95 delivery to BT)

| Session conversion | 6 months before | 6 months after |
|---|---|---|
| Northern Ireland | 2.73% | **1.96% (−28%)** |
| Rest of UK | 2.87% | 3.02% |

- Sessions and add-to-basket rate in NI are **unchanged** (≈10%). People still shop; they drop out at checkout when the delivery charge appears.
- **Action:** test a free-delivery threshold for NI, or absorb part of the surcharge. The lost conversions are worth more than the fee.

### S4. The Black Friday 2024 cohort (BF24 ran at 40% off, not the usual 25%)

| First-order month | Customers | Ordered again in month 3 | Repeat within months 1–3 |
|---|---|---|---|
| Aug 2024 | 2,176 | 13.9% | 30.0% |
| Sep 2024 | 2,267 | 11.2% | 30.9% |
| Oct 2024 | 2,438 | 9.6% | 30.5% |
| **Nov 2024** | **4,470** | **4.6%** | **16.4%** |
| Dec 2024 | 3,418 | 9.9% | 23.6% |

- Biggest acquisition month of the year, and the worst-quality customers: deal hunters who rarely came back.
- **Action:** count **customer lifetime value**, not new-customer volume, in campaign targets. Deeper discounts bought volume, not loyal customers.

### S5. The iOS checkout bug (4–24 Aug 2025)

| iOS app | Before | 4–24 Aug | After |
|---|---|---|---|
| Conversion | 4.51% | **1.80%** | 4.42% |
| Add-to-basket rate | 11.7% | 11.8% | 11.8% |

- Other devices were flat (Android 3.55% → 3.58%, desktop 3.73% → 3.71%).
- Baskets were filled as normal but orders didn't complete, which points to **checkout**, not demand. At total level the dip looks like summer seasonality; split by device it's obvious.
- **Action:** add a **conversion-by-device alert** (e.g. a daily drop of more than 30% against the 4-week average) so an app release problem is caught in days, not weeks.

### S6. The free-delivery threshold change (1 Sep 2025: £40 → £60)

| Web and app orders | Mar–Aug 2025 | Sep 2025–Feb 2026 |
|---|---|---|
| Baskets of £40–£60 | **16.6%** | **5.0%** |
| Average basket (inc. VAT) | £96.08 | £100.59 |

- Customers either topped up their basket to £60 or didn't order. AOV rose, but lower-value customers ordered noticeably less afterwards.
- **Action:** read AOV together with **order frequency and active customers**. A rising AOV can hide lost customers.

### S7. Data-quality trap: the "London boom" week (7–11 Apr 2025)

- Orders per day doubled from **207 to 415** that week, all delivered to postcode area **EC** (City of London).
- Cause: an IT load test wrote **1,500 orders** from **25 test accounts** (emails ending `@qa.internal.test`) into production. Each order was £1, had no delivery fee, and had one converting session.
- Generic cleaning doesn't catch them: they are unique, valid-looking orders. They show up as an outlier in **orders per customer** (50–71 orders each in five days) and in **email-domain profiling**.
- **Status: identified and quantified; the fix is designed but deliberately not applied.** The published numbers include these orders. Applying the fix means reloading the large fact tables (see below), and for this portfolio build the impact (0.6% of orders, £1,276 of revenue, one week) was documented rather than reprocessed.
- **Designed fix**, following the STAGING rule (flag, never silently drop):
  - `stg_customers.is_test_account` (email ends `@qa.internal.test`), `stg_orders.is_test_order` and `stg_sessions.is_test_account` flag the rows in STAGING.
  - MARTS views filter `WHERE NOT is_test_…`.
  - `07_dq_checks` reports the counts (25 accounts, 1,500 orders).
  - A `09_marts_tests` test fails if any test-account row reaches MARTS.
  - Edge case found while testing the fix: customers with no email give a NULL flag, and `WHERE NOT NULL` drops the row. The flag must be `COALESCE(…, FALSE)`.
- **Effect if applied** (verified with a read-only run of the changed views):

| | Published (includes test data) | After the fix |
|---|---|---|
| Net Revenue | £19,415,548 | £19,414,272 |
| Orders | 233,799 | 232,299 |
| Sessions | 7,131,889 | 7,130,389 |
| Customers (dim) | 151,102 | 151,077 |

  Revenue barely moves (£1 orders), but **orders, AOV, conversion and London's numbers** are distorted for that week. Read 7–11 Apr 2025 with care.
- **Why it isn't a quick fix: incremental refresh doesn't see deletions.** A bucket is re-pulled only when its latest `loaded_at` changes, and removing rows doesn't change it. Removing data from an old period means forcing a reload: re-loading RAW so every `loaded_at` moves, then a full model refresh. In production this is worth designing for up front, with soft-delete flags or a "logic changed" timestamp that incremental refresh can detect.
