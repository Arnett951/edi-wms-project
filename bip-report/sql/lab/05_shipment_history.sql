-- ============================================================================
-- Shipment history: give every shipped order a shipment, trailer and BOL (synthetic).
--
-- 04_kpi_history.sql created shipped orders at the order level only. This links them:
--   * SHIP_TO rows for every customer the shipped orders went to (the store names in
--     the history, and the original lab Synthetic Dealer orders).
--   * One LTL shipment per facility + customer + ship date, each with its own VICS
--     17-digit BOL number (GS1 example prefix 0614141 + serial + mod-10 check digit,
--     computed below) and PRO number.
--   * All of a facility's shipments on a date share the LTL carrier's pickup trailer
--     and seal, the way LTL pickups work: one trailer, many BOLs.
--   * OUTBOUND_ORDER.SHIPMENT_ID is set for those orders.
-- The two trailers at the dock (SHIPMENT 1 and 2, LOADED) are untouched.
--
-- Backups first (BAK20260925.*_B4). Run once, all-or-nothing:
--   db2 +c -s -tf 05_shipment_history.sql
-- ============================================================================

CONNECT TO TIREWMS;

CREATE TABLE BAK20260925.SHIP_TO_B4 AS (SELECT * FROM WMS.SHIP_TO) WITH DATA;
CREATE TABLE BAK20260925.SHIPMENT_B4 AS (SELECT * FROM WMS.SHIPMENT) WITH DATA;
CREATE TABLE BAK20260925.OUTBOUND_ORDER_B4 AS (SELECT * FROM WMS.OUTBOUND_ORDER) WITH DATA;

