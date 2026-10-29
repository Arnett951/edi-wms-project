-- =====================================================
-- One-time Snowflake setup for the WMS lab. Run in a Snowsight worksheet as
-- ACCOUNTADMIN (the trial's default role).
--
-- Least-privilege layout, same shape a customer account would use:
--   WMSLAB_WH      X-Small warehouse, suspends after 60s idle (trial credits)
--   WMSLAB         database; RAW = loaded copies, ANALYTICS = views
--   WMSLAB_LOADER  role that owns the lab objects; the copy script uses it
-- =====================================================
USE ROLE ACCOUNTADMIN;

CREATE WAREHOUSE IF NOT EXISTS WMSLAB_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE;

CREATE ROLE IF NOT EXISTS WMSLAB_LOADER;
GRANT ROLE WMSLAB_LOADER TO ROLE SYSADMIN;
GRANT USAGE, OPERATE ON WAREHOUSE WMSLAB_WH TO ROLE WMSLAB_LOADER;

CREATE DATABASE IF NOT EXISTS WMSLAB;
GRANT OWNERSHIP ON DATABASE WMSLAB TO ROLE WMSLAB_LOADER COPY CURRENT GRANTS;

-- Grant the role to yourself (replace with your login name if different).
GRANT ROLE WMSLAB_LOADER TO USER CARNETT909;

-- Key-pair auth for the copy script, so it never needs your password or MFA.
-- Paste the public key body that snowflake/make_keypair.py prints (no BEGIN/END lines).
-- ALTER USER CARNETT909 SET RSA_PUBLIC_KEY = 'MIIBIjANBgkq...';
-- Check it took: DESC USER CARNETT909 ->  RSA_PUBLIC_KEY_FP is filled in.

-- Optional guardrail on trial credits: email/suspend before burning the $400.
-- CREATE RESOURCE MONITOR WMSLAB_RM WITH CREDIT_QUOTA = 20
--   TRIGGERS ON 80 PERCENT DO NOTIFY ON 100 PERCENT DO SUSPEND;
-- ALTER WAREHOUSE WMSLAB_WH SET RESOURCE_MONITOR = WMSLAB_RM;
