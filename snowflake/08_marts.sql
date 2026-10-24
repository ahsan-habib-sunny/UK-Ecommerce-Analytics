/* =====================================================================
   08_marts.sql: MARTS star schema, the only layer Power BI reads
   Run as ECOM_DEVELOPER. All views: no data is copied, and every query
   sees the latest RAW → STAGING data.

   Conventions (docs/data_model.md):
   - Keys are the source IDs renamed *_key; dates are YYYYMMDD integers.
   - Every dimension has a -1 "Unknown" row; facts never hold NULL keys.
   - Money is GBP; net_revenue is after discount and EXCLUDING VAT.
   ===================================================================== */

USE ROLE ECOM_DEVELOPER;
USE WAREHOUSE ECOM_TRANSFORM_WH;
USE SCHEMA UK_ECOM.MARTS;


/* =====================================================================
   INTERMEDIATE: order attribution (lives in STAGING, so Power BI can't see it)
   Rule: last NON-DIRECT click within 30 days. Candidates are the session the
   order was placed in, plus the customer's earlier logged-in sessions in the
   30 days before. The latest non-Direct one wins; if every candidate was
   Direct, the order is Direct. Marketplace orders have no sessions.
   ===================================================================== */
CREATE OR REPLACE VIEW UK_ECOM.STAGING.int_order_attribution AS
WITH candidates AS (
    SELECT o.order_id, s.session_start_ts, s.channel, s.campaign_code
    FROM UK_ECOM.STAGING.stg_orders o
    JOIN UK_ECOM.STAGING.stg_sessions s ON s.session_id = o.session_id
    UNION ALL
    SELECT o.order_id, s.session_start_ts, s.channel, s.campaign_code
    FROM UK_ECOM.STAGING.stg_orders o
    JOIN UK_ECOM.STAGING.stg_sessions s
      ON  s.customer_id = o.customer_id
      AND s.session_start_ts BETWEEN DATEADD(day, -30, o.order_ts) AND o.order_ts
      AND s.channel <> 'Direct'
)
SELECT
    o.order_id,
    COALESCE(c.channel, IFF(o.sales_channel = 'marketplace', 'Marketplace', 'Direct')) AS channel,
    c.campaign_code
FROM UK_ECOM.STAGING.stg_orders o
LEFT JOIN candidates c ON c.order_id = o.order_id
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY o.order_id
    ORDER BY IFF(c.channel = 'Direct', 1, 0), c.session_start_ts DESC NULLS LAST   -- non-direct first, then most recent
) = 1;


/* =====================================================================
   DIMENSIONS
   ===================================================================== */

-- dim_date: one row per day, 2023-01-01 → 2026-12-31 (whole years, as Power BI expects)
CREATE OR REPLACE VIEW dim_date AS
WITH days AS (
    SELECT DATEADD(day, ROW_NUMBER() OVER (ORDER BY SEQ4()) - 1, '2023-01-01'::DATE) AS d
    FROM TABLE(GENERATOR(ROWCOUNT => 1461))
),
bank_holidays AS (   -- England & Wales
    SELECT column1::DATE AS d FROM VALUES
    ('2023-01-02'),('2023-04-07'),('2023-04-10'),('2023-05-01'),('2023-05-08'),('2023-05-29'),('2023-08-28'),('2023-12-25'),('2023-12-26'),
    ('2024-01-01'),('2024-03-29'),('2024-04-01'),('2024-05-06'),('2024-05-27'),('2024-08-26'),('2024-12-25'),('2024-12-26'),
    ('2025-01-01'),('2025-04-18'),('2025-04-21'),('2025-05-05'),('2025-05-26'),('2025-08-25'),('2025-12-25'),('2025-12-26'),
    ('2026-01-01'),('2026-04-03'),('2026-04-06'),('2026-05-04'),('2026-05-25'),('2026-08-31'),('2026-12-25'),('2026-12-28')
)
SELECT
    TO_NUMBER(TO_CHAR(days.d, 'YYYYMMDD'))           AS date_key,
    days.d                                            AS calendar_date,
    DAYOFWEEKISO(days.d)                              AS day_of_week,          -- 1 = Monday
    DECODE(DAYOFWEEKISO(days.d), 1, 'Monday', 2, 'Tuesday', 3, 'Wednesday', 4, 'Thursday',
                                 5, 'Friday', 6, 'Saturday', 7, 'Sunday')    AS day_name,
    DAYOFWEEKISO(days.d) IN (6, 7)                    AS is_weekend,
    DATEADD(day, 1 - DAYOFWEEKISO(days.d), days.d)    AS week_start_date,      -- Monday
    DATE_TRUNC(month, days.d)                         AS month_start_date,
    TO_CHAR(days.d, 'MMMM')                           AS month_name,
    TO_CHAR(days.d, 'MON')                            AS month_short,
    MONTH(days.d)                                     AS month_number,
    TO_CHAR(days.d, 'YYYY-MM')                        AS year_month,
    YEAR(days.d) * 100 + MONTH(days.d)                AS year_month_sort,
    QUARTER(days.d)                                   AS quarter,
    YEAR(days.d)                                      AS year,
    MOD(MONTH(days.d) + 8, 12) + 1                    AS fiscal_month_number,  -- April = 1
    'Q' || CEIL(fiscal_month_number / 3)              AS fiscal_quarter,
    'FY' || (YEAR(days.d) + IFF(MONTH(days.d) >= 4, 1, 0)) AS fiscal_year,     -- FY2025 = Apr 2024 – Mar 2025
    bh.d IS NOT NULL                                  AS is_uk_bank_holiday
