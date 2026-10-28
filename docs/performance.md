# Performance: VertiPaq Analyzer and Performance Analyzer

## Method
1. **Model size:** DAX Studio → Advanced → View Metrics (VertiPaq Analyzer), exported as `.vpax` before and after.
2. **Report speed:** Power BI Desktop → Performance analyzer, refreshing visuals on all 5 pages, exported as JSON before and after. Figures below are medians per visual.

## Result

| | Before | After | Change |
|---|---|---|---|
| **Model size** | **756.1 MB** | **55.8 MB** | **−92.6%** |
| `fact_sessions` (7.1M rows) | 709.5 MB | 20.2 MB | −97% |
| `fact_order_line` (546k rows) | 34.1 MB | 22.0 MB | −35% |
| Row counts, measure results | | | unchanged (Net Revenue £19,415,548 · Orders 233,799 · Sessions 7,131,889) |
| Slowest query (Churn Rate % card) | ~190 ms | ~210 ms | no change (run-to-run noise) |
| Total query time, Web Funnel page | 136 ms | 88 ms | −35% |
| **Full model refresh in the service** (first refresh after publish) | **2 min 13 s** | **1 min 4 s** | **−52%** |

## Diagnosis
VertiPaq Analyzer showed **three columns using 93% of the model**:

| Column | Size before | Why so large | Used? |
|---|---|---|---|
| `fact_sessions[SESSION_START_TS]` | 380 MB | Unique to the second on 7.1M rows: the dictionary can't compress | Only by the incremental-refresh filter |
| `fact_sessions[SESSION_ID]` | 311 MB | Unique text per row | No: `Sessions` = `COUNTROWS` |
| `fact_order_line[ORDER_TS]` | 13 MB | Unique timestamps | Only by the incremental-refresh filter |

VertiPaq stores each **distinct** value once, so cost follows **cardinality**, not row count. A 3-value `DEVICE` column on the same 7.1M rows costs almost nothing.

Query times were already low (every visual's query under ~200 ms; most of each visual's time is rendering). DAX rewrites would have gained little; the problem was memory.

## Fix
In `fact_sessions` and `fact_order_line`, the Power Query steps now:

1. **Filter** on the timestamp with `RangeStart`/`RangeEnd`. Incremental refresh still partitions on it.
2. **Then remove** the unused columns (`Table.RemoveColumns`).

Both steps fold to SQL against the Lakehouse endpoint, so the columns are never transferred. The same change is in each table's `refreshPolicy.sourceExpression`, so service partitions match. `LOADED_AT` is kept: the policy's change detection (`pollingExpression`) reads it.

## Why it matters
- **Memory:** an Import model must fit in capacity memory. Pro has a 1 GB per-model limit, and refresh needs room for a second copy while it runs. At 756 MB the model was close to that limit, before any growth.
- **Refresh:** less data to transfer and compress on every refresh.
- **Scale:** sessions grow fastest. At the old rate, each extra year of sessions would have added roughly 175 MB; now it adds roughly 5 MB.

## Rule of thumb
Before tuning DAX, check VertiPaq Analyzer. Remove what the report doesn't use, especially **IDs, GUIDs and to-the-second timestamps on fact tables**. If time of day is needed, split it into a date key plus an hour column instead.
