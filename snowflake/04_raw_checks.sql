/* =====================================================================
   04_raw_checks.sql: look at what landed in RAW (run as ECOM_DEVELOPER)
   Read-only. Nothing here changes data.
   ===================================================================== */

USE ROLE ECOM_DEVELOPER;
USE WAREHOUSE ECOM_TRANSFORM_WH;
USE SCHEMA UK_ECOM.RAW;

-- 1. Row counts per table (from metadata: free and instant, no warehouse needed)
SELECT table_name, row_count, ROUND(bytes / 1024 / 1024, 1) AS size_mb
FROM UK_ECOM.INFORMATION_SCHEMA.TABLES
WHERE table_schema = 'RAW'
ORDER BY row_count DESC;

-- 2. Load history: every file COPY INTO processed, with status and row counts
SELECT table_name, file_name, status, row_count, last_load_time
FROM UK_ECOM.INFORMATION_SCHEMA.LOAD_HISTORY
WHERE schema_name = 'RAW'
ORDER BY last_load_time DESC
LIMIT 50;

-- 3. The audit columns: which file each row came from, and when
SELECT _source_file, COUNT(*) AS rows_loaded, MIN(_loaded_at) AS loaded_at
FROM orders
GROUP BY _source_file
ORDER BY _source_file;

-- 4. A first look at the raw data. Notice anything odd? (keep notes for Day 5)
SELECT * FROM orders      SAMPLE (20 ROWS);
SELECT * FROM order_lines SAMPLE (20 ROWS);
SELECT * FROM customers   SAMPLE (20 ROWS);
SELECT * FROM products    SAMPLE (20 ROWS);
