# Power BI semantic model: Lakehouse → Import model with incremental refresh, saved as PBIP

## Design

```
lh_uk_ecom (SQL analytics endpoint)
   │  Import mode
   ▼
Semantic model  UK_Ecommerce
   ├─ star schema: 4 facts, 7 dimensions, single-direction 1:* relationships
   ├─ dim_date marked as the date table (auto date/time off)
   ├─ incremental refresh on fact_order_line and fact_sessions (RangeStart / RangeEnd)
   └─ saved as PBIP (TMDL text files) in pbip/ → every model change is a readable Git diff
```

**Why Import, not Direct Lake?** The brief asks for Import with the model's own incremental refresh, the most widely used pattern in industry and an interview staple. Direct Lake (reading the Lakehouse Delta files with no import) is the Fabric-native alternative, and a good "what would you do differently" talking point.

**Two layers of incremental refresh.** Dataflow Gen2 refreshes Snowflake → Lakehouse incrementally (Day 7). The semantic model refreshes Lakehouse → model incrementally, so each layer only moves recent data.

---

## Step 0: Desktop settings (before loading anything)
Power BI Desktop (latest version) → **File → Options and settings → Options**:
- **Current file → Data Load:** untick **Autodetect new relationships after data is loaded** (we create them by hand; auto-detect guesses wrong on `*_key` columns). Untick **Auto date/time** (we have `dim_date`).
- **Global → Preview features:** if listed, tick **Power BI Project (.pbip) save option** and **Store semantic model using TMDL format** (both are on by default in recent versions).

## Step 1: Connect to the Lakehouse (Import)
1. **Home → OneLake catalog** (or **Get data → Lakehouses**) → select `lh_uk_ecom`.
2. Click the arrow next to **Connect** → **Connect to SQL endpoint**. (Plain *Connect* may create a Direct Lake model instead.)
3. Tick all 11 tables under `dbo` → **Transform data**. If asked for a connectivity mode, choose **Import**.

## Step 2: RangeStart / RangeEnd parameters
**Home → Manage parameters → New**, twice. The names are case-sensitive and must be exactly these:

| Name | Type | Suggested values | Current value |
|---|---|---|---|
| `RangeStart` | Date/Time | Any value | `01/09/2026 00:00:00` |
| `RangeEnd` | Date/Time | Any value | `01/10/2026 00:00:00` |

These only control what **Desktop** loads (one month, September 2026), which keeps the PBIP file small. After publishing, the service replaces them with each partition's own date range.

## Step 3: Filter the two big facts
For `dbo_fact_order_line`: column `order_ts` → filter arrow → **Date/Time filters → Custom filter**:
- **is after or equal to** → (parameter) `RangeStart`
- **And** · **is before** → (parameter) `RangeEnd`

The step's M should read:
```powerquery
= Table.SelectRows(dbo_fact_order_line, each [order_ts] >= RangeStart and [order_ts] < RangeEnd)
```
Do the same for `dbo_fact_sessions` on `session_start_ts`.

**Use `>=` on one side and `<` on the other.** Otherwise rows exactly on a partition boundary load twice.
Right-click the filter step → **View native query** should be clickable: the filter folds to SQL, so each partition only reads its own month.

Rename the queries to drop the `dbo_` prefix (e.g. `fact_order_line`), then **Close & Apply**.

## Step 4: Relationships (Model view)
Delete any relationship Desktop created by itself, then drag these. All are **Many-to-one (*:1), single direction, active** unless marked otherwise.

