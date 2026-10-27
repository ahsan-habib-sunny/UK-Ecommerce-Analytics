# CLAUDE.md: UK E-commerce Analytics

14-day portfolio project: **Python generator → Parquet → Snowflake (RAW → STAGING → MARTS) → Fabric Dataflow Gen2 (incremental) → Lakehouse → Import semantic model (incremental refresh) → Power BI report → App.**
Repo: github.com/ahsan-habib-sunny/UK-Ecommerce-Analytics · Windows · Git Bash + PowerShell.

## Working with this user
- **Give finished, working files.** No discovery homework, no "find it yourself", no asking them to send lists.
- **Claude builds the model and report**: write TMDL and PBIR directly. The user opens Desktop to check.
- **The user does all git commits, pushes and PRs** (learning Git is a goal). Give them the exact commands: branch → `git add .` → commit → push → PR → merge → `git switch main && git pull`.
- Explain new scripts briefly. Keep instructions as short numbered steps.
- Report style they like: light corporate look, big readable fonts (titles 15pt, labels 13pt, KPI 30pt), **all text black**, no subtitles, no "Unknown"/N/A members on visuals, data labels on for bar/column charts, business-friendly titles, no clutter.

## Hard rules
- **Power BI Desktop must be CLOSED (without saving) before editing anything under `pbip/`.** If Desktop is open, saving overwrites file edits. Check with `tasklist | grep -i PBIDesktop`.
- **`sealed/` is git-ignored and holds the hidden-story answer key** (story_spec.md, scenario.toml, hooks.py). Never show its contents to the user unless they ask for the Day 11+ story discovery. The generator reads story parameters from it.
- Never commit secrets: `.env`, `*.p8` and `data/` are ignored. Private keys live in `~/.snowflake/` (`ecom_loader_key.p8`, `ecom_bi_key.p8`).
- Validate every PBIR change: `python tools/validate_pbir.py pbip/UK_Ecommerce.Report`. It needs `jsonschema` and `referencing`, and must show 0 errors.

## Layout
| Path | What |
|---|---|
| `generator/` | Seeded synthetic data (`generate.py`, `ecomgen/*`, `params.toml`). Full run (seed 42) ≈ 8,143,461 rows in ~30s; `--scale 0.0125` ≈ 112k rows. Venv `.venv` at the repo root. |
| `loader/` | `make_keypair.py --name`, `load_to_snowflake.py` (idempotent PUT + COPY; `--reload`). Reads `.env`. |
| `snowflake/01…10_*.sql` | setup · RAW tables · loader user · RAW checks · profiling · staging views · DQ checks · marts · marts tests (31) · Fabric user |
| `docs/` | data_model, data_dictionary, fabric_dataflow, semantic_model, dax_customers, dax_advanced (expected validation values), report |
| `pbip/UK_Ecommerce.SemanticModel/definition/` | TMDL model. `tables/_Measures.tmdl` holds all measures in display folders. |
| `pbip/UK_Ecommerce.Report/` | PBIR report, 5 pages. Theme: `StaticResources/RegisteredResources/UKEcomLight.json` |
| `tools/` | `build_report.py` regenerates **all** report pages and the theme (run from the repo root; it overwrites manual Desktop edits to the pages). `validate_pbir.py`. `run_sql.py file.sql [--show]` and `test_views.py`: read-only Snowflake checks as ECOM_LOADER. |

## Snowflake
- Account `EYASEXZ-PE64823` (Azure UK South). DB `UK_ECOM`; schemas RAW, STAGING, MARTS.
- Roles: ECOM_DEVELOPER (the user, in the UI), ECOM_LOADER_ROLE (user ECOM_LOADER), ECOM_REPORTER (user ECOM_BI_SVC, used by Fabric). Service users authenticate with a key pair (TYPE=SERVICE).
- Warehouses: ECOM_TRANSFORM_WH and ECOM_BI_WH (XS, auto-suspend 60). Resource monitor ECOM_RM.
- Stage `STG_LANDING` (Parquet, USE_LOGICAL_TYPE). COPY uses MATCH_BY_COLUMN_NAME.
- RAW keeps `order_ts` and `registered_at` as VARCHAR (two formats; parsed in STAGING).
- **Views resolve unqualified names in the view's own schema.** Fully qualify cross-schema references (`UK_ECOM.MARTS.x`).
- MARTS:
  - Dims: dim_date (2023-01-01..2026-12-31, column `calendar_date`, fiscal year Apr–Mar), dim_geography, dim_channel, dim_campaign, dim_return_reason, dim_product, dim_customer.
  - Facts: fact_order_line and fact_sessions, which both have `loaded_at`; fact_returns; fact_marketing_spend.
  - `-1` = Unknown member. Date keys are YYYYMMDD. Attribution: last non-direct click, 30-day lookback.
