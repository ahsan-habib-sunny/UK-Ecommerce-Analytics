/* =====================================================================
   06_staging_views.sql: STAGING layer, one view per RAW table
   Run as ECOM_DEVELOPER. Views are free to create and always show
   the current RAW data, so there's nothing to refresh.

   STAGING rules:
   - Cast types, standardise text, remove duplicates, repair known issues.
   - Never drop a row silently: every repair also sets an is_* flag, so
     the fix is visible and countable (see dq_checks in 07).
   - Business logic (revenue, VAT, attribution) waits for MARTS.
   ===================================================================== */

USE ROLE ECOM_DEVELOPER;
USE WAREHOUSE ECOM_TRANSFORM_WH;
USE SCHEMA UK_ECOM.STAGING;

-- Reference data: tidy text only
CREATE OR REPLACE VIEW stg_postcode_areas AS
SELECT
    UPPER(TRIM(postcode_area)) AS postcode_area,
    TRIM(area_name)            AS area_name,
    TRIM(region)               AS region,
    TRIM(country)              AS country
FROM UK_ECOM.RAW.postcode_areas;


-- Customers: standard postcodes, typed registration timestamp
CREATE OR REPLACE VIEW stg_customers AS
WITH src AS (
    SELECT *,
           REGEXP_REPLACE(UPPER(postcode), '\\s', '') AS pc_compact     -- 'sw1a 1aa ' → 'SW1A1AA'
    FROM UK_ECOM.RAW.customers
    QUALIFY ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY _loaded_at DESC) = 1   -- latest snapshot wins
)
SELECT
    customer_id,
    LOWER(TRIM(email))                                          AS email,
    TRIM(first_name)                                            AS first_name,
    TRIM(last_name)                                             AS last_name,
    LEFT(pc_compact, LENGTH(pc_compact) - 3) || ' ' || RIGHT(pc_compact, 3) AS postcode,   -- inward code is always 3 chars
    REGEXP_SUBSTR(pc_compact, '^[A-Z]{1,2}')                    AS postcode_area,
    TRY_TO_TIMESTAMP_NTZ(registered_at, 'YYYY-MM-DD HH24:MI:SS') AS registered_at,
    date_of_birth,
    marketing_opt_in,
    postcode <> LEFT(pc_compact, LENGTH(pc_compact) - 3) || ' ' || RIGHT(pc_compact, 3) AS is_postcode_reformatted,
    _loaded_at
FROM src;


-- Products: one spelling per category
CREATE OR REPLACE VIEW stg_products AS
SELECT
    product_id,
    TRIM(sku)                  AS sku,
    TRIM(product_name)         AS product_name,
    INITCAP(TRIM(category))    AS category,           -- 'home ', 'HOME' → 'Home'
    TRIM(subcategory)          AS subcategory,
    TRIM(brand)                AS brand,
    list_price,
    unit_cost,
    vat_rate,
    launched_on,
    discontinued_on,
    discontinued_on IS NULL    AS is_active,
    category <> INITCAP(TRIM(category)) AS is_category_cleaned,
    _loaded_at
FROM UK_ECOM.RAW.products
QUALIFY ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY _loaded_at DESC) = 1;


-- Orders: two timestamp formats → one TIMESTAMP, standard postcodes
CREATE OR REPLACE VIEW stg_orders AS
WITH src AS (
    SELECT *,
           TRY_TO_TIMESTAMP_NTZ(order_ts, 'YYYY-MM-DD HH24:MI:SS') AS ts_iso,
           TRY_TO_TIMESTAMP_NTZ(order_ts, 'DD/MM/YYYY HH24:MI')    AS ts_legacy,   -- old OMS, UK day-first
           REGEXP_REPLACE(UPPER(delivery_postcode), '\\s', '')     AS pc_compact
    FROM UK_ECOM.RAW.orders
    QUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY _loaded_at DESC) = 1
)
SELECT
    order_id,
    customer_id,
    COALESCE(ts_iso, ts_legacy)                    AS order_ts,
    COALESCE(ts_iso, ts_legacy)::DATE              AS order_date,
    LOWER(TRIM(sales_channel))                     AS sales_channel,
    session_id,
    LEFT(pc_compact, LENGTH(pc_compact) - 3) || ' ' || RIGHT(pc_compact, 3) AS delivery_postcode,
    REGEXP_SUBSTR(pc_compact, '^[A-Z]{1,2}')       AS delivery_postcode_area,
    NULLIF(TRIM(promo_code), '')                   AS promo_code,
    shipping_fee,
    LOWER(TRIM(payment_method))                    AS payment_method,
    INITCAP(TRIM(status))                          AS status,
    INITCAP(TRIM(status)) = 'Cancelled'            AS is_cancelled,
    ts_iso IS NULL AND ts_legacy IS NOT NULL       AS is_legacy_ts_format,
    delivery_postcode <> LEFT(pc_compact, LENGTH(pc_compact) - 3) || ' ' || RIGHT(pc_compact, 3) AS is_postcode_reformatted,
    _loaded_at
