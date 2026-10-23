/* =====================================================================
   05_profile_raw.sql: data profiling. What's wrong with RAW?
   Read-only. Run each block, read the result, and write down anything
   that breaks the rules in docs/data_dictionary.md. Those notes become
   the cleaning rules for the STAGING views.

   Tip: run one block at a time (select it, then Ctrl+Enter).
   ===================================================================== */

USE ROLE ECOM_DEVELOPER;
USE WAREHOUSE ECOM_TRANSFORM_WH;
USE SCHEMA UK_ECOM.RAW;

/* ---------------------------------------------------------------------
   A. UNIQUENESS: every primary key should appear exactly once.
   What to look for: duplicate_rows > 0.
   --------------------------------------------------------------------- */
SELECT 'customers'   AS table_name, COUNT(*) AS total_rows, COUNT(DISTINCT customer_id)   AS distinct_keys, COUNT(*) - COUNT(DISTINCT customer_id)   AS duplicate_rows FROM customers
UNION ALL SELECT 'products',    COUNT(*), COUNT(DISTINCT product_id),    COUNT(*) - COUNT(DISTINCT product_id)    FROM products
UNION ALL SELECT 'orders',      COUNT(*), COUNT(DISTINCT order_id),      COUNT(*) - COUNT(DISTINCT order_id)      FROM orders
UNION ALL SELECT 'order_lines', COUNT(*), COUNT(DISTINCT order_line_id), COUNT(*) - COUNT(DISTINCT order_line_id) FROM order_lines
UNION ALL SELECT 'returns',     COUNT(*), COUNT(DISTINCT return_id),     COUNT(*) - COUNT(DISTINCT return_id)     FROM returns
UNION ALL SELECT 'sessions',    COUNT(*), COUNT(DISTINCT session_id),    COUNT(*) - COUNT(DISTINCT session_id)    FROM sessions
UNION ALL SELECT 'campaigns',   COUNT(*), COUNT(DISTINCT campaign_id),   COUNT(*) - COUNT(DISTINCT campaign_id)   FROM campaigns;

-- If you find duplicates: are they exact copies, or different rows that share a key?
-- (Replace <table>/<key> with what you found.)
-- SELECT * FROM <table> WHERE <key> IN (SELECT <key> FROM <table> GROUP BY 1 HAVING COUNT(*) > 1) ORDER BY <key> LIMIT 20;


/* ---------------------------------------------------------------------
   B. RELATIONSHIPS: every foreign key should find its parent.
   What to look for: orphan_rows > 0. Which relationships break?
   --------------------------------------------------------------------- */
SELECT 'order_lines → orders' AS relationship, COUNT(*) AS orphan_rows
  FROM order_lines l WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.order_id = l.order_id)
UNION ALL SELECT 'order_lines → products', COUNT(*)
  FROM order_lines l WHERE NOT EXISTS (SELECT 1 FROM products p WHERE p.product_id = l.product_id)
UNION ALL SELECT 'returns → order_lines', COUNT(*)
  FROM returns r WHERE NOT EXISTS (SELECT 1 FROM order_lines l WHERE l.order_line_id = r.order_line_id)
UNION ALL SELECT 'orders → customers', COUNT(*)
  FROM orders o WHERE NOT EXISTS (SELECT 1 FROM customers c WHERE c.customer_id = o.customer_id)
UNION ALL SELECT 'orders.session_id → sessions', COUNT(*)
  FROM orders o WHERE o.session_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM sessions s WHERE s.session_id = o.session_id)
UNION ALL SELECT 'sessions.customer_id → customers', COUNT(*)
  FROM sessions s WHERE s.customer_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM customers c WHERE c.customer_id = s.customer_id)
UNION ALL SELECT 'orders.promo_code → campaigns', COUNT(*)
  FROM orders o WHERE o.promo_code IS NOT NULL AND NOT EXISTS (SELECT 1 FROM campaigns c WHERE c.campaign_code = o.promo_code)
UNION ALL SELECT 'marketing_spend.campaign_code → campaigns', COUNT(*)
  FROM marketing_spend m WHERE m.campaign_code IS NOT NULL AND NOT EXISTS (SELECT 1 FROM campaigns c WHERE c.campaign_code = m.campaign_code);

-- If something is orphaned, look at the missing keys. How many distinct ones? Is there a pattern?


/* ---------------------------------------------------------------------
   C. TIMESTAMPS: the data dictionary says text timestamps are
   'YYYY-MM-DD HH24:MI:SS'. Does every value follow that format?
   What to look for: rows that don't parse, and what they look like.
   --------------------------------------------------------------------- */
SELECT COUNT(*) AS total_orders,
       COUNT_IF(TRY_TO_TIMESTAMP_NTZ(order_ts, 'YYYY-MM-DD HH24:MI:SS') IS NULL) AS not_in_documented_format
FROM orders;

SELECT order_ts FROM orders
WHERE TRY_TO_TIMESTAMP_NTZ(order_ts, 'YYYY-MM-DD HH24:MI:SS') IS NULL
LIMIT 20;

SELECT COUNT(*) AS total_customers,
       COUNT_IF(TRY_TO_TIMESTAMP_NTZ(registered_at, 'YYYY-MM-DD HH24:MI:SS') IS NULL) AS not_in_documented_format
FROM customers;

