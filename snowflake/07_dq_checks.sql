/* =====================================================================
   07_dq_checks.sql: data-quality scorecard
   One row per check: how many RAW rows had the problem, how many are
   still wrong after STAGING, and how it was handled.
   Expected: remaining_after_staging = 0 for everything fixed in STAGING.
   Query it any time: SELECT * FROM UK_ECOM.STAGING.dq_checks;
   ===================================================================== */

USE ROLE ECOM_DEVELOPER;
USE WAREHOUSE ECOM_TRANSFORM_WH;
USE SCHEMA UK_ECOM.STAGING;

CREATE OR REPLACE VIEW dq_checks AS
-- Issues found in RAW and repaired in STAGING
SELECT 'order_lines' AS table_name, 'Duplicate order_line_id' AS check_name, 'Repaired' AS handling,
       (SELECT COUNT(*) - COUNT(DISTINCT order_line_id) FROM UK_ECOM.RAW.order_lines) AS raw_rows_affected,
       (SELECT COUNT(*) - COUNT(DISTINCT order_line_id) FROM stg_order_lines)          AS remaining_after_staging
UNION ALL
SELECT 'customers', 'Postcode not in standard format', 'Repaired',
       (SELECT COUNT_IF(NOT REGEXP_LIKE(postcode, '^[A-Z]{1,2}[0-9][0-9A-Z]? [0-9][A-Z]{2}$')) FROM UK_ECOM.RAW.customers),
       (SELECT COUNT_IF(NOT REGEXP_LIKE(postcode, '^[A-Z]{1,2}[0-9][0-9A-Z]? [0-9][A-Z]{2}$')) FROM stg_customers)
UNION ALL
SELECT 'orders', 'Delivery postcode not in standard format', 'Repaired',
       (SELECT COUNT_IF(NOT REGEXP_LIKE(delivery_postcode, '^[A-Z]{1,2}[0-9][0-9A-Z]? [0-9][A-Z]{2}$')) FROM UK_ECOM.RAW.orders),
       (SELECT COUNT_IF(NOT REGEXP_LIKE(delivery_postcode, '^[A-Z]{1,2}[0-9][0-9A-Z]? [0-9][A-Z]{2}$')) FROM stg_orders)
UNION ALL
SELECT 'products', 'Category not in the standard list', 'Repaired',
       (SELECT COUNT_IF(category NOT IN ('Fashion','Home','Electronics','Beauty','Books','Kids')) FROM UK_ECOM.RAW.products),
       (SELECT COUNT_IF(category NOT IN ('Fashion','Home','Electronics','Beauty','Books','Kids')) FROM stg_products)
UNION ALL
SELECT 'order_lines', 'Marketplace price sent in pence', 'Repaired',
       (SELECT COUNT_IF(is_price_converted_from_pence) FROM stg_order_lines),
       (SELECT COUNT(*) FROM stg_order_lines l JOIN stg_products p ON p.product_id = l.product_id
         WHERE l.unit_price > p.list_price * 2)                        -- anything still priced at 2× list
UNION ALL
SELECT 'orders', 'order_ts not in documented format', 'Repaired',
       (SELECT COUNT_IF(TRY_TO_TIMESTAMP_NTZ(order_ts, 'YYYY-MM-DD HH24:MI:SS') IS NULL) FROM UK_ECOM.RAW.orders),
       (SELECT COUNT_IF(order_ts IS NULL) FROM stg_orders)
UNION ALL
SELECT 'returns', 'Return dated before its order', 'Repaired',
       (SELECT COUNT_IF(is_return_before_order) FROM stg_returns),
       (SELECT COUNT(*) FROM stg_returns r JOIN stg_order_lines l USING (order_line_id) JOIN stg_orders o USING (order_id)
         WHERE r.return_date < o.order_date)
UNION ALL
-- Issues handled later in MARTS
SELECT 'order_lines', 'product_id missing from products (orphan)', 'Mapped to Unknown product (-1) in MARTS',
       (SELECT COUNT(*) FROM stg_order_lines l WHERE NOT EXISTS (SELECT 1 FROM stg_products p WHERE p.product_id = l.product_id)),
       (SELECT COUNT(*) FROM stg_order_lines l WHERE NOT EXISTS (SELECT 1 FROM stg_products p WHERE p.product_id = l.product_id))
UNION ALL
-- Guards: assumptions that must stay true (expected 0 everywhere)
SELECT 'orders', 'Duplicate order_id', 'Guard',
       (SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM UK_ECOM.RAW.orders),
       (SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM stg_orders)
UNION ALL
SELECT 'sessions', 'Duplicate session_id (no dedupe in stg_sessions)', 'Guard',
       (SELECT COUNT(*) - COUNT(DISTINCT session_id) FROM UK_ECOM.RAW.sessions),
       (SELECT COUNT(*) - COUNT(DISTINCT session_id) FROM stg_sessions)
UNION ALL
SELECT 'order_lines', 'Line without an order', 'Guard',
       (SELECT COUNT(*) FROM UK_ECOM.RAW.order_lines l WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.RAW.orders o WHERE o.order_id = l.order_id)),
       (SELECT COUNT(*) FROM stg_order_lines l WHERE NOT EXISTS (SELECT 1 FROM stg_orders o WHERE o.order_id = l.order_id))
UNION ALL
SELECT 'returns', 'Return without an order line', 'Guard',
       (SELECT COUNT(*) FROM UK_ECOM.RAW.returns r WHERE NOT EXISTS (SELECT 1 FROM UK_ECOM.RAW.order_lines l WHERE l.order_line_id = r.order_line_id)),
       (SELECT COUNT(*) FROM stg_returns r WHERE NOT EXISTS (SELECT 1 FROM stg_order_lines l WHERE l.order_line_id = r.order_line_id));

SELECT * FROM dq_checks ORDER BY handling DESC, table_name;
