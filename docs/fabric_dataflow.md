# Fabric: Snowflake MARTS → Dataflow Gen2 (incremental) → Lakehouse

## Design

```
Snowflake UK_ECOM.MARTS (11 views)
   │  connection: ECOM_BI_SVC, key-pair, warehouse ECOM_BI_WH (read-only)
   ▼
Dataflow Gen2  df_uk_ecom_marts
   ├─ 2 big facts → INCREMENTAL refresh (monthly buckets)
   └─ 9 dims + small facts → full refresh (Replace)
   ▼
Lakehouse  lh_uk_ecom  (Delta tables, same names as the views)
```

| Query | Rows | Refresh | Filter column | Change-detection column |
|---|---|---|---|---|
| fact_sessions | 7.1M | Incremental | `session_start_ts` | `loaded_at` |
| fact_order_line | 546k | Incremental | `order_ts` | `loaded_at` |
| fact_returns, fact_marketing_spend | 62k, 8k | Full | | |
| 7 dimensions | ≤151k | Full | | |

### Why these settings
- **Incremental only on the big facts.** Bucket overhead isn't worth it for small tables.
- **Separate filter and detection columns** (Microsoft's recommendation). `order_ts` decides *which month bucket* a row belongs to; `loaded_at` (when Snowflake loaded the row) decides *whether that bucket changed*. A re-load of one month changes `loaded_at` only in that month, so only that bucket is re-pulled.
- **Monthly buckets, 4 years back:** Oct 2022 → Oct 2026 = 49 buckets per query (limit 50); 2 queries = 98 for the dataflow (limit 150).
- **Lakehouse limits** ([docs](https://learn.microsoft.com/en-us/fabric/data-factory/dataflow-gen2-incremental-refresh)): at most 10 concurrent evaluations; fixed schema; update method `Replace`; incremental refresh must be on **before the first load** (an existing table can't be converted).

---

## Step 1: Workspace and Lakehouse
1. Go to app.powerbi.com → **Workspaces** → **+ New workspace**.
   - Name: `UK Ecommerce Analytics`
   - **Advanced** → License mode: **Fabric capacity** (or **Trial**) → pick your trial capacity → **Apply**.
2. In the workspace: **+ New item** → **Lakehouse** → name `lh_uk_ecom` → **Create**.
   If "Lakehouse schemas" is on (now the default), tables go in the **`dbo`** schema.

## Step 2: Dataflow and Snowflake connection
1. Back in the workspace: **+ New item** → **Dataflow Gen2** → name `df_uk_ecom_marts`.
2. **Get data** → search **Snowflake** → select it.
3. Connection settings:
   - **Server:** `eyasexz-pe64823.snowflakecomputing.com` (**all lowercase**: uppercase server names are a known Fabric issue)
   - **Warehouse:** `ECOM_BI_WH`
   - **Connection name:** `Snowflake UK_ECOM (ECOM_BI_SVC)`
   - **Authentication kind:** **Key-Pair**
   - **Username:** `ECOM_BI_SVC`
   - **Private key:** **Upload** the file `C:\Users\ahsan\.snowflake\ecom_bi_key.p8` (paste `C:\Users\ahsan\.snowflake` into the file picker's address bar; set the file-type filter to *All files* if it's hidden)
   - **Passphrase:** leave empty (the key isn't encrypted)
   - **Next**
4. In the navigator, expand **UK_ECOM** → **MARTS** → tick **all 11 views** → **Create**.

## Step 3: Set column types (all queries)
Snowflake numbers arrive as generic decimals. For each query, set types (click the icon in the column header):
- `*_key`, `*_date_key`, `quantity`, `quantity_returned`, `pageviews`, `added_to_basket`, `converted`, `is_cancelled`, `impressions`, `clicks`, `day_of_week`, `month_number`, `year`, `quarter`, `fiscal_month_number`, `year_month_sort` → **Whole number**
- Money (`gross_sales`, `discount_amount`, `net_revenue`, `vat_amount`, `cogs`, `gross_margin`, `shipping_allocated`, `refund_amount`, `spend`, `list_price`, `unit_cost`, `vat_rate`, `discount_pct`) → **Decimal number**
- `order_ts`, `session_start_ts`, `loaded_at` → **Date/Time**
- `return_date`, `spend_date`, `calendar_date`, `*_date` → **Date**

Every step should keep the **folding indicator green** (the small icon next to each applied step). Changing types folds to Snowflake.

## Step 4: Destinations: full-refresh queries (the 9 small ones)
For each of: `dim_date`, `dim_customer`, `dim_product`, `dim_geography`, `dim_channel`, `dim_campaign`, `dim_return_reason`, `fact_returns`, `fact_marketing_spend`:
1. Select the query → bottom right **Data destination** → **+** → **Lakehouse**.
2. Choose `UK Ecommerce Analytics` → `lh_uk_ecom` → schema **`dbo`** → **New table**, name = query name → **Next**.
   (Never pick anything named *staging*: that's Fabric's internal dataflow staging area.)
3. Turn **off** "Use automatic settings" → Update method **Replace** → Schema options **Fixed schema** → **Save settings**.

## Step 5: The two incremental queries
Do this for `fact_order_line`, then for `fact_sessions`. **Configure incremental refresh first, then the destination, then publish.**

1. Right-click the query → **Incremental refresh**:
   - **Choose a DateTime column to filter by:** `order_ts` (for sessions: `session_start_ts`)
   - **Extract data from the past:** `4` **Years**
   - **Bucket size:** **Month**
   - **Only extract new data when the maximum value in this column changes:** `loaded_at`
   - **Only extract data for concluded periods:** off
   - Advanced: **Require incremental refresh query to fully fold:** **on**
   - **OK**. The query icon now shows a small blue triangle.
2. Data destination → Lakehouse → `lh_uk_ecom` → **`dbo`** → **New table** (same name) → automatic settings **off** → **Replace** → **Fixed schema** → **Save settings**.

## Step 6: Concurrency, then publish
1. **Home → Options** (or the gear icon) → **Scale** → set **Maximum number of parallel query evaluations** to **10** (the Lakehouse limit) → **OK**.
2. **Publish** (or **Save & run**). The first refresh starts automatically and loads all 49 monthly buckets per fact.

## Step 7: Check the results
1. Workspace → `df_uk_ecom_marts` → **⋯** → **Recent runs** (refresh history). Note the **duration** of the first refresh.
2. Open `lh_uk_ecom` → switch to **SQL analytics endpoint** (top right) → **New SQL query** → run:

```sql
SELECT 'fact_sessions' AS t, COUNT(*) AS n FROM fact_sessions
UNION ALL SELECT 'fact_order_line', COUNT(*) FROM fact_order_line
UNION ALL SELECT 'fact_returns', COUNT(*) FROM fact_returns
UNION ALL SELECT 'fact_marketing_spend', COUNT(*) FROM fact_marketing_spend
UNION ALL SELECT 'dim_customer', COUNT(*) FROM dim_customer
UNION ALL SELECT 'dim_date', COUNT(*) FROM dim_date;
```
Expected: 7,131,889 · 546,025 · 61,619 · 8,235 · 151,102 · 1,461.

3. **Refresh the dataflow again** (nothing changed in Snowflake). It should be **much faster**: every bucket's max `loaded_at` is unchanged, so no fact data is pulled. Note this duration too.

Those two durations, first load against unchanged refresh, are the incremental-refresh evidence for the README and CV.

## Results (2026-10-24)

| Refresh | Duration | What happened |
|---|---|---|
| First load | **21 min** | All 49 monthly buckets × 2 facts pulled from Snowflake, plus 9 full tables |
| Second refresh, no source changes | **3 min** | Every bucket's max `loaded_at` unchanged → no fact data pulled; only the small tables reloaded |

**≈7× faster** refresh for 7.7M fact rows. The remaining 3 minutes is mostly the 9 full-refresh tables and dataflow start-up overhead.

## Troubleshooting
| Symptom | Likely cause / fix |
|---|---|
| "Invalid credentials" on the Snowflake connection | First check the **server name is all lowercase** (a [known issue](https://learn.microsoft.com/en-us/fabric/data-factory/connector-snowflake)); use *Create new connection* rather than the saved failed one. Then check Snowflake `LOGIN_HISTORY_BY_USER('ECOM_BI_SVC')` for the rejection reason. Also: | Upload `ecom_bi_key.p8` (not the loader's key); Username exactly `ECOM_BI_SVC`; in Snowflake, `DESC USER ECOM_BI_SVC` must show an `RSA_PUBLIC_KEY_FP`. |
| Can't see the MARTS views | The connection's role defaults to `ECOM_REPORTER`; check `10_fabric_user.sql` ran fully. |
| "Incremental refresh is not supported when it uses a default destination" | Set the destination **per query** (Steps 4–5), not a dataflow-wide default. |
| Folding indicator turns red/yellow | Remove the last step that broke folding; type changes, column removal and renames fold. |
| `cannot convert the value "…" to type List` or `cannot convert Type to List` in `Apply_<QUERY>_Incremental_Over_Periods` | Seen on `fact_sessions` (2026-10-24). A stray column type in the query's steps. Fix that worked: delete the Lakehouse table and the query, re-add the view, set each column's type by hand (no *Detect data type*, no *Any* columns), configure incremental refresh, then the destination, then publish. |
| Error about overlapping data / converting a table | The Lakehouse table was first loaded without incremental refresh. Delete the table in the Lakehouse and refresh again. |
