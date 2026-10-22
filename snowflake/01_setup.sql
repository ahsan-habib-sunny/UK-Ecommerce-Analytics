/* =====================================================================
   01_setup.sql: one-time Snowflake account setup for UK E-commerce
   Run top to bottom in a Snowsight worksheet, as ACCOUNTADMIN.
   Safe to re-run: every statement is IF NOT EXISTS or OR REPLACE.
   ===================================================================== */

-- ACCOUNTADMIN is the only role allowed to create resource monitors.
-- We use it for setup only and then switch to project roles.
USE ROLE ACCOUNTADMIN;

/* ---------------------------------------------------------------------
   1. COST GUARDRAIL: resource monitor
   A hard ceiling on credits, so a forgotten warehouse can't burn the
   $400 trial. The expected spend is 15–25 credits, so 40 leaves headroom.
   --------------------------------------------------------------------- */
CREATE OR REPLACE RESOURCE MONITOR ECOM_RM
  WITH CREDIT_QUOTA = 40                -- total credits allowed per period
       FREQUENCY = MONTHLY              -- quota resets each month
       START_TIMESTAMP = IMMEDIATELY    -- start counting now
  TRIGGERS
       ON 50  PERCENT DO NOTIFY         -- email warning at 20 credits
       ON 80  PERCENT DO NOTIFY         -- email warning at 32 credits
       ON 90  PERCENT DO SUSPEND        -- let running queries finish, then stop
       ON 100 PERCENT DO SUSPEND_IMMEDIATE;  -- kill running queries and stop

/* ---------------------------------------------------------------------
   2. WAREHOUSES (compute)
   Two XS warehouses, one for loading/transforming and one for Power BI
   reads. Snowflake bills per second only while a warehouse runs, so two
   cost no more than one, and you can see BI cost separately from ELT
   cost (a workload-isolation talking point).
   --------------------------------------------------------------------- */
CREATE WAREHOUSE IF NOT EXISTS ECOM_TRANSFORM_WH
  WITH WAREHOUSE_SIZE = 'XSMALL'        -- 1 credit/hour, the smallest size
       AUTO_SUSPEND = 60                -- sleep after 60s idle (billing min is 60s)
       AUTO_RESUME = TRUE               -- wake up automatically when queried
       INITIALLY_SUSPENDED = TRUE       -- don't start billing on creation
       COMMENT = 'Python loads, COPY INTO, STAGING/MARTS builds';

CREATE WAREHOUSE IF NOT EXISTS ECOM_BI_WH
  WITH WAREHOUSE_SIZE = 'XSMALL'
       AUTO_SUSPEND = 60
       AUTO_RESUME = TRUE
       INITIALLY_SUSPENDED = TRUE
       COMMENT = 'Power BI / Dataflow refreshes (read-only)';

-- Attach both warehouses to the monitor so the ceiling applies to them.
ALTER WAREHOUSE ECOM_TRANSFORM_WH SET RESOURCE_MONITOR = ECOM_RM;
ALTER WAREHOUSE ECOM_BI_WH        SET RESOURCE_MONITOR = ECOM_RM;

/* ---------------------------------------------------------------------
   3. ROLES (least privilege)
   ECOM_DEVELOPER: owns and builds everything (you, and the Python loader)
   ECOM_REPORTER:  read-only on MARTS (the role Power BI connects as)
   --------------------------------------------------------------------- */
CREATE ROLE IF NOT EXISTS ECOM_DEVELOPER COMMENT = 'Builds RAW/STAGING/MARTS';
CREATE ROLE IF NOT EXISTS ECOM_REPORTER  COMMENT = 'Read-only on MARTS for Power BI';