- Data ends **30 Sep 2026**.

## Fabric
- Workspace "UK Ecommerce Analytics", Lakehouse `lh_uk_ecom` (schema **dbo**), Dataflow Gen2 `df_uk_ecom_marts`.
- Server name must be **lowercase**: `eyasexz-pe64823.snowflakecomputing.com`. Upload the key file; pasting isn't supported.
- Incremental refresh on the two big facts: monthly buckets, 4 years (49 buckets), filter `order_ts`/`session_start_ts`, change detection `loaded_at`. Destination: Replace, fixed schema.
- Refresh times: first load 21 min → incremental 3 min.

## Semantic model (TMDL)
- Import from the Lakehouse SQL endpoint. RangeStart/RangeEnd. IR policy: 4 years archive, 3 months refresh, detect on loaded_at.
- Service refresh needs the explicit cloud connection **"Lakehouse lh_uk_ecom (OAuth)"**; without it you get Premium_ASWL_Error. Refresh times: 2m13s → 26s.
- **Model column names are UPPERCASE** (e.g. `dim_geography[REGION]`).
- `discourageImplicitMeasures` is on (required by the calculation group), so visuals must use measures.
- Extra tables:
  - `Cohort Offset` (0..44, disconnected).
  - `Customer RFM` (calculated; related to fact_order_line and fact_returns on CUSTOMER_KEY).
  - `Time Intelligence` (calculation group; PY items capped at the data end).
  - Field parameters `Metric Selector` (5 metrics) and `Dimension Selector` (Region, Sales Channel, Price Band, Age Band).
- **Measures cannot reference a field parameter's display column** (composite-key limit; the visual goes blank). Use the `… Order` column instead, as `Sales Mix Title` does.
- Validation totals: Net Revenue £19,415,548 · Orders 233,799 · Sessions 7,131,889 · Active customers 12M 51,517. More values are in `docs/dax_*.md`.

## Report (PBIR) gotchas
- Visuals that use field parameters need `fieldParameters` in queryState.
- `accentBar` is not allowed on cards.
- Slicer defaults go in `objects.general.filter`.
- Top N uses a TopN filter on dim_product SKU.
- Matrix fit: `columnAdjustment: "growToFit"`.
- Unknown members are hidden with per-visual NOT filters.

## Status
- Days 1–11 are done and merged to main (PR #8 = Day 11 report). Tags: `v0.6-marts`.
- Day 12 RLS merged (PR #9):
  - `snowflake/11_security.sql` → `SECURITY_USER_REGION` (hidden, no relationships). Tenant domain: `ahsantheanalyst29.onmicrosoft.com`.
  - Role `Regional Manager` filters dim_geography, dim_customer (home region, keep -1) and Customer RFM.
  - `fact_returns[GEOGRAPHY_KEY]` is a LOOKUPVALUE calculated column with a relationship to dim_geography.
  - Expected values: London £2,829,707 / 35,513 orders / 1,080,184 sessions; Scotland £1,525,431 / 18,198 / 569,947.
- Day 12 part 2 done:
  - Published; model mapped to "Lakehouse lh_uk_ecom (OAuth)".
  - Test users london/scotland/north.manager@ahsantheanalyst29.onmicrosoft.com are workspace Viewers and members of the role, and were verified in the service.
  - Pipeline `pl_uk_ecom_daily` (dataflow → model refresh, daily 06:00) is built and has run (described in `docs/security_and_refresh.md`).
  - "Test as role" is missing in this tenant's UI; test by signing in as the user in InPrivate.
- Day 13 tuning:
  - Model 756.1 MB → 55.8 MB. SESSION_ID, SESSION_START_TS and ORDER_TS are removed after the IR filter step; LOADED_AT is kept for polling.
  - Query speed was already fine (slowest ~200 ms). Write-up: `docs/performance.md`.
  - Before/after `.vpax` and Performance Analyzer JSON files are in `data/` (git-ignored). Parsers: `tools/vpax_summary.py`, `tools/perf_summary.py`.
- **Next:**
  - Day 13: app, plus DAX Studio/VertiPaq tuning (before/after numbers).
  - Day 14: README, write-up, CV bullets, release tag.
- Update this section when a day is merged.