FROM days
LEFT JOIN bank_holidays bh ON bh.d = days.d;


-- dim_geography: postcode area → region → country (the RLS dimension)
CREATE OR REPLACE VIEW dim_geography AS
SELECT ROW_NUMBER() OVER (ORDER BY postcode_area) AS geography_key,   -- stable: static reference list
       postcode_area, area_name, region, country
FROM UK_ECOM.STAGING.stg_postcode_areas
UNION ALL
SELECT -1, 'N/A', 'Unknown', 'Unknown', 'Unknown';


-- dim_channel: fixed list of marketing channels
CREATE OR REPLACE VIEW dim_channel AS
SELECT column1 AS channel_key, column2 AS channel_name, column3 AS channel_group, column4 AS is_paid
FROM VALUES
    (1, 'Organic Search', 'Earned',      FALSE),
    (2, 'Paid Search',    'Paid',        TRUE),
    (3, 'Paid Social',    'Paid',        TRUE),
    (4, 'Email',          'Owned',       FALSE),
    (5, 'Affiliate',      'Paid',        TRUE),
    (6, 'Display',        'Paid',        TRUE),
    (7, 'Referral',       'Earned',      FALSE),
    (8, 'Direct',         'Direct',      FALSE),
    (9, 'Marketplace',    'Marketplace', FALSE),
    (-1, 'Unknown',       'Unknown',     FALSE);


-- dim_campaign
CREATE OR REPLACE VIEW dim_campaign AS
SELECT campaign_id AS campaign_key, campaign_code, campaign_name, campaign_type, start_date, end_date, discount_pct
FROM UK_ECOM.STAGING.stg_campaigns
UNION ALL
SELECT -1, 'NONE', 'No campaign', 'None', NULL, NULL, 0;


-- dim_return_reason: is_controllable = the business could have prevented it
CREATE OR REPLACE VIEW dim_return_reason AS
SELECT column1 AS return_reason_key, column2 AS reason_code, column3 AS reason_description, column4 AS is_controllable
FROM VALUES
    (1, 'SIZE',         'Wrong size or fit',  FALSE),
    (2, 'FAULTY',       'Faulty or damaged',  TRUE),
    (3, 'NOT_AS_DESC',  'Not as described',   TRUE),
    (4, 'CHANGED_MIND', 'Changed mind',       FALSE),
    (5, 'LATE',         'Arrived late',       TRUE),
    (-1, 'UNKNOWN',     'Unknown',            FALSE);


-- dim_product
CREATE OR REPLACE VIEW dim_product AS
SELECT
    product_id AS product_key, sku, product_name, category, subcategory, brand,
    list_price, unit_cost, vat_rate,
    CASE WHEN list_price < 20  THEN 'Under £20'
         WHEN list_price < 50  THEN '£20–49'
         WHEN list_price < 100 THEN '£50–99'
         ELSE '£100+' END      AS price_band,
    launched_on, is_active
FROM UK_ECOM.STAGING.stg_products
UNION ALL
SELECT -1, 'N/A', 'Unknown product', 'Unknown', 'Unknown', 'Unknown', NULL, NULL, NULL, 'Unknown', NULL, FALSE;