-- Role hierarchy: SYSADMIN inherits the custom roles, so admins can still
-- see and manage these objects (Snowflake's recommended pattern).
-- The reporter rolls up into the developer, so the developer can test what BI sees.
GRANT ROLE ECOM_REPORTER  TO ROLE ECOM_DEVELOPER;
GRANT ROLE ECOM_DEVELOPER TO ROLE SYSADMIN;

-- Give yourself both roles. CURRENT_USER() can't be used in GRANT,
-- so replace <YOUR_USERNAME> with the login you signed up with.
GRANT ROLE ECOM_DEVELOPER TO USER <YOUR_USERNAME>;

-- Each role may use (run on) its own warehouse.
GRANT USAGE, OPERATE ON WAREHOUSE ECOM_TRANSFORM_WH TO ROLE ECOM_DEVELOPER;
GRANT USAGE          ON WAREHOUSE ECOM_BI_WH        TO ROLE ECOM_REPORTER;

/* ---------------------------------------------------------------------
   4. DATABASE AND SCHEMAS (the medallion layers)
   RAW:     data exactly as loaded (never edited)
   STAGING: views that type, dedupe and clean
   MARTS:   star schema that Power BI reads
   --------------------------------------------------------------------- */
-- Create as SYSADMIN, then hand ownership to the project role.
USE ROLE SYSADMIN;

CREATE DATABASE IF NOT EXISTS UK_ECOM COMMENT = 'UK E-commerce analytics portfolio';
CREATE SCHEMA IF NOT EXISTS UK_ECOM.RAW;
CREATE SCHEMA IF NOT EXISTS UK_ECOM.STAGING;
CREATE SCHEMA IF NOT EXISTS UK_ECOM.MARTS;

-- ECOM_DEVELOPER owns the database and schemas, so it can create any object inside them.
GRANT OWNERSHIP ON DATABASE UK_ECOM         TO ROLE ECOM_DEVELOPER COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA   UK_ECOM.RAW     TO ROLE ECOM_DEVELOPER COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA   UK_ECOM.STAGING TO ROLE ECOM_DEVELOPER COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA   UK_ECOM.MARTS   TO ROLE ECOM_DEVELOPER COPY CURRENT GRANTS;

-- The reporter can see the database and MARTS, but not RAW or STAGING.
USE ROLE ECOM_DEVELOPER;
GRANT USAGE  ON DATABASE UK_ECOM       TO ROLE ECOM_REPORTER;
GRANT USAGE  ON SCHEMA   UK_ECOM.MARTS TO ROLE ECOM_REPORTER;
GRANT SELECT ON ALL    VIEWS  IN SCHEMA UK_ECOM.MARTS TO ROLE ECOM_REPORTER;
GRANT SELECT ON ALL    TABLES IN SCHEMA UK_ECOM.MARTS TO ROLE ECOM_REPORTER;
-- FUTURE grants cover views we haven't built yet (Day 6), so we don't
-- have to remember to re-grant. FUTURE grants in a schema need the
-- schema owner (us) or MANAGE GRANTS.
GRANT SELECT ON FUTURE VIEWS  IN SCHEMA UK_ECOM.MARTS TO ROLE ECOM_REPORTER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA UK_ECOM.MARTS TO ROLE ECOM_REPORTER;

/* ---------------------------------------------------------------------
   5. LOADING PLUMBING: file format and internal stage (used on Day 4)
   The stage is a landing zone inside Snowflake. Python PUTs Parquet files
   here, then COPY INTO moves them into RAW tables.
   --------------------------------------------------------------------- */
USE SCHEMA UK_ECOM.RAW;

CREATE FILE FORMAT IF NOT EXISTS FF_PARQUET
  TYPE = PARQUET
  COMPRESSION = SNAPPY                  -- pandas/pyarrow's default compression
  COMMENT = 'Parquet files from the Python generator';

CREATE STAGE IF NOT EXISTS STG_LANDING
  FILE_FORMAT = FF_PARQUET              -- default format for files in this stage
  COMMENT = 'Internal stage: generator PUTs Parquet here before COPY INTO';

/* ---------------------------------------------------------------------
   6. SMOKE TEST: should return your role, warehouse and database
   --------------------------------------------------------------------- */
USE WAREHOUSE ECOM_TRANSFORM_WH;
SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA();
SHOW SCHEMAS IN DATABASE UK_ECOM;
