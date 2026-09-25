-- ============================================================================
-- LGCYLIB: a legacy IBM i-style copy of the WMS lab schema (Db2 LUW).
--
-- Mimics common conventions of RPG-era IBM i applications -- NOT the actual
-- schema of Manhattan WMi or any real product:
--   * library (schema) + "physical file" names of <= 10 chars ending in P
--   * 6-char column names with a per-file prefix (IL = inventory lot, ...)
--   * no surrogate keys; files join on natural keys (warehouse + location, sku + lot)
--   * fixed-length, blank-padded CHAR text
--   * dates as DECIMAL(8,0) YYYYMMDD, or DECIMAL(7,0) CYYMMDD
--     (C = century flag: 0 = 19xx, 1 = 20xx), times as DECIMAL(6,0) HHMMSS,
--     and 0 meaning "no date"
--   * one-letter status codes
--
-- Loaded from the WMS.* lab tables so 03_reconcile.sql can prove the legacy
-- query returns exactly what the original query returns.
-- Run as the instance owner:  db2 -tvf 01_create_lgcylib.sql
-- ============================================================================

CONNECT TO TIREWMS;

CREATE SCHEMA LGCYLIB;

-- Warehouse master
CREATE TABLE LGCYLIB.WHSMSTP (
    WHWHSE  CHAR(10)      NOT NULL,   -- warehouse code
    WHNAME  CHAR(40)      NOT NULL,   -- warehouse name
    PRIMARY KEY (WHWHSE)
);

-- Item master
CREATE TABLE LGCYLIB.ITMMSTP (
    IMSKU   CHAR(15)      NOT NULL,   -- SKU
    IMDESC  CHAR(40)      NOT NULL,   -- description
    IMSIZE  CHAR(12)      NOT NULL,   -- tire size
    IMUCST  DECIMAL(9,2)  NOT NULL,   -- unit cost
    PRIMARY KEY (IMSKU)
);

-- Location master
CREATE TABLE LGCYLIB.LOCMSTP (
    LMWHSE  CHAR(10)      NOT NULL,   -- warehouse code
    LMLOC   CHAR(12)      NOT NULL,   -- location code
    LMZONE  CHAR(10)      NOT NULL,   -- zone
    PRIMARY KEY (LMWHSE, LMLOC)
);

-- Inventory by lot and location
CREATE TABLE LGCYLIB.INVLOTP (
    ILWHSE  CHAR(10)      NOT NULL,   -- warehouse code
    ILLOC   CHAR(12)      NOT NULL,   -- location code
    ILSKU   CHAR(15)      NOT NULL,   -- SKU
    ILLOT   CHAR(12)      NOT NULL,   -- lot number
    ILSTAT  CHAR(1)       NOT NULL,   -- A=available H=hold D=damaged
    ILRCVD  DECIMAL(8,0)  NOT NULL DEFAULT 0,  -- received date YYYYMMDD (0 = none)
    ILRCVT  DECIMAL(6,0)  NOT NULL DEFAULT 0,  -- received time HHMMSS
    ILOHQT  DECIMAL(7,0)  NOT NULL DEFAULT 0,  -- on-hand qty
    ILRSQT  DECIMAL(7,0)  NOT NULL DEFAULT 0,  -- reserved (allocated) qty
    PRIMARY KEY (ILWHSE, ILLOC, ILSKU, ILLOT)
);

-- Lot attributes (DOT / manufacture)
CREATE TABLE LGCYLIB.LOTATRP (
    LASKU   CHAR(15)      NOT NULL,   -- SKU
    LALOT   CHAR(12)      NOT NULL,   -- lot number
    LADOT   CHAR(15)      NOT NULL,   -- DOT code
    LAMFWK  DECIMAL(2,0)  NOT NULL,   -- manufacture week
    LAMFYR  DECIMAL(4,0)  NOT NULL,   -- manufacture year
    LAMFGD  DECIMAL(7,0)  NOT NULL DEFAULT 0,  -- manufacture date CYYMMDD (0 = unknown)
    PRIMARY KEY (LASKU, LALOT)
);

