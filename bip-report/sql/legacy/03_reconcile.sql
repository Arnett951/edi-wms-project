-- ============================================================================
-- Reconciliation: prove the legacy-format query returns exactly the same rows
-- as the original WMS query. Both counts must be 0 (and the totals equal).
-- This is the habit to bring to any converted or rewritten report: diff old vs new.
-- ============================================================================
WITH W AS (   -- original dataset (WMS.* tables, real DATE columns)
    SELECT w.WAREHOUSE_CODE, w.WAREHOUSE_NAME, i.SKU, i.DESCRIPTION, i.TIRE_SIZE,
           l.LOCATION_CODE, l.ZONE, inv.LOT_NUMBER,
           la.DOT_CODE, la.MFG_WEEK, la.MFG_YEAR, la.MFG_DATE, inv.RECEIVED_DATE,
           MIN(inv.RECEIVED_DATE) OVER (PARTITION BY w.WAREHOUSE_CODE, i.SKU) AS OLDEST_RECEIVED_DATE,
           DAYS(CURRENT DATE) - DAYS(inv.RECEIVED_DATE) AS WAREHOUSE_AGE_DAYS,
           DAYS(CURRENT DATE) - DAYS(la.MFG_DATE) AS TIRE_AGE_DAYS,
           inv.STOCK_STATUS, inv.ON_HAND_QTY, inv.RESERVED_QTY,
           CASE WHEN inv.STOCK_STATUS = 'AVAILABLE' THEN inv.ON_HAND_QTY - inv.RESERVED_QTY ELSE 0 END AS AVAILABLE_QTY,
           DECIMAL(inv.ON_HAND_QTY * i.UNIT_COST, 14, 2) AS INVENTORY_VALUE
    FROM WMS.INVENTORY inv
    JOIN WMS.ITEM i ON i.ITEM_ID = inv.ITEM_ID
    JOIN WMS.LOCATION l ON l.LOCATION_ID = inv.LOCATION_ID
    JOIN WMS.WAREHOUSE w ON w.WAREHOUSE_ID = l.WAREHOUSE_ID
    LEFT JOIN WMS.LOT_ATTRIBUTE la ON la.ITEM_ID = inv.ITEM_ID AND la.LOT_NUMBER = inv.LOT_NUMBER
    WHERE DAYS(CURRENT DATE) - DAYS(inv.RECEIVED_DATE) >= 7
),
INV AS (      -- legacy dataset (LGCYLIB.* files), same logic as 02_inventory_aging_legacy.sql
    SELECT il.*,
           CASE WHEN il.ILRCVD = 0 THEN NULL
                ELSE DATE(TIMESTAMP_FORMAT(DIGITS(il.ILRCVD), 'YYYYMMDD')) END AS RCV_DATE
    FROM LGCYLIB.INVLOTP il
    WHERE il.ILRCVD > 0
      AND il.ILRCVD <= INTEGER(VARCHAR_FORMAT(CURRENT DATE - 7 DAYS, 'YYYYMMDD'))
),
LOT AS (
    SELECT la.*,
           CASE WHEN la.LAMFGD = 0 THEN NULL
                ELSE DATE(TIMESTAMP_FORMAT(DIGITS(DECIMAL(la.LAMFGD + 19000000, 8, 0)), 'YYYYMMDD')) END AS MFG_DT
    FROM LGCYLIB.LOTATRP la
),
L AS (
    SELECT TRIM(inv.ILWHSE) AS WAREHOUSE_CODE, TRIM(wh.WHNAME) AS WAREHOUSE_NAME, TRIM(im.IMSKU) AS SKU,
           TRIM(im.IMDESC) AS DESCRIPTION, TRIM(im.IMSIZE) AS TIRE_SIZE, TRIM(inv.ILLOC) AS LOCATION_CODE,
           TRIM(lm.LMZONE) AS ZONE, TRIM(inv.ILLOT) AS LOT_NUMBER, TRIM(lot.LADOT) AS DOT_CODE,
           lot.LAMFWK AS MFG_WEEK, lot.LAMFYR AS MFG_YEAR, lot.MFG_DT AS MFG_DATE, inv.RCV_DATE AS RECEIVED_DATE,
           MIN(inv.RCV_DATE) OVER (PARTITION BY inv.ILWHSE, inv.ILSKU) AS OLDEST_RECEIVED_DATE,
           DAYS(CURRENT DATE) - DAYS(inv.RCV_DATE) AS WAREHOUSE_AGE_DAYS,
           DAYS(CURRENT DATE) - DAYS(lot.MFG_DT) AS TIRE_AGE_DAYS,
           CASE inv.ILSTAT WHEN 'A' THEN 'AVAILABLE' WHEN 'H' THEN 'HOLD' WHEN 'D' THEN 'DAMAGED' ELSE 'UNKNOWN' END AS STOCK_STATUS,
           INTEGER(inv.ILOHQT) AS ON_HAND_QTY, INTEGER(inv.ILRSQT) AS RESERVED_QTY,
           CASE WHEN inv.ILSTAT = 'A' THEN INTEGER(inv.ILOHQT - inv.ILRSQT) ELSE 0 END AS AVAILABLE_QTY,
           DECIMAL(inv.ILOHQT * im.IMUCST, 14, 2) AS INVENTORY_VALUE
    FROM INV inv
    JOIN LGCYLIB.WHSMSTP wh ON wh.WHWHSE = inv.ILWHSE
    JOIN LGCYLIB.ITMMSTP im ON im.IMSKU = inv.ILSKU
    JOIN LGCYLIB.LOCMSTP lm ON lm.LMWHSE = inv.ILWHSE AND lm.LMLOC = inv.ILLOC
    LEFT JOIN LOT lot ON lot.LASKU = inv.ILSKU AND lot.LALOT = inv.ILLOT
)
SELECT 'rows only in original' AS CHECK_NAME, COUNT(*) AS RESULT FROM (SELECT * FROM W EXCEPT ALL SELECT * FROM L) x
UNION ALL
SELECT 'rows only in legacy',   COUNT(*) FROM (SELECT * FROM L EXCEPT ALL SELECT * FROM W) x
UNION ALL
SELECT 'original row count',    COUNT(*) FROM W
UNION ALL
SELECT 'legacy row count',      COUNT(*) FROM L
UNION ALL
SELECT 'original total value',  BIGINT(SUM(INVENTORY_VALUE)) FROM W
UNION ALL
SELECT 'legacy total value',    BIGINT(SUM(INVENTORY_VALUE)) FROM L
WITH UR;
