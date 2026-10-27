# Security and refresh: dynamic RLS, publishing, daily pipeline

## Dynamic row-level security

Regional managers see only their region. Access is controlled by **data**, not by roles: adding a manager or changing their regions is a row in Snowflake. No model change and no republish are needed.

```
Snowflake MARTS.security_user_region  (user_email → region, 'All' = everything)
   ▼ Dataflow → Lakehouse → model table SECURITY_USER_REGION (hidden, no relationships)
Role 'Regional Manager'  ── USERPRINCIPALNAME() looks up the viewer's regions
   ├─ dim_geography  : delivery / visit region   → orders, sessions, returns
   ├─ dim_customer   : customer's home region (+ the anonymous -1 customer)
   └─ Customer RFM   : customer's home region (calculated table, needs its own rule)
```

| Object | Where |
|---|---|
| Security table | `snowflake/11_security.sql` |
| Model table | `tables/SECURITY_USER_REGION.tmdl` |
| Role | `roles/Regional Manager.tmdl` |
| Returns → region | `fact_returns[GEOGRAPHY_KEY]` = `LOOKUPVALUE` from the order line, related to `dim_geography` |

### Rules and why
- **One row per user per region.** A manager can cover several regions (the north manager has North East and North West).
- **`All`** is the admin keyword. Admins see everything without being given 12 rows.
- **Unknown email = sees nothing.** If the lookup finds no rows, every filter returns FALSE. The model fails closed.
- **Three filtered tables, not one.** Cohort sizes count `dim_customer` rows, and `Customer RFM` is a calculated table, so neither is reached by the `dim_geography` filter. Without their own rules, a regional manager's retention % and RFM segments would be national.
- **Filters combine with AND.** A manager sees orders delivered to their region **by customers who live there** (or anonymous ones). About 5% of order lines are delivered to a different region from the customer's home. Those belong to the home region's manager, so a London manager's revenue is slightly below "London" in an unsecured view.
- **Not secured, on purpose:** marketing spend, products, channels and the calendar. Budgets and the catalogue are national.

### Test results
Checked in Desktop (**View as**) and in the service, signing in as each test user. The expected values come from Snowflake MARTS.

| User | Net Revenue | Orders | Sessions | Result |
|---|---|---|---|---|
| london.manager@… | £2,829,707 | 35,513 | 1,080,184 | ✅ London only |
| scotland.manager@… | £1,525,431 | 18,198 | 569,947 | ✅ Scotland only |
| north.manager@… | North East + North West | | | ✅ two regions |
| ahsan@… (`All`) | £19,415,548 | 233,799 | 7,131,889 | ✅ everything |

**Lesson learned:** the first service test showed blank visuals for London, because the Snowflake table still held placeholder emails. Blank (not an error) is the expected symptom of a UPN mismatch, and a change to the security table only takes effect after **Snowflake → dataflow → model refresh**.

## Publishing

1. **Publish → Replace** into the `UK Ecommerce Analytics` workspace. This keeps the model's ID, connection mapping and role members.
2. Semantic model **Settings → Gateway and cloud connections**: map the Lakehouse SQL endpoint to the shareable cloud connection **Lakehouse lh_uk_ecom (OAuth)**. All 12 tables share one source, so one mapping covers them.
3. **Refresh now.** A publish replaces the incremental-refresh partitions, so the first refresh after a publish is a full rebuild.
4. Model **⋯ → Security**: add the managers to **Regional Manager**. Workspace **Manage access**: add them as **Viewer**.
   - RLS applies only to Viewers. Admin, Member and Contributor roles bypass it.
   - Viewers need no Lakehouse or Snowflake access (Import mode). Refresh runs under the connection's credential.

## Daily pipeline: `pl_uk_ecom_daily`

```
06:00 daily  ──▶  Dataflow df_uk_ecom_marts  ──on success──▶  Semantic model refresh (wait on completion)
```

- **Why a pipeline:** the model must never refresh before the Lakehouse has new data. Two independent schedules can overlap on a slow day and silently publish stale numbers. Here the model refresh only starts after the dataflow **succeeds**. If anything fails, the report keeps yesterday's complete data.
- The separate schedules on the dataflow and the model are **off**. The pipeline is the only trigger.
- **Each run:**
  - The dataflow re-pulls only the monthly buckets whose `loaded_at` changed.
  - The model refreshes only the last 3 months of partitions.
  - The security table refreshes in the same run, so a manager added in Snowflake has access the next morning.
