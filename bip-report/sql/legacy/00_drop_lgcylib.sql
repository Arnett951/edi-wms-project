-- Drop LGCYLIB so 01_create_lgcylib.sql can rebuild it from the current WMS.* data.
-- LGCYLIB is a one-time copy: re-sync it this way whenever WMS.* changes.
--   db2 -tf 00_drop_lgcylib.sql && db2 -tf 01_create_lgcylib.sql && db2 -tf 03_reconcile.sql
CONNECT TO TIREWMS;
DROP TABLE LGCYLIB.INVLOTP;
DROP TABLE LGCYLIB.LOTATRP;
DROP TABLE LGCYLIB.LOCMSTP;
DROP TABLE LGCYLIB.ITMMSTP;
DROP TABLE LGCYLIB.WHSMSTP;
DROP SCHEMA LGCYLIB RESTRICT;
CONNECT RESET;
