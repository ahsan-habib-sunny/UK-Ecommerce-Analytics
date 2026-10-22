/* =====================================================================
   02_raw_tables.sql: empty RAW tables, ready for COPY INTO
   Run as ECOM_DEVELOPER. Safe to re-run (CREATE OR REPLACE wipes the
   table, so only re-run before loading or when you want a clean reload).

   RAW rules:
   - Columns match the source exactly (see docs/data_dictionary.md).
   - Messy text columns (order_ts, registered_at) stay VARCHAR here;
     STAGING casts them on Day 5. RAW never "fixes" anything.
   - Every table gets two audit columns, filled in by COPY INTO:
       _source_file: which Parquet file the row came from
       _loaded_at:   when the load ran
   ===================================================================== */

USE ROLE ECOM_DEVELOPER;
USE WAREHOUSE ECOM_TRANSFORM_WH;
USE SCHEMA UK_ECOM.RAW;

CREATE OR REPLACE TABLE customers (
    customer_id       NUMBER(38,0),
    email             VARCHAR,
    first_name        VARCHAR,
    last_name         VARCHAR,
    postcode          VARCHAR,
    registered_at     VARCHAR,          -- text in the CRM export; cast in STAGING
    date_of_birth     DATE,
    marketing_opt_in  BOOLEAN,
    _source_file      VARCHAR,
    _loaded_at        TIMESTAMP_LTZ
) COMMENT = 'CRM customer snapshot';

CREATE OR REPLACE TABLE products (
    product_id        NUMBER(38,0),
    sku               VARCHAR,
    product_name      VARCHAR,
    category          VARCHAR,
    subcategory       VARCHAR,
    brand             VARCHAR,
    list_price        NUMBER(10,2),
    unit_cost         NUMBER(10,2),
    vat_rate          NUMBER(4,2),
    launched_on       DATE,
    discontinued_on   DATE,
    _source_file      VARCHAR,
    _loaded_at        TIMESTAMP_LTZ
) COMMENT = 'PIM product snapshot';

CREATE OR REPLACE TABLE orders (
    order_id          NUMBER(38,0),
    customer_id       NUMBER(38,0),
    order_ts          VARCHAR,          -- text from the OMS; cast in STAGING
    sales_channel     VARCHAR,
    session_id        VARCHAR,
    delivery_postcode VARCHAR,
    promo_code        VARCHAR,
    shipping_fee      NUMBER(10,2),
    payment_method    VARCHAR,
    status            VARCHAR,
    _source_file      VARCHAR,
    _loaded_at        TIMESTAMP_LTZ
) COMMENT = 'OMS order headers, appended monthly';

CREATE OR REPLACE TABLE order_lines (
    order_line_id     NUMBER(38,0),
    order_id          NUMBER(38,0),
    product_id        NUMBER(38,0),
    quantity          NUMBER(38,0),
    unit_price        NUMBER(12,2),
    discount_amount   NUMBER(12,2),
    unit_cost         NUMBER(10,2),
    _source_file      VARCHAR,
    _loaded_at        TIMESTAMP_LTZ
) COMMENT = 'OMS order lines, appended monthly';

CREATE OR REPLACE TABLE returns (
    return_id         NUMBER(38,0),
    order_line_id     NUMBER(38,0),
    return_date       DATE,
    quantity_returned NUMBER(38,0),
    reason_code       VARCHAR,
    refund_amount     NUMBER(10,2),
    _source_file      VARCHAR,
    _loaded_at        TIMESTAMP_LTZ
) COMMENT = 'Returns portal, appended monthly';

CREATE OR REPLACE TABLE sessions (
    session_id        VARCHAR,
    session_start_ts  TIMESTAMP_NTZ,
    customer_id       NUMBER(38,0),
    device            VARCHAR,
    channel           VARCHAR,
    campaign_code     VARCHAR,
    landing_page_type VARCHAR,
    postcode_area     VARCHAR,
    pageviews         NUMBER(38,0),
    added_to_basket   BOOLEAN,
    converted         BOOLEAN,
    _source_file      VARCHAR,
    _loaded_at        TIMESTAMP_LTZ
) COMMENT = 'Web/app analytics sessions, appended monthly';

CREATE OR REPLACE TABLE campaigns (
    campaign_id       NUMBER(38,0),
    campaign_code     VARCHAR,
    campaign_name     VARCHAR,
    campaign_type     VARCHAR,
    start_date        DATE,
    end_date          DATE,
    discount_pct      NUMBER(4,2),
    _source_file      VARCHAR,
    _loaded_at        TIMESTAMP_LTZ
) COMMENT = 'Marketing calendar snapshot';

CREATE OR REPLACE TABLE marketing_spend (
    spend_date        DATE,
    campaign_code     VARCHAR,
    channel           VARCHAR,
    spend             NUMBER(12,2),
    impressions       NUMBER(38,0),
    clicks            NUMBER(38,0),
    _source_file      VARCHAR,
    _loaded_at        TIMESTAMP_LTZ
) COMMENT = 'Ad platform daily spend, appended monthly';

CREATE OR REPLACE TABLE postcode_areas (
    postcode_area     VARCHAR,
    area_name         VARCHAR,
    region            VARCHAR,
    country           VARCHAR,
    _source_file      VARCHAR,
    _loaded_at        TIMESTAMP_LTZ
) COMMENT = 'Reference: UK postcode areas → ITL1 region';

-- Should list 9 tables, all with 0 rows
SHOW TABLES IN SCHEMA UK_ECOM.RAW;