-- dim_customer: cohort and acquisition channel come from the first COMPLETED order
CREATE OR REPLACE VIEW dim_customer AS
WITH first_order AS (
    SELECT o.customer_id, o.order_ts AS first_order_ts, a.channel AS first_order_channel
    FROM UK_ECOM.STAGING.stg_orders o
    JOIN UK_ECOM.STAGING.int_order_attribution a ON a.order_id = o.order_id
    WHERE NOT o.is_cancelled
    QUALIFY ROW_NUMBER() OVER (PARTITION BY o.customer_id ORDER BY o.order_ts, o.order_id) = 1
)
SELECT
    c.customer_id                                   AS customer_key,
    c.first_name || ' ' || c.last_name              AS customer_name,     -- email stays out of the model (PII)
    COALESCE(g.geography_key, -1)                   AS geography_key,
    c.registered_at::DATE                           AS registered_date,
    f.first_order_ts::DATE                          AS first_order_date,
    -- Registered before the data starts = earlier orders exist that we can't see (history cut off)
    c.registered_at < '2023-01-01'                  AS is_pre_2023,
    IFF(is_pre_2023, NULL, DATE_TRUNC(month, f.first_order_ts)::DATE) AS cohort_month,
    CASE WHEN is_pre_2023              THEN 'Pre-2023'
         WHEN f.first_order_ts IS NULL THEN 'No completed order'
         ELSE TO_CHAR(f.first_order_ts, 'YYYY-MM') END                 AS cohort_label,
    CASE WHEN is_pre_2023 THEN 'Unknown (Pre-2023)'
         ELSE COALESCE(f.first_order_channel, 'None') END              AS acquisition_channel,
    CASE WHEN c.date_of_birth IS NULL THEN 'Unknown'
         -- age on the data end date, so bands don't shift every time the view runs
         WHEN DATEDIFF(day, c.date_of_birth, '2026-09-30') / 365.25 < 25 THEN '18–24'
         WHEN DATEDIFF(day, c.date_of_birth, '2026-09-30') / 365.25 < 35 THEN '25–34'
         WHEN DATEDIFF(day, c.date_of_birth, '2026-09-30') / 365.25 < 45 THEN '35–44'
         WHEN DATEDIFF(day, c.date_of_birth, '2026-09-30') / 365.25 < 55 THEN '45–54'
         WHEN DATEDIFF(day, c.date_of_birth, '2026-09-30') / 365.25 < 65 THEN '55–64'
         ELSE '65+' END                                                AS age_band,
    c.marketing_opt_in
FROM UK_ECOM.STAGING.stg_customers c
LEFT JOIN first_order f   ON f.customer_id   = c.customer_id
LEFT JOIN dim_geography g ON g.postcode_area = c.postcode_area
UNION ALL
SELECT -1, 'Anonymous', -1, NULL, NULL, FALSE, NULL, 'Anonymous', 'Unknown', 'Unknown', FALSE;


/* =====================================================================
   FACTS
   ===================================================================== */

-- fact_order_line: one row per product line on an order
CREATE OR REPLACE VIEW fact_order_line AS
WITH lines AS (
    SELECT
        l.order_line_id, l.order_id, l.quantity, l.unit_price, l.discount_amount, l.unit_cost, l._loaded_at,
        o.order_ts, o.order_date, o.customer_id, o.sales_channel, o.is_cancelled, o.shipping_fee,
        o.delivery_postcode_area, a.channel, a.campaign_code,
        p.product_id                         AS known_product_id,          -- NULL = orphan line
        COALESCE(p.vat_rate, 0.20)           AS vat_rate,                  -- unknown product: assume standard rate
        (l.quantity * l.unit_price - l.discount_amount) / (1 + COALESCE(p.vat_rate, 0.20)) AS net
    FROM UK_ECOM.STAGING.stg_order_lines l
    JOIN UK_ECOM.STAGING.stg_orders o            ON o.order_id   = l.order_id
    JOIN UK_ECOM.STAGING.int_order_attribution a ON a.order_id   = l.order_id
    LEFT JOIN UK_ECOM.STAGING.stg_products p     ON p.product_id = l.product_id
)
SELECT
    l.order_line_id                                  AS order_line_key,
    l.order_id,                                                         -- degenerate dimension
    TO_NUMBER(TO_CHAR(l.order_date, 'YYYYMMDD'))     AS order_date_key,
    l.order_ts,                                                         -- incremental refresh: filter column
    l._loaded_at::TIMESTAMP_NTZ                      AS loaded_at,         -- incremental refresh: change-detection column
    l.customer_id                                    AS customer_key,
    COALESCE(l.known_product_id, -1)                 AS product_key,
    COALESCE(g.geography_key, -1)                    AS geography_key,
    COALESCE(ch.channel_key, -1)                     AS channel_key,
    COALESCE(cp.campaign_key, -1)                    AS campaign_key,
    l.sales_channel,
    l.is_cancelled::INT                              AS is_cancelled,
    l.quantity,
    ROUND(l.quantity * l.unit_price, 2)              AS gross_sales,       -- inc. VAT, before discount
    l.discount_amount,
    ROUND(l.net, 2)                                  AS net_revenue,       -- after discount, ex. VAT
    ROUND(l.quantity * l.unit_price - l.discount_amount - l.net, 2) AS vat_amount,
    ROUND(l.quantity * l.unit_cost, 2)               AS cogs,
    ROUND(l.net - l.quantity * l.unit_cost, 2)       AS gross_margin,
    -- Order shipping (ex. VAT) shared across lines by their share of order net revenue
    ROUND(l.shipping_fee / 1.2 * DIV0(l.net, SUM(l.net) OVER (PARTITION BY l.order_id)), 2) AS shipping_allocated