FROM src;


-- Order lines: drop exact duplicates, convert marketplace pence → pounds
CREATE OR REPLACE VIEW stg_order_lines AS
WITH lines AS (
    SELECT *
    FROM UK_ECOM.RAW.order_lines
    QUALIFY ROW_NUMBER() OVER (PARTITION BY order_line_id ORDER BY _loaded_at DESC, _source_file) = 1
)
SELECT
    l.order_line_id,
    l.order_id,
    l.product_id,
    l.quantity,
    -- The marketplace feed sends prices in pence; everything else is already in pounds
    IFF(o.sales_channel = 'marketplace', l.unit_price      / 100, l.unit_price)::NUMBER(10,2)      AS unit_price,
    IFF(o.sales_channel = 'marketplace', l.discount_amount / 100, l.discount_amount)::NUMBER(10,2) AS discount_amount,
    l.unit_cost,
    o.sales_channel = 'marketplace' AS is_price_converted_from_pence,
    l._loaded_at
FROM lines l
LEFT JOIN stg_orders o ON o.order_id = l.order_id;   -- same source system (OMS), so this join is allowed


-- Returns: a return can't happen before its order
CREATE OR REPLACE VIEW stg_returns AS
SELECT
    r.return_id,
    r.order_line_id,
    IFF(r.return_date < o.order_date, o.order_date, r.return_date) AS return_date,   -- clamp clock-bug dates
    r.return_date                                  AS return_date_raw,
    r.return_date < o.order_date                   AS is_return_before_order,
    r.quantity_returned,
    UPPER(TRIM(r.reason_code))                     AS reason_code,
    r.refund_amount,
    r._loaded_at
FROM UK_ECOM.RAW.returns r
LEFT JOIN stg_order_lines l ON l.order_line_id = r.order_line_id
LEFT JOIN stg_orders o      ON o.order_id      = l.order_id
QUALIFY ROW_NUMBER() OVER (PARTITION BY r.return_id ORDER BY r._loaded_at DESC) = 1;


-- Sessions: 7M rows. Profiling found no duplicate keys, so there's no ROW_NUMBER here:
-- a window over 7M rows on every query costs real credits. dq_checks guards the assumption instead.
CREATE OR REPLACE VIEW stg_sessions AS
SELECT
    session_id,
    session_start_ts,
    session_start_ts::DATE         AS session_date,
    customer_id,
    LOWER(TRIM(device))            AS device,
    TRIM(channel)                  AS channel,
    NULLIF(TRIM(campaign_code), '') AS campaign_code,
    LOWER(TRIM(landing_page_type)) AS landing_page_type,
    UPPER(TRIM(postcode_area))     AS postcode_area,
    pageviews,
    added_to_basket,
    converted,
    _loaded_at
FROM UK_ECOM.RAW.sessions;


CREATE OR REPLACE VIEW stg_campaigns AS
SELECT
    campaign_id,
    UPPER(TRIM(campaign_code)) AS campaign_code,
    TRIM(campaign_name)        AS campaign_name,
    TRIM(campaign_type)        AS campaign_type,
    start_date,
    end_date,
    discount_pct,
    _loaded_at
FROM UK_ECOM.RAW.campaigns
QUALIFY ROW_NUMBER() OVER (PARTITION BY campaign_id ORDER BY _loaded_at DESC) = 1;


CREATE OR REPLACE VIEW stg_marketing_spend AS
SELECT
    spend_date,
    NULLIF(UPPER(TRIM(campaign_code)), '') AS campaign_code,
    TRIM(channel)              AS channel,
    spend,
    impressions,
    clicks,
    _loaded_at
FROM UK_ECOM.RAW.marketing_spend;


SHOW VIEWS IN SCHEMA UK_ECOM.STAGING;
