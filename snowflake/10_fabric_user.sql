/* =====================================================================
   10_fabric_user.sql: a read-only service user for Fabric / Power BI
   Run as ACCOUNTADMIN after `loader/make_keypair.py --name ecom_bi`
   has printed the public key.

   ECOM_BI_SVC can only:
   - use the ECOM_BI_WH warehouse (so BI cost shows up separately from ELT)
   - SELECT from MARTS views (via ECOM_REPORTER, from 01_setup.sql)
   It can't see RAW or STAGING, and can't change anything.
   ===================================================================== */

USE ROLE ACCOUNTADMIN;

CREATE USER IF NOT EXISTS ECOM_BI_SVC
  TYPE = SERVICE                         -- key-pair only: no password, no UI login
  DEFAULT_ROLE = ECOM_REPORTER
  DEFAULT_WAREHOUSE = ECOM_BI_WH
  DEFAULT_NAMESPACE = UK_ECOM.MARTS
  COMMENT = 'Fabric Dataflow Gen2 / Power BI (read-only MARTS)';

-- Replace <PUBLIC_KEY> with the line printed by make_keypair.py --name ecom_bi (keep the quotes)
ALTER USER ECOM_BI_SVC SET RSA_PUBLIC_KEY = '<PUBLIC_KEY>';

GRANT ROLE ECOM_REPORTER TO USER ECOM_BI_SVC;

-- Check 1: RSA_PUBLIC_KEY_FP should show SHA256:...
DESC USER ECOM_BI_SVC;

-- Check 2: what the reporter role can see. Should be the 11 MARTS views, nothing from RAW/STAGING.
USE ROLE ECOM_REPORTER;
USE WAREHOUSE ECOM_BI_WH;
SHOW VIEWS IN SCHEMA UK_ECOM.MARTS;
SELECT COUNT(*) AS order_lines_visible_to_bi FROM UK_ECOM.MARTS.fact_order_line;