-- Danger zone: what does Snowflake do if you DON'T give it a format? Compare these two columns.
SELECT order_ts, TRY_TO_TIMESTAMP_NTZ(order_ts) AS auto_detected
FROM orders
WHERE TRY_TO_TIMESTAMP_NTZ(order_ts, 'YYYY-MM-DD HH24:MI:SS') IS NULL
LIMIT 20;


/* ---------------------------------------------------------------------
   D. POSTCODES: a valid UK postcode looks like 'M14 5RT' or 'SW1A 1AA':
   upper case, one space before the last three characters.
   What to look for: values that break the pattern, and HOW they break it.
   --------------------------------------------------------------------- */
SELECT 'customers.postcode' AS col, COUNT(*) AS total,
       COUNT_IF(NOT REGEXP_LIKE(postcode, '^[A-Z]{1,2}[0-9][0-9A-Z]? [0-9][A-Z]{2}$')) AS non_standard
FROM customers
UNION ALL
SELECT 'orders.delivery_postcode', COUNT(*),
       COUNT_IF(NOT REGEXP_LIKE(delivery_postcode, '^[A-Z]{1,2}[0-9][0-9A-Z]? [0-9][A-Z]{2}$'))
FROM orders;

-- The '|' characters show hidden leading/trailing spaces
SELECT '|' || postcode || '|' AS postcode_with_edges
FROM customers
WHERE NOT REGEXP_LIKE(postcode, '^[A-Z]{1,2}[0-9][0-9A-Z]? [0-9][A-Z]{2}$')
LIMIT 20;


/* ---------------------------------------------------------------------
   E. CATEGORIES AND CODES: each text code should have a small, clean set
   of values. What to look for: near-duplicates of the same value.
   --------------------------------------------------------------------- */
SELECT '|' || category || '|' AS category, COUNT(*) AS products FROM products GROUP BY 1 ORDER BY 1;
SELECT status,         COUNT(*) FROM orders   GROUP BY 1 ORDER BY 2 DESC;
SELECT sales_channel,  COUNT(*) FROM orders   GROUP BY 1 ORDER BY 2 DESC;
SELECT payment_method, COUNT(*) FROM orders   GROUP BY 1 ORDER BY 2 DESC;
SELECT reason_code,    COUNT(*) FROM returns  GROUP BY 1 ORDER BY 2 DESC;
SELECT device, channel, COUNT(*) FROM sessions GROUP BY 1, 2 ORDER BY 1, 3 DESC;


/* ---------------------------------------------------------------------
   F. NUMBERS: are values in a believable range? Compare like with like.
   What to look for: one group whose prices look very different from the rest.
   --------------------------------------------------------------------- */
SELECT o.sales_channel,
       COUNT(*)                    AS lines,
       MIN(l.unit_price)           AS min_price,
       MEDIAN(l.unit_price)        AS median_price,
       MAX(l.unit_price)           AS max_price,
       MEDIAN(p.list_price)        AS median_list_price_of_same_products
FROM order_lines l
JOIN orders   o ON o.order_id   = l.order_id
LEFT JOIN products p ON p.product_id = l.product_id
GROUP BY 1
ORDER BY 1;

SELECT COUNT_IF(quantity <= 0)                        AS non_positive_qty,
       COUNT_IF(unit_price <= 0)                      AS non_positive_price,
       COUNT_IF(discount_amount > quantity * unit_price) AS discount_bigger_than_line,
       COUNT_IF(unit_cost <= 0)                       AS non_positive_cost
FROM order_lines;


/* ---------------------------------------------------------------------
   G. DATE LOGIC: things must happen in the right order.
   What to look for: a return that happens before its order was placed.
   --------------------------------------------------------------------- */
SELECT COUNT(*) AS returns_checked,
       COUNT_IF(r.return_date < TRY_TO_DATE(LEFT(o.order_ts, 10), 'YYYY-MM-DD')) AS returned_before_ordered,
       COUNT_IF(DATEDIFF(day, TRY_TO_DATE(LEFT(o.order_ts, 10), 'YYYY-MM-DD'), r.return_date) > 30) AS outside_30_day_window
FROM returns r
JOIN order_lines l ON l.order_line_id = r.order_line_id
JOIN orders o      ON o.order_id      = l.order_id;


/* ---------------------------------------------------------------------
   H. MISSING VALUES: which columns have NULLs, and is that expected?
   (Check against the data dictionary: some NULLs are legitimate.)
   --------------------------------------------------------------------- */
SELECT COUNT(*) AS customers, COUNT_IF(email IS NULL) AS no_email,
       COUNT_IF(date_of_birth IS NULL) AS no_dob, COUNT_IF(postcode IS NULL) AS no_postcode
FROM customers;

SELECT sales_channel, COUNT(*) AS orders, COUNT_IF(session_id IS NULL) AS no_session,
       COUNT_IF(promo_code IS NOT NULL) AS with_promo
FROM orders GROUP BY 1;


/* ---------------------------------------------------------------------
   I. VOLUMES OVER TIME: steady growth with seasonal peaks is expected.
   What to look for: a month that doesn't fit the pattern.
   (Uses only rows with the documented timestamp format; see block C.)
   --------------------------------------------------------------------- */
SELECT DATE_TRUNC(month, TRY_TO_TIMESTAMP_NTZ(order_ts, 'YYYY-MM-DD HH24:MI:SS')) AS month,
       COUNT(*) AS orders
FROM orders
GROUP BY 1
ORDER BY 1;