-- ---------------------------------------------------------------- ship-to for every customer shipped to
-- Store number from the name (after the #); addresses are fictional, city by facility region.
INSERT INTO WMS.SHIP_TO
    (SHIP_TO_ID, SHIP_TO_NAME, ADDRESS_LINE1, CITY, STATE_CODE, POSTAL_CODE, LOCATION_NUMBER, CUSTOMER_ID)
WITH C AS (
    SELECT DISTINCT o.CUSTOMER_NAME, w.WAREHOUSE_CODE
    FROM WMS.OUTBOUND_ORDER o
    JOIN WMS.WAREHOUSE w ON w.WAREHOUSE_ID = o.WAREHOUSE_ID
    WHERE o.ORDER_STATUS = 'SHIPPED' AND o.SHIPMENT_ID IS NULL
      AND o.CUSTOMER_NAME NOT IN (SELECT SHIP_TO_NAME FROM WMS.SHIP_TO)
),
N AS (
    SELECT C.*, ROW_NUMBER() OVER (ORDER BY C.WAREHOUSE_CODE, C.CUSTOMER_NAME) AS RN
    FROM C
),
BASE AS (SELECT MAX(SHIP_TO_ID) AS MAXID FROM WMS.SHIP_TO)
SELECT BASE.MAXID + N.RN,
       N.CUSTOMER_NAME,
       TRIM(CHAR(100 + N.RN * 10)) || ' Sample Way',
       CASE WHEN N.WAREHOUSE_CODE = 'PERRIS'
            THEN CASE MOD(N.RN, 3) WHEN 0 THEN 'Riverside' WHEN 1 THEN 'Temecula' ELSE 'Corona' END
            ELSE CASE MOD(N.RN, 3) WHEN 0 THEN 'Marietta' WHEN 1 THEN 'Decatur' ELSE 'Kennesaw' END END,
       CASE WHEN N.WAREHOUSE_CODE = 'PERRIS' THEN 'CA' ELSE 'GA' END,
       CASE WHEN N.WAREHOUSE_CODE = 'PERRIS' THEN '925' ELSE '300' END || RIGHT(DIGITS(SMALLINT(N.RN)), 2),
       CASE WHEN LOCATE('#', N.CUSTOMER_NAME) > 0
            THEN SUBSTR(N.CUSTOMER_NAME, LOCATE('#', N.CUSTOMER_NAME) + 1, 4)
            ELSE 'D' || RIGHT(DIGITS(SMALLINT(N.RN)), 3) END,
       CASE WHEN LOCATE('#', N.CUSTOMER_NAME) > 0 THEN 'HWT-RETAIL' ELSE 'DEALER' END
FROM N, BASE;

-- ---------------------------------------------------------------- one shipment per facility + customer + ship date
CREATE TABLE BAK20260925.SHIP_MAP_B4 AS (
    SELECT o.WAREHOUSE_ID, o.CUSTOMER_NAME, o.ACTUAL_SHIP_DATE,
           ROW_NUMBER() OVER (ORDER BY o.ACTUAL_SHIP_DATE, o.WAREHOUSE_ID, o.CUSTOMER_NAME) AS RN
    FROM (SELECT DISTINCT WAREHOUSE_ID, CUSTOMER_NAME, ACTUAL_SHIP_DATE
          FROM WMS.OUTBOUND_ORDER
          WHERE ORDER_STATUS = 'SHIPPED' AND SHIPMENT_ID IS NULL) o
) WITH DATA;

INSERT INTO WMS.SHIPMENT
    (SHIPMENT_ID, BOL_NUMBER, WAREHOUSE_ID, SHIP_TO_ID, CARRIER_CODE, TRAILER_NUMBER, SEAL_NUMBER,
     PRO_NUMBER, FREIGHT_TERMS, SHIP_DATE, SHIPMENT_STATUS, TRAILER_LOADED_BY, FREIGHT_COUNTED_BY,
     SPECIAL_INSTRUCTIONS)
WITH BASE AS (SELECT MAX(SHIPMENT_ID) AS MAXID FROM WMS.SHIPMENT),
B AS (
    -- BOL serials continue after the two loaded trailers (serials 1 and 2)
    SELECT m.*, '0614141' || DIGITS(DECIMAL(BASE.MAXID + m.RN, 9, 0)) AS BODY, BASE.MAXID + m.RN AS NEW_ID
    FROM BAK20260925.SHIP_MAP_B4 m, BASE
)
SELECT B.NEW_ID,
       B.BODY || CHAR(MOD(10 - MOD(1 * INTEGER(SUBSTR(B.BODY, 1, 1)) + 3 * INTEGER(SUBSTR(B.BODY, 2, 1)) + 1 * INTEGER(SUBSTR(B.BODY, 3, 1)) + 3 * INTEGER(SUBSTR(B.BODY, 4, 1)) + 1 * INTEGER(SUBSTR(B.BODY, 5, 1)) + 3 * INTEGER(SUBSTR(B.BODY, 6, 1)) + 1 * INTEGER(SUBSTR(B.BODY, 7, 1)) + 3 * INTEGER(SUBSTR(B.BODY, 8, 1)) + 1 * INTEGER(SUBSTR(B.BODY, 9, 1)) + 3 * INTEGER(SUBSTR(B.BODY, 10, 1)) + 1 * INTEGER(SUBSTR(B.BODY, 11, 1)) + 3 * INTEGER(SUBSTR(B.BODY, 12, 1)) + 1 * INTEGER(SUBSTR(B.BODY, 13, 1)) + 3 * INTEGER(SUBSTR(B.BODY, 14, 1)) + 1 * INTEGER(SUBSTR(B.BODY, 15, 1)) + 3 * INTEGER(SUBSTR(B.BODY, 16, 1)), 10), 10)),
       B.WAREHOUSE_ID,
       t.SHIP_TO_ID,
       'DEMO-LTL',
       -- the LTL carrier's pickup trailer for this facility and day, shared by that day's BOLs
       'SLTX-' || CASE w.WAREHOUSE_CODE WHEN 'PERRIS' THEN 'PER' ELSE 'ATL' END || '-' || VARCHAR_FORMAT(B.ACTUAL_SHIP_DATE, 'MMDD'),
       'SL-7' || CASE w.WAREHOUSE_CODE WHEN 'PERRIS' THEN '1' ELSE '2' END || VARCHAR_FORMAT(B.ACTUAL_SHIP_DATE, 'MMDD'),
       '77' || DIGITS(DECIMAL(B.NEW_ID, 8, 0)),
       'PREPAID', B.ACTUAL_SHIP_DATE, 'SHIPPED', 'SHIPPER', 'DRIVER_PALLETS',
       CAST(NULL AS VARCHAR(200))
FROM B
JOIN WMS.WAREHOUSE w ON w.WAREHOUSE_ID = B.WAREHOUSE_ID
JOIN WMS.SHIP_TO t ON t.SHIP_TO_NAME = B.CUSTOMER_NAME;

-- ---------------------------------------------------------------- link the orders
UPDATE WMS.OUTBOUND_ORDER o
SET SHIPMENT_ID = (
    SELECT s.SHIPMENT_ID
    FROM WMS.SHIPMENT s
    JOIN WMS.SHIP_TO t ON t.SHIP_TO_ID = s.SHIP_TO_ID
    WHERE s.WAREHOUSE_ID = o.WAREHOUSE_ID
      AND t.SHIP_TO_NAME = o.CUSTOMER_NAME
      AND s.SHIP_DATE = o.ACTUAL_SHIP_DATE
      AND s.SHIPMENT_STATUS = 'SHIPPED')
WHERE o.ORDER_STATUS = 'SHIPPED' AND o.SHIPMENT_ID IS NULL;

DROP TABLE BAK20260925.SHIP_MAP_B4;

COMMIT;

-- Checks: every shipped order has a shipment; BOL numbers unique and 17 digits;
-- per facility, shipments (BOLs) and trailers (distinct pickups).
SELECT COUNT(*) AS SHIPPED_WITHOUT_SHIPMENT FROM WMS.OUTBOUND_ORDER
WHERE ORDER_STATUS = 'SHIPPED' AND SHIPMENT_ID IS NULL;
SELECT COUNT(*) AS BOLS, COUNT(DISTINCT BOL_NUMBER) AS DISTINCT_BOLS,
       SUM(CASE WHEN LENGTH(TRIM(BOL_NUMBER)) = 17 THEN 1 ELSE 0 END) AS SEVENTEEN_DIGIT
FROM WMS.SHIPMENT;
SELECT w.WAREHOUSE_CODE, s.SHIPMENT_STATUS, COUNT(*) AS SHIPMENTS, COUNT(DISTINCT s.TRAILER_NUMBER) AS TRAILERS
FROM WMS.SHIPMENT s JOIN WMS.WAREHOUSE w ON w.WAREHOUSE_ID = s.WAREHOUSE_ID
GROUP BY w.WAREHOUSE_CODE, s.SHIPMENT_STATUS ORDER BY 1, 2;

CONNECT RESET;
