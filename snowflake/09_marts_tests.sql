/* =====================================================================
   09_marts_tests.sql: automated tests for the star schema
   One row per test with PASS/FAIL. Re-run after any change to
   STAGING or MARTS: every row should say PASS.
   The view lives in STAGING, so Power BI users never see it. Because of that,
   MARTS objects must be fully qualified: inside a view, unqualified names
   resolve against the VIEW's schema (STAGING), not your current schema.
   ===================================================================== */

USE ROLE ECOM_DEVELOPER;
USE WAREHOUSE ECOM_TRANSFORM_WH;
USE SCHEMA UK_ECOM.MARTS;

CREATE OR REPLACE VIEW UK_ECOM.STAGING.marts_tests AS
WITH t AS (
    -- 1. Row counts: facts must keep every cleaned row (no rows lost or multiplied by joins)
    SELECT 'Row count' AS test_type, 'fact_order_line = stg_order_lines' AS test_name,
           (SELECT COUNT(*) FROM UK_ECOM.STAGING.stg_order_lines) AS expected,
           (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_order_line) AS actual
    UNION ALL SELECT 'Row count', 'fact_returns = stg_returns',
           (SELECT COUNT(*) FROM UK_ECOM.STAGING.stg_returns), (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_returns)
    UNION ALL SELECT 'Row count', 'fact_sessions = stg_sessions',
           (SELECT COUNT(*) FROM UK_ECOM.STAGING.stg_sessions), (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_sessions)
    UNION ALL SELECT 'Row count', 'fact_marketing_spend = stg_marketing_spend',
           (SELECT COUNT(*) FROM UK_ECOM.STAGING.stg_marketing_spend), (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_marketing_spend)
    UNION ALL SELECT 'Row count', 'dim_customer = stg_customers + 1 unknown row',
           (SELECT COUNT(*) + 1 FROM UK_ECOM.STAGING.stg_customers), (SELECT COUNT(*) FROM UK_ECOM.MARTS.dim_customer)

    -- 2. Unique keys: a duplicated dimension key would double-count in Power BI
    UNION ALL SELECT 'Unique key', 'fact_order_line.order_line_key', 0, (SELECT COUNT(*) - COUNT(DISTINCT order_line_key) FROM UK_ECOM.MARTS.fact_order_line)
    UNION ALL SELECT 'Unique key', 'dim_customer.customer_key',      0, (SELECT COUNT(*) - COUNT(DISTINCT customer_key) FROM UK_ECOM.MARTS.dim_customer)
    UNION ALL SELECT 'Unique key', 'dim_product.product_key',        0, (SELECT COUNT(*) - COUNT(DISTINCT product_key) FROM UK_ECOM.MARTS.dim_product)
    UNION ALL SELECT 'Unique key', 'dim_geography.geography_key',    0, (SELECT COUNT(*) - COUNT(DISTINCT geography_key) FROM UK_ECOM.MARTS.dim_geography)
    UNION ALL SELECT 'Unique key', 'dim_campaign.campaign_key',      0, (SELECT COUNT(*) - COUNT(DISTINCT campaign_key) FROM UK_ECOM.MARTS.dim_campaign)
    UNION ALL SELECT 'Unique key', 'dim_date.date_key',              0, (SELECT COUNT(*) - COUNT(DISTINCT date_key) FROM UK_ECOM.MARTS.dim_date)

    -- 3. Orphan keys: every fact key must exist in its dimension (NULLs count as orphans too)
    UNION ALL SELECT 'Orphan key', 'fact_order_line → dim_date',      0, (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_order_line f WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.MARTS.dim_date d      WHERE d.date_key      = f.order_date_key))
    UNION ALL SELECT 'Orphan key', 'fact_order_line → dim_customer',  0, (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_order_line f WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.MARTS.dim_customer d  WHERE d.customer_key  = f.customer_key))
    UNION ALL SELECT 'Orphan key', 'fact_order_line → dim_product',   0, (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_order_line f WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.MARTS.dim_product d   WHERE d.product_key   = f.product_key))
    UNION ALL SELECT 'Orphan key', 'fact_order_line → dim_geography', 0, (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_order_line f WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.MARTS.dim_geography d WHERE d.geography_key = f.geography_key))
    UNION ALL SELECT 'Orphan key', 'fact_order_line → dim_channel',   0, (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_order_line f WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.MARTS.dim_channel d   WHERE d.channel_key   = f.channel_key))
    UNION ALL SELECT 'Orphan key', 'fact_order_line → dim_campaign',  0, (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_order_line f WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.MARTS.dim_campaign d  WHERE d.campaign_key  = f.campaign_key))
    UNION ALL SELECT 'Orphan key', 'fact_returns → dim_date (return)', 0, (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_returns f WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.MARTS.dim_date d WHERE d.date_key = f.return_date_key))
    UNION ALL SELECT 'Orphan key', 'fact_returns → dim_product',      0, (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_returns f WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.MARTS.dim_product d WHERE d.product_key = f.product_key))
    UNION ALL SELECT 'Orphan key', 'fact_returns → dim_return_reason', 0, (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_returns f WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.MARTS.dim_return_reason d WHERE d.return_reason_key = f.return_reason_key))
    UNION ALL SELECT 'Orphan key', 'fact_sessions → dim_date',        0, (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_sessions f WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.MARTS.dim_date d      WHERE d.date_key      = f.session_date_key))
    UNION ALL SELECT 'Orphan key', 'fact_sessions → dim_customer',    0, (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_sessions f WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.MARTS.dim_customer d  WHERE d.customer_key  = f.customer_key))
    UNION ALL SELECT 'Orphan key', 'fact_sessions → dim_channel',     0, (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_sessions f WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.MARTS.dim_channel d   WHERE d.channel_key   = f.channel_key))
    UNION ALL SELECT 'Orphan key', 'fact_sessions → dim_geography',   0, (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_sessions f WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.MARTS.dim_geography d WHERE d.geography_key = f.geography_key))
    UNION ALL SELECT 'Orphan key', 'fact_marketing_spend → dim_campaign', 0, (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_marketing_spend f WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.MARTS.dim_campaign d WHERE d.campaign_key = f.campaign_key))
    UNION ALL SELECT 'Orphan key', 'fact_marketing_spend → dim_channel',  0, (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_marketing_spend f WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.MARTS.dim_channel d WHERE d.channel_key = f.channel_key))

    -- 4. Unknown members: how many rows fell back to -1 (expected: only the known orphan products)
    UNION ALL SELECT 'Unknown member', 'fact_order_line rows on Unknown product = known orphan lines',
           (SELECT COUNT(*) FROM UK_ECOM.STAGING.stg_order_lines l WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.STAGING.stg_products p WHERE p.product_id = l.product_id)),
           (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_order_line WHERE product_key = -1)
    UNION ALL SELECT 'Unknown member', 'fact_order_line rows on Unknown channel/geography', 0,
           (SELECT COUNT(*) FROM UK_ECOM.MARTS.fact_order_line WHERE channel_key = -1 OR geography_key = -1)

    -- 5. Reconciliation: totals must match staging. Each row is rounded to the penny, so the
    --    totals may differ by at most half a penny per row; anything bigger is a real bug.
    UNION ALL SELECT 'Reconciliation', 'Net revenue matches staging (within half a penny of rounding per row)', 0,
           (SELECT IFF(ABS(f.v - s.v) <= 0.005 * f.n, 0, ROUND(f.v - s.v))
              FROM (SELECT SUM(net_revenue) AS v, COUNT(*) AS n FROM UK_ECOM.MARTS.fact_order_line) f,
                   (SELECT SUM((l.quantity * l.unit_price - l.discount_amount) / (1 + COALESCE(p.vat_rate, 0.20))) AS v
                      FROM UK_ECOM.STAGING.stg_order_lines l
                      LEFT JOIN UK_ECOM.STAGING.stg_products p ON p.product_id = l.product_id) s)
    UNION ALL SELECT 'Reconciliation', 'Allocated shipping matches order shipping (within half a penny of rounding per row)', 0,
           (SELECT IFF(ABS(f.v - s.v) <= 0.005 * f.n, 0, ROUND(f.v - s.v))
              FROM (SELECT SUM(shipping_allocated) AS v, COUNT(*) AS n FROM UK_ECOM.MARTS.fact_order_line) f,
                   (SELECT SUM(shipping_fee / 1.2) AS v FROM UK_ECOM.STAGING.stg_orders) s)
    UNION ALL SELECT 'Reconciliation', 'Every order has an attribution row', 0,
           (SELECT COUNT(*) FROM UK_ECOM.STAGING.stg_orders o WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.STAGING.int_order_attribution a WHERE a.order_id = o.order_id))
)
SELECT test_type, test_name, expected, actual, IFF(expected = actual, 'PASS', 'FAIL') AS result
FROM t;

SELECT * FROM UK_ECOM.STAGING.marts_tests ORDER BY result, test_type;