| From (many) | To (one) |
|---|---|
| fact_order_line[order_date_key] | dim_date[date_key] |
| fact_order_line[customer_key] | dim_customer[customer_key] |
| fact_order_line[product_key] | dim_product[product_key] |
| fact_order_line[geography_key] | dim_geography[geography_key] |
| fact_order_line[channel_key] | dim_channel[channel_key] |
| fact_order_line[campaign_key] | dim_campaign[campaign_key] |
| fact_returns[order_date_key] | dim_date[date_key] (**active**: return rate is by order date) |
| fact_returns[return_date_key] | dim_date[date_key] (**inactive**: use with `USERELATIONSHIP`) |
| fact_returns[customer_key] | dim_customer[customer_key] |
| fact_returns[product_key] | dim_product[product_key] |
| fact_returns[return_reason_key] | dim_return_reason[return_reason_key] |
| fact_sessions[session_date_key] | dim_date[date_key] |
| fact_sessions[customer_key] | dim_customer[customer_key] |
| fact_sessions[channel_key] | dim_channel[channel_key] |
| fact_sessions[campaign_key] | dim_campaign[campaign_key] |
| fact_sessions[geography_key] | dim_geography[geography_key] |
| fact_marketing_spend[spend_date_key] | dim_date[date_key] |
| fact_marketing_spend[campaign_key] | dim_campaign[campaign_key] |
| fact_marketing_spend[channel_key] | dim_channel[channel_key] |

**Not related on purpose:** `dim_customer[geography_key]` → `dim_geography`. Facts already reach geography by **delivery** area, so a second path through the customer's home area would make the model ambiguous. (Region RLS on Day 12 filters by delivery region.)

## Step 5: Model hygiene
- **Date table:** select `dim_date` → **Table tools → Mark as date table** → `calendar_date`.
- **Sort by column** (select the column → *Column tools → Sort by column*):
  `month_name` and `month_short` by `month_number` · `day_name` by `day_of_week` · `year_month` by `year_month_sort`.
- **Hide** (right-click → *Hide in report view*): every `*_key` column on facts, `loaded_at`, `order_ts`, `session_start_ts`, `return_date`, `spend_date`, `order_line_key`, `return_key`, `session_id`.
- **Summarization → Don't summarize:** `year`, `quarter`, `month_number`, `day_of_week`, `fiscal_month_number`, `year_month_sort`, `list_price`, `unit_cost`, `vat_rate`, `discount_pct`.
- **Data category:** `dim_geography[region]` → *State or Province*; `postcode_area` → *Postal code* (for maps later).

## Step 6: Base measures
**Home → Enter data** → name the table `_Measures` → **Load**. (The underscore keeps it at the top of the field list; delete its dummy column after adding the first measure.) Add these with **New measure**. Put them in a display folder named `Base`:

```dax
Net Revenue = CALCULATE ( SUM ( fact_order_line[net_revenue] ), fact_order_line[is_cancelled] = 0 )
Gross Margin = CALCULATE ( SUM ( fact_order_line[gross_margin] ), fact_order_line[is_cancelled] = 0 )
Margin % = DIVIDE ( [Gross Margin], [Net Revenue] )
Orders = CALCULATE ( DISTINCTCOUNT ( fact_order_line[order_id] ), fact_order_line[is_cancelled] = 0 )
Units Sold = CALCULATE ( SUM ( fact_order_line[quantity] ), fact_order_line[is_cancelled] = 0 )
AOV = DIVIDE ( [Net Revenue], [Orders] )
Units Returned = SUM ( fact_returns[quantity_returned] )
Return Rate % = DIVIDE ( [Units Returned], [Units Sold] )
Refunds = SUM ( fact_returns[refund_amount] )
Sessions = COUNTROWS ( fact_sessions )
Conversion Rate % = DIVIDE ( SUM ( fact_sessions[converted] ), [Sessions] )
Marketing Spend = SUM ( fact_marketing_spend[spend] )
```
Formats: currency measures → **£ Currency, 0 decimals** (AOV 2 decimals); `%` measures → **Percentage, 1 decimal** (conversion 2 decimals); counts → **Whole number** with thousands separator.

## Step 7: Incremental refresh policies
Right-click `fact_order_line` → **Incremental refresh**:
- **Incrementally refresh this table:** On
- **Archive data starting** `4` **Years** before refresh date
- **Incrementally refresh data starting** `3` **Months** before refresh date
- **Detect data changes:** ticked → column `loaded_at`
- **Only refresh complete days:** off
- **Apply**

Repeat for `fact_sessions` (same values, detect changes on `loaded_at`).

