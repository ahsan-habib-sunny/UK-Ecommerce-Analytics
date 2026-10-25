# DAX, Day 9: customers, retention, churn and cohorts

All measures were written straight into the PBIP model files (`pbip/UK_Ecommerce.SemanticModel/definition/tables/_Measures.tmdl`) with formats, folders and descriptions. Open the project and they're there.

## Measures

| Folder | Measure | Business rule (docs/data_model.md) |
|---|---|---|
| Customers | **Customers** | Distinct customers with ≥1 completed order in context |
| | **New Customers** | First completed order falls in the period; Pre-2023 customers excluded (their history is cut off) |
| | **Returning Customers** | Customers − New Customers |
| | **New Customer %**, **Orders per Customer** | Ratios |
| | **Repeat Customer Rate %** | Share of the period's customers with 2+ orders in that period |
| Retention & Churn | **Active Customers (12M)** | Completed order in the 365 days up to the period end |
| | **Active Customers (Prior 12M)** | Active in the 365 days before that |
| | **Churned Customers (12M)** | Active in the prior 12M, **no** order in the last 12M |
| | **Churn Rate % (12M)** | Churned ÷ Active (Prior 12M) |
| Cohorts | **Cohort Size** | Customers whose first completed order was in the cohort month |
| | **Retained Customers** | Cohort customers ordering in month *N* after the cohort month |
| | **Retention %** | Retained ÷ Cohort Size |
| Helpers (hidden) | **Data End Date** | Last order date; stops rolling windows running past the data |

Plus a small disconnected table **`Cohort Offset`** (`Month Offset` = 0…44) that gives the cohort matrix its "months since first order" columns.

### DAX patterns worth knowing (interview material)
- **`New Customers`** filters a dimension *attribute* (`FIRST_ORDER_DATE`) using the visible date range, so it respects every other slicer (region, channel…) because the count still runs over the fact table.
- **Rolling 12-month windows** use `DATESBETWEEN` on the marked date table, capped with `MIN(MAX(date), [Data End Date])`, so "2026" doesn't mean "up to 31 Dec 2026" when data stops on 30 Sep.
- **Churn** is a set difference: `EXCEPT(prior-window customers, current-window customers)`.
- **Cohort matrix**: a disconnected offset table + `EDATE(cohort month, offset)` + `REMOVEFILTERS(dim_date)`, the standard cohort-analysis pattern.

## Step 1: Open the project
1. Close Power BI Desktop if it has the project open. **Don't save**: Desktop would overwrite the new measures with its in-memory copy.
2. Open `pbip/UK_Ecommerce.pbip`. The new folders appear under `_Measures`.
3. If Desktop reports a TMDL error on open, copy the message: it includes the file and line.

## Step 2: Load all history in Desktop (for development)
Desktop currently holds only September 2026 (RangeStart/RangeEnd). Cohorts and 12-month churn need every month:
**Transform data → Manage parameters → `RangeStart` = `01/01/2023 00:00:00`** → **Close & Apply** (1–3 minutes; all 7.1M sessions load).
This only affects your local file; the published model always uses its own partitions. The large local cache stays out of Git.

## Step 3: Build three check visuals (a scratch page)

**A. Customer KPIs by year**: Matrix, rows `dim_date[YEAR]`, values `Customers`, `New Customers`, `Returning Customers`, `Repeat Customer Rate %`, `Orders per Customer`.

**B. Churn as of the data end**: Card visuals: `Active Customers (12M)`, `Churned Customers (12M)`, `Churn Rate % (12M)` (no date filter: they cap at 30 Sep 2026 automatically).

**C. Cohort retention matrix**:
- Visual: **Matrix**
- Rows: `dim_customer[COHORT_LABEL]`
- Columns: `Cohort Offset[Month Offset]`
- Values: `Retention %`
- Conditional formatting → **Background color** on `Retention %` (white → dark blue).
- Turn off row and column subtotals (Format → Row/Column subtotals → Off).

Rows for "Pre-2023", "No completed order" and "Anonymous" stay blank and drop out automatically. Column 0 is always 100%.

## Step 4: Validate (expected values from Snowflake MARTS)

| Visual | Check | Expected |
|---|---|---|
| A | 2025 · Customers | **45,669** |
| A | 2025 · New Customers | **35,086** |
| A | 2025 · Returning Customers | **10,583** |
| A | 2025 · Repeat Customer Rate % | **34.8%** (15,889 ÷ 45,669) |
| A | 2025 · Orders per Customer | **1.58** (72,230 ÷ 45,669) |
| B | Active Customers (12M) | **51,517** |
| B | Churned Customers (12M) | **33,021** |
| B | Churn Rate % (12M) | **74.8%** (33,021 ÷ 44,134) |
| C | Cohort 2024-01 · Month 0 / 1 / 3 / 6 / 12 | **100% / 8.4% / 8.8% / 6.6% / 3.9%** (cohort of 2,431) |

**A ~75% annual churn isn't a bug.** Most e-commerce customers buy once; churn among *repeat* customers is far lower. That's a good insight to show on the report later (Day 11).

## Step 5: Commit
After checking, **save** in Desktop (writes the formats you may have tweaked, plus the visuals), then commit on a branch, PR and merge as usual. `git diff` on `_Measures.tmdl` shows each measure as readable DAX.
