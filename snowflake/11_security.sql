-- Day 12: dynamic RLS security table (user email → region). Re-runnable.
-- Power BI role 'Regional Manager' reads it with USERPRINCIPALNAME(); 'All' = see everything.
USE ROLE ECOM_DEVELOPER;
USE WAREHOUSE ECOM_TRANSFORM_WH;

CREATE OR REPLACE TABLE UK_ECOM.MARTS.security_user_region (
    user_email  VARCHAR NOT NULL,   -- must match the Power BI sign-in (UPN)
    region      VARCHAR NOT NULL    -- a dim_geography region, or 'All'
);
-- ECOM_REPORTER can read it through the FUTURE TABLES grant in 01_setup.sql.

INSERT INTO UK_ECOM.MARTS.security_user_region VALUES
  ('ahsan@ahsantheanalyst29.onmicrosoft.com',            'All'),
  ('london.manager@ahsantheanalyst29.onmicrosoft.com',   'London'),
  ('scotland.manager@ahsantheanalyst29.onmicrosoft.com', 'Scotland'),
  ('north.manager@ahsantheanalyst29.onmicrosoft.com',    'North East'),
  ('north.manager@ahsantheanalyst29.onmicrosoft.com',    'North West');   -- one person, two regions

SELECT * FROM UK_ECOM.MARTS.security_user_region ORDER BY user_email, region;