FROM lines l
LEFT JOIN dim_geography g ON g.postcode_area = l.delivery_postcode_area
LEFT JOIN dim_channel  ch ON ch.channel_name = l.channel
LEFT JOIN dim_campaign cp ON cp.campaign_code = l.campaign_code;


-- fact_returns: one row per returned order line
CREATE OR REPLACE VIEW fact_returns AS
SELECT
    r.return_id                                      AS return_key,
    r.order_line_id                                  AS order_line_key,    -- drill-through to the sale
    TO_NUMBER(TO_CHAR(r.return_date, 'YYYYMMDD'))    AS return_date_key,
    TO_NUMBER(TO_CHAR(o.order_date,  'YYYYMMDD'))    AS order_date_key,    -- return rate is by ORDER date
    r.return_date,                                                      -- for incremental refresh
    o.customer_id                                    AS customer_key,
    COALESCE(p.product_id, -1)                       AS product_key,
    COALESCE(rr.return_reason_key, -1)               AS return_reason_key,
    r.quantity_returned,
    ROUND(r.refund_amount / (1 + COALESCE(p.vat_rate, 0.20)), 2) AS refund_amount   -- ex. VAT
FROM UK_ECOM.STAGING.stg_returns r
JOIN UK_ECOM.STAGING.stg_order_lines l   ON l.order_line_id = r.order_line_id
JOIN UK_ECOM.STAGING.stg_orders o        ON o.order_id      = l.order_id
LEFT JOIN UK_ECOM.STAGING.stg_products p ON p.product_id    = l.product_id
LEFT JOIN dim_return_reason rr           ON rr.reason_code  = r.reason_code;


-- fact_sessions: one row per website/app visit (the biggest table, ~7M rows)
CREATE OR REPLACE VIEW fact_sessions AS
SELECT
    s.session_id,
    TO_NUMBER(TO_CHAR(s.session_date, 'YYYYMMDD'))   AS session_date_key,
    s.session_start_ts,                                                 -- incremental refresh: filter column
    s._loaded_at::TIMESTAMP_NTZ                      AS loaded_at,         -- incremental refresh: change-detection column
    COALESCE(s.customer_id, -1)                      AS customer_key,      -- -1 = anonymous
    COALESCE(ch.channel_key, -1)                     AS channel_key,
    COALESCE(cp.campaign_key, -1)                    AS campaign_key,
    COALESCE(g.geography_key, -1)                    AS geography_key,
    s.device,
    s.landing_page_type,
    s.pageviews,
    s.added_to_basket::INT                           AS added_to_basket,   -- 0/1 sums easily in DAX
    s.converted::INT                                 AS converted
FROM UK_ECOM.STAGING.stg_sessions s
LEFT JOIN dim_channel  ch ON ch.channel_name  = s.channel
LEFT JOIN dim_campaign cp ON cp.campaign_code = s.campaign_code
LEFT JOIN dim_geography g ON g.postcode_area  = s.postcode_area;


-- fact_marketing_spend: one row per day × channel × campaign
CREATE OR REPLACE VIEW fact_marketing_spend AS
SELECT
    TO_NUMBER(TO_CHAR(m.spend_date, 'YYYYMMDD'))     AS spend_date_key,
    m.spend_date,
    COALESCE(cp.campaign_key, -1)                    AS campaign_key,      -- -1 = always-on spend
    COALESCE(ch.channel_key, -1)                     AS channel_key,
    m.spend,
    m.impressions,
    m.clicks
FROM UK_ECOM.STAGING.stg_marketing_spend m
LEFT JOIN dim_channel  ch ON ch.channel_name  = m.channel
LEFT JOIN dim_campaign cp ON cp.campaign_code = m.campaign_code;


SHOW VIEWS IN SCHEMA UK_ECOM.MARTS;