What this means: the service keeps 4 years of history in yearly/quarterly/monthly partitions, re-checks only the last 3 months on each refresh, and within those skips any month whose max `loaded_at` hasn't changed.

## Step 8: Save as PBIP (into the repo)
**File → Save as → Browse** → go to `…\UK-Ecommerce-Analytics\pbip\` → *Save as type* **Power BI project files (\*.pbip)** → name `UK_Ecommerce` → **Save**.

This creates `UK_Ecommerce.pbip`, `UK_Ecommerce.SemanticModel\` (tables, measures, relationships and the refresh policy as `.tmdl` text files) and `UK_Ecommerce.Report\`. The imported data (`.pbi\cache.abf`) and personal settings are already in `.gitignore`.

## Step 9: Validate in Desktop (September 2026 only)
Build a quick table: `dim_date[year_month]` + `[Net Revenue]`. With RangeStart/RangeEnd = September 2026, you should see a single month:

| Check | Expected |
|---|---|
| Net Revenue, 2026-09 | **£544,907** |
 
## Step 10: Publish and refresh in the service
1. **Home → Publish** → workspace **UK Ecommerce Analytics**.
2. **Map the Lakehouse to an explicit cloud connection** (required for Import refresh; *Data source credentials* will say "No data sources found", which is expected):
   semantic model → **⋯ → Settings → Gateway and cloud connections** → in the Lakehouse SQL endpoint row, **Maps to → Create a connection** → name `Lakehouse lh_uk_ecom (OAuth)`, authentication **OAuth 2.0** → sign in → **Create** → select it in **Maps to** → **Apply**.
   Without this, refresh fails with `Premium_ASWL_Error … uses a default data connection without explicit connection credentials`.
   While in Settings, confirm it's an **Import** model: you should see a **Refresh / Scheduled refresh** section, not a *Direct Lake* section.
3. In the workspace: semantic model `UK_Ecommerce` → **Refresh now**. The first refresh builds all partitions and loads 4 years. Note the duration (refresh history: **⋯ → Refresh history**).
4. **Refresh now** again. Only the last 3 months are checked, and unchanged months are skipped. Note the duration.
5. Check the full totals: workspace → semantic model → **Create report** (or *Explore this data*) → cards:

| Measure | Expected (all time) |
|---|---|
| Net Revenue | £19,415,548 |
| Gross Margin | £7,663,419 (Margin % 39.5%) |
| Orders | 233,799 |
| Units Sold | 620,743 |
| AOV | £83.04 |
| Units Returned | 69,138 (Return Rate % 11.1%) |
| Refunds | £2,144,256 |
| Sessions | 7,131,889 |
| Conversion Rate % | 2.87% |
| Marketing Spend | £5,519,662 |

(Reference values from Snowflake MARTS, computed 2026-10-24. If they match, every layer from RAW to the model agrees.)

## Results (2026-10-25)

| Refresh | Duration | What happened |
|---|---|---|
| First refresh | **2 min 13 s** | Partitions created; 4 years of both facts imported from the Lakehouse |
| Second refresh | **26 s** | Only the last 3 months re-checked; months with unchanged `loaded_at` skipped |

**≈5× faster**. All 10 validation measures matched the Snowflake MARTS totals exactly (Net Revenue £19,415,548, Sessions 7,131,889, …), so RAW → STAGING → MARTS → Lakehouse → model reconcile end to end.

## Troubleshooting
| Symptom | Fix |
|---|---|
| Incremental refresh option greyed out | Parameters must be named exactly `RangeStart` / `RangeEnd`, type **Date/Time**, and used in a filter on that table. |
| "Unable to confirm if the M query can be folded" warning | Check *View native query* on the filter step; remove steps after the filter that break folding. Type changes and renames are fine. |
| Totals in the service are too low | The archive window is too short (must cover 2023-01 onwards), or the first refresh is still running. |
| Rows duplicated at month boundaries | One filter side must be `<` (not `<=`). |
| `Premium_ASWL_Error`: "uses a default data connection without explicit connection credentials" | Step 10.2: create a cloud connection (OAuth 2.0) and map the source to it under *Gateway and cloud connections*. |
