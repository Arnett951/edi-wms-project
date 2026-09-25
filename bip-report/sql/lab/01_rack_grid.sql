-- ============================================================================
-- Rack grid for the location heatmap (Db2 LUW lab, synthetic data).
--
--  * Adds AISLE / BAY / RACK_LEVEL to WMS.LOCATION.
--  * Creates a 4 aisle x 10 bay x 3 level rack per warehouse (120 each):
--    codes like A-03-2 (aisle A, bay 03, level 2); aisle A = PICK, B-D = BULK.
--  * Relocates the lots in the old PICK-01 / BULK-01 locations into the rack,
--    posting a MOVE transaction per lot so V_INVENTORY_RECONCILIATION stays at
--    zero differences (a relocation, not a silent UPDATE).
--  * QUALITY / RETURNS / RECEIVING stay as floor areas (no aisle/bay/level).
--
-- Backups first: BAK20260925.LOCATION / INVENTORY / INVENTORY_TRANSACTION.
-- Run once as the instance owner, all-or-nothing (no autocommit, stop on error):
--   db2 +c -s -tf 01_rack_grid.sql
-- ============================================================================

CONNECT TO TIREWMS;

CREATE SCHEMA BAK20260925;
CREATE TABLE BAK20260925.LOCATION AS (SELECT * FROM WMS.LOCATION) WITH DATA;
CREATE TABLE BAK20260925.INVENTORY AS (SELECT * FROM WMS.INVENTORY) WITH DATA;
CREATE TABLE BAK20260925.INVENTORY_TRANSACTION AS (SELECT * FROM WMS.INVENTORY_TRANSACTION) WITH DATA;

ALTER TABLE WMS.LOCATION
    ADD COLUMN AISLE      VARCHAR(4)
    ADD COLUMN BAY        SMALLINT
    ADD COLUMN RACK_LEVEL SMALLINT;