-- Column text: on IBM i this is how you decode cryptic names (LABEL ON /
-- COMMENT ON, read back from QSYS2.SYSCOLUMNS). Db2 LUW keeps it in SYSCAT.COLUMNS.REMARKS.
COMMENT ON COLUMN LGCYLIB.INVLOTP.ILSTAT IS 'Stock status: A=available H=hold D=damaged';
COMMENT ON COLUMN LGCYLIB.INVLOTP.ILRCVD IS 'Received date, numeric YYYYMMDD, 0 = none';
COMMENT ON COLUMN LGCYLIB.INVLOTP.ILRCVT IS 'Received time, numeric HHMMSS';
COMMENT ON COLUMN LGCYLIB.INVLOTP.ILOHQT IS 'On-hand quantity';
COMMENT ON COLUMN LGCYLIB.INVLOTP.ILRSQT IS 'Reserved / allocated quantity';
COMMENT ON COLUMN LGCYLIB.LOTATRP.LAMFGD IS 'Manufacture date, numeric CYYMMDD (C: 0=19xx 1=20xx), 0 = unknown';
COMMENT ON COLUMN LGCYLIB.ITMMSTP.IMUCST IS 'Unit cost';

-- ---------------------------------------------------------------------------
-- Load from the WMS lab tables, converting to legacy formats
-- ---------------------------------------------------------------------------
INSERT INTO LGCYLIB.WHSMSTP
SELECT WAREHOUSE_CODE, WAREHOUSE_NAME FROM WMS.WAREHOUSE;

INSERT INTO LGCYLIB.ITMMSTP
SELECT SKU, DESCRIPTION, TIRE_SIZE, UNIT_COST FROM WMS.ITEM;

INSERT INTO LGCYLIB.LOCMSTP
SELECT w.WAREHOUSE_CODE, l.LOCATION_CODE, l.ZONE
FROM WMS.LOCATION l
JOIN WMS.WAREHOUSE w ON w.WAREHOUSE_ID = l.WAREHOUSE_ID;

INSERT INTO LGCYLIB.INVLOTP
SELECT w.WAREHOUSE_CODE, l.LOCATION_CODE, i.SKU, n.LOT_NUMBER,
       CASE n.STOCK_STATUS WHEN 'AVAILABLE' THEN 'A' WHEN 'HOLD' THEN 'H' WHEN 'DAMAGED' THEN 'D' ELSE '?' END,
       YEAR(n.RECEIVED_DATE) * 10000 + MONTH(n.RECEIVED_DATE) * 100 + DAY(n.RECEIVED_DATE),
       -- synthetic but valid receipt time (hh < 24, mm < 60, ss < 60)
       MOD(n.INVENTORY_ID * 7, 24) * 10000 + MOD(n.INVENTORY_ID * 31, 60) * 100 + MOD(n.INVENTORY_ID * 17, 60),
       n.ON_HAND_QTY, n.RESERVED_QTY
FROM WMS.INVENTORY n
JOIN WMS.ITEM i     ON i.ITEM_ID = n.ITEM_ID
JOIN WMS.LOCATION l ON l.LOCATION_ID = n.LOCATION_ID
JOIN WMS.WAREHOUSE w ON w.WAREHOUSE_ID = l.WAREHOUSE_ID;

INSERT INTO LGCYLIB.LOTATRP
SELECT i.SKU, la.LOT_NUMBER, la.DOT_CODE, la.MFG_WEEK, la.MFG_YEAR,
       (YEAR(la.MFG_DATE) - 1900) * 10000 + MONTH(la.MFG_DATE) * 100 + DAY(la.MFG_DATE)   -- CYYMMDD
FROM WMS.LOT_ATTRIBUTE la
JOIN WMS.ITEM i ON i.ITEM_ID = la.ITEM_ID;

-- Read-only access for the report service (bip-report) and ad hoc use
GRANT SELECT ON LGCYLIB.WHSMSTP TO USER RPTVIEW;
GRANT SELECT ON LGCYLIB.ITMMSTP TO USER RPTVIEW;
GRANT SELECT ON LGCYLIB.LOCMSTP TO USER RPTVIEW;
GRANT SELECT ON LGCYLIB.INVLOTP TO USER RPTVIEW;
GRANT SELECT ON LGCYLIB.LOTATRP TO USER RPTVIEW;

CONNECT RESET;
