/* =====================================================================
   03_loader_user.sql: a service user for the Python loader
   Run as ACCOUNTADMIN after loader/make_keypair.py has printed your key.

   Why a separate user and role?
   - Scripts shouldn't log in as you. A SERVICE user can't use a password
     or the web UI; it can only authenticate with its RSA key.
   - Least privilege: the loader can write files to the stage and insert
     into RAW tables, and nothing else. It can't read MARTS, drop
     tables, or touch other schemas.
   ===================================================================== */

USE ROLE ACCOUNTADMIN;

-- 1. A role that can only load RAW
CREATE ROLE IF NOT EXISTS ECOM_LOADER_ROLE COMMENT = 'PUT files to the RAW stage and COPY INTO RAW tables';
GRANT ROLE ECOM_LOADER_ROLE TO ROLE ECOM_DEVELOPER;          -- keep the role hierarchy tidy

GRANT USAGE ON WAREHOUSE ECOM_TRANSFORM_WH        TO ROLE ECOM_LOADER_ROLE;
GRANT USAGE ON DATABASE  UK_ECOM                  TO ROLE ECOM_LOADER_ROLE;
GRANT USAGE ON SCHEMA    UK_ECOM.RAW              TO ROLE ECOM_LOADER_ROLE;
GRANT USAGE ON FILE FORMAT UK_ECOM.RAW.FF_PARQUET TO ROLE ECOM_LOADER_ROLE;
GRANT READ, WRITE ON STAGE UK_ECOM.RAW.STG_LANDING TO ROLE ECOM_LOADER_ROLE;   -- WRITE = PUT/REMOVE, READ = LIST/COPY
GRANT SELECT, INSERT, TRUNCATE ON ALL TABLES IN SCHEMA UK_ECOM.RAW TO ROLE ECOM_LOADER_ROLE;

-- 2. The service user, logging in with the RSA public key only
CREATE USER IF NOT EXISTS ECOM_LOADER
  TYPE = SERVICE                         -- no password, no UI login: key-pair only
  DEFAULT_ROLE = ECOM_LOADER_ROLE
  DEFAULT_WAREHOUSE = ECOM_TRANSFORM_WH
  DEFAULT_NAMESPACE = UK_ECOM.RAW
  COMMENT = 'Python loader (loader/load_to_snowflake.py)';

-- Replace <PUBLIC_KEY> with the one long line printed by make_keypair.py (keep the quotes)
ALTER USER ECOM_LOADER SET RSA_PUBLIC_KEY = '<PUBLIC_KEY>';

GRANT ROLE ECOM_LOADER_ROLE TO USER ECOM_LOADER;

-- 3. Parquet timestamps and decimals are "logical types". This tells COPY to read
--    them as real TIMESTAMP/NUMBER values rather than raw integers.
USE ROLE ECOM_DEVELOPER;
ALTER FILE FORMAT UK_ECOM.RAW.FF_PARQUET SET USE_LOGICAL_TYPE = TRUE;

-- Check: RSA_PUBLIC_KEY_FP should show a fingerprint like SHA256:...
USE ROLE ACCOUNTADMIN;
DESC USER ECOM_LOADER;