-- 120 rack locations per warehouse. LOCATION_ID is not an identity column:
-- continue after the current maximum.
INSERT INTO WMS.LOCATION (LOCATION_ID, WAREHOUSE_ID, LOCATION_CODE, ZONE, AISLE, BAY, RACK_LEVEL)
WITH A (AISLE, AIDX) AS (VALUES ('A', 0), ('B', 1), ('C', 2), ('D', 3)),
     B (BAY) AS (VALUES 1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
     L (LVL) AS (VALUES 1, 2, 3),
     W AS (SELECT WAREHOUSE_ID, ROW_NUMBER() OVER (ORDER BY WAREHOUSE_ID) - 1 AS WIDX FROM WMS.WAREHOUSE),
     BASE AS (SELECT MAX(LOCATION_ID) AS MAXID FROM WMS.LOCATION)
SELECT BASE.MAXID + W.WIDX * 120 + A.AIDX * 30 + (B.BAY - 1) * 3 + L.LVL,
       W.WAREHOUSE_ID,
       A.AISLE || '-' || RIGHT(DIGITS(SMALLINT(B.BAY)), 2) || '-' || CHAR(L.LVL),
       CASE WHEN A.AISLE = 'A' THEN 'PICK' ELSE 'BULK' END,
       A.AISLE, B.BAY, L.LVL
FROM W, A, B, L, BASE;

-- Which rack slot each old PICK / BULK lot moves to. Slot index t runs 0..29 in
-- aisle A (pick lots) or 0..89 across aisles B-D (bulk lots). Multiplying the row
-- number by a number coprime with the slot count spreads lots across the rack
-- with no two lots in one slot.
CREATE TABLE BAK20260925.RELOC_MAP AS (
    SELECT n.INVENTORY_ID, n.ITEM_ID, n.LOT_NUMBER, n.ON_HAND_QTY,
           n.LOCATION_ID AS FROM_LOCATION_ID, l.WAREHOUSE_ID, l.ZONE,
           ROW_NUMBER() OVER (PARTITION BY l.WAREHOUSE_ID, l.ZONE ORDER BY n.INVENTORY_ID) AS K
    FROM WMS.INVENTORY n JOIN WMS.LOCATION l ON l.LOCATION_ID = n.LOCATION_ID
    WHERE l.ZONE IN ('PICK', 'BULK') AND l.AISLE IS NULL
) WITH DATA;

ALTER TABLE BAK20260925.RELOC_MAP ADD COLUMN TO_LOCATION_ID INTEGER;

UPDATE BAK20260925.RELOC_MAP m
SET TO_LOCATION_ID = (
    SELECT r.LOCATION_ID FROM WMS.LOCATION r
    WHERE r.WAREHOUSE_ID = m.WAREHOUSE_ID
      AND r.AISLE IS NOT NULL
      AND (   (m.ZONE = 'PICK' AND r.AISLE = 'A'
               AND (r.BAY - 1) * 3 + (r.RACK_LEVEL - 1) = MOD(m.K * 7, 30))
           OR (m.ZONE = 'BULK' AND r.AISLE <> 'A'
               AND (CASE r.AISLE WHEN 'B' THEN 0 WHEN 'C' THEN 30 ELSE 60 END)
                   + (r.BAY - 1) * 3 + (r.RACK_LEVEL - 1) = MOD(m.K * 37, 90)))
);

-- The relocation, recorded as MOVE transactions (TRANSACTION_ID is an identity).
INSERT INTO WMS.INVENTORY_TRANSACTION
    (EVENT_REFERENCE, TRANSACTION_TYPE, TRANSACTION_TS, ITEM_ID, LOT_NUMBER,
     FROM_LOCATION_ID, TO_LOCATION_ID, QUANTITY, DOCUMENT_REFERENCE, OPERATOR_ID, REASON_CODE, NOTES)
SELECT 'RELOC-' || RTRIM(CHAR(m.INVENTORY_ID)), 'MOVE', TIMESTAMP('2026-09-25-10.00.00'),
       m.ITEM_ID, m.LOT_NUMBER, m.FROM_LOCATION_ID, m.TO_LOCATION_ID, m.ON_HAND_QTY,
       'RACK-RELOC-20260925', 'LAB-SETUP', 'RELOCATION',
       'Lab: relocate lot from floor location into rack grid for location heatmap'
FROM BAK20260925.RELOC_MAP m;

UPDATE WMS.INVENTORY n
SET LOCATION_ID = (SELECT m.TO_LOCATION_ID FROM BAK20260925.RELOC_MAP m WHERE m.INVENTORY_ID = n.INVENTORY_ID)
WHERE n.INVENTORY_ID IN (SELECT INVENTORY_ID FROM BAK20260925.RELOC_MAP);

GRANT SELECT ON WMS.LOCATION TO USER RPTVIEW;

COMMIT;

-- Checks: must be 0 differences, 48 rows, 3192 on hand, no lot in the old floor PICK/BULK,
-- and no rack slot holding two lots.
SELECT COUNT(*) AS RECON_ROWS, SUM(CASE WHEN DIFFERENCE <> 0 THEN 1 ELSE 0 END) AS RECON_DIFFS
FROM WMS.V_INVENTORY_RECONCILIATION;
SELECT COUNT(*) AS INV_ROWS, SUM(ON_HAND_QTY) AS ON_HAND FROM WMS.INVENTORY;
SELECT COUNT(*) AS LEFT_ON_FLOOR_PICK_BULK FROM WMS.INVENTORY n JOIN WMS.LOCATION l ON l.LOCATION_ID = n.LOCATION_ID
WHERE l.ZONE IN ('PICK', 'BULK') AND l.AISLE IS NULL;
SELECT COUNT(*) AS DOUBLED_UP_SLOTS FROM (
    SELECT n.LOCATION_ID FROM WMS.INVENTORY n JOIN WMS.LOCATION l ON l.LOCATION_ID = n.LOCATION_ID
    WHERE l.AISLE IS NOT NULL GROUP BY n.LOCATION_ID HAVING COUNT(*) > 1) x;
SELECT COUNT(*) AS NULL_TARGETS FROM BAK20260925.RELOC_MAP WHERE TO_LOCATION_ID IS NULL;

CONNECT RESET;
