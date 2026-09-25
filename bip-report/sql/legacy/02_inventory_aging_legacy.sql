-- ============================================================================
-- Inventory Aging dataset against the legacy LGCYLIB files.
--
-- Same output columns (and so the same XML element names) as the WMS version,
-- so WAREHOUSE.rtf renders it unchanged. The conversion work is all here:
--   1. numeric YYYYMMDD / CYYMMDD  -> real DATE (0 -> NULL, never an error)
--   2. CHAR padding                -> TRIM() on everything that leaves the query
--   3. status codes                -> descriptive text
--   4. natural-key joins           -> join on every key column
-- Syntax works on Db2 for i (7.x) as well as Db2 LUW.
-- ============================================================================
WITH INV AS (
    SELECT il.*,
           -- DIGITS() keeps leading zeros, so TIMESTAMP_FORMAT always sees 8 characters
           CASE WHEN il.ILRCVD = 0 THEN NULL
                ELSE DATE(TIMESTAMP_FORMAT(DIGITS(il.ILRCVD), 'YYYYMMDD')) END AS RCV_DATE
    FROM LGCYLIB.INVLOTP il
    -- Filter on the RAW numeric column by converting the constant, not the column:
    -- the comparison stays index-friendly. "Received at least 7 days ago":
    WHERE il.ILRCVD > 0
      AND il.ILRCVD <= INTEGER(VARCHAR_FORMAT(CURRENT DATE - 7 DAYS, 'YYYYMMDD'))
),
LOT AS (
    SELECT la.*,
           -- CYYMMDD + 19000000 = YYYYMMDD  (1260413 -> 20260413, 0991231 -> 19991231)
           CASE WHEN la.LAMFGD = 0 THEN NULL
                ELSE DATE(TIMESTAMP_FORMAT(DIGITS(DECIMAL(la.LAMFGD + 19000000, 8, 0)), 'YYYYMMDD')) END AS MFG_DT
    FROM LGCYLIB.LOTATRP la
)
SELECT
    TRIM(inv.ILWHSE)                                   AS WAREHOUSE_CODE,
    TRIM(wh.WHNAME)                                    AS WAREHOUSE_NAME,
    TRIM(im.IMSKU)                                     AS SKU,
    TRIM(im.IMDESC)                                    AS DESCRIPTION,
    TRIM(im.IMSIZE)                                    AS TIRE_SIZE,
    TRIM(inv.ILLOC)                                    AS LOCATION_CODE,
    TRIM(lm.LMZONE)                                    AS ZONE,
    TRIM(inv.ILLOT)                                    AS LOT_NUMBER,
    TRIM(lot.LADOT)                                    AS DOT_CODE,
    lot.LAMFWK                                         AS MFG_WEEK,
    lot.LAMFYR                                         AS MFG_YEAR,
    lot.MFG_DT                                         AS MFG_DATE,
    inv.RCV_DATE                                       AS RECEIVED_DATE,
    MIN(inv.RCV_DATE) OVER (PARTITION BY inv.ILWHSE, inv.ILSKU)
                                                       AS OLDEST_RECEIVED_DATE,
    DAYS(CURRENT DATE) - DAYS(inv.RCV_DATE)            AS WAREHOUSE_AGE_DAYS,
    DAYS(CURRENT DATE) - DAYS(lot.MFG_DT)              AS TIRE_AGE_DAYS,
    CASE inv.ILSTAT WHEN 'A' THEN 'AVAILABLE'
                    WHEN 'H' THEN 'HOLD'
                    WHEN 'D' THEN 'DAMAGED'
                    ELSE 'UNKNOWN' END                 AS STOCK_STATUS,
    INTEGER(inv.ILOHQT)                                AS ON_HAND_QTY,
    INTEGER(inv.ILRSQT)                                AS RESERVED_QTY,
    CASE WHEN inv.ILSTAT = 'A' THEN INTEGER(inv.ILOHQT - inv.ILRSQT) ELSE 0 END
                                                       AS AVAILABLE_QTY,
    DECIMAL(inv.ILOHQT * im.IMUCST, 14, 2)             AS INVENTORY_VALUE
FROM INV inv
JOIN LGCYLIB.WHSMSTP wh ON wh.WHWHSE = inv.ILWHSE
JOIN LGCYLIB.ITMMSTP im ON im.IMSKU  = inv.ILSKU
JOIN LGCYLIB.LOCMSTP lm ON lm.LMWHSE = inv.ILWHSE      -- natural key: BOTH columns
                       AND lm.LMLOC  = inv.ILLOC
LEFT JOIN LOT lot       ON lot.LASKU = inv.ILSKU
                       AND lot.LALOT = inv.ILLOT
-- WHERE inv.ILWHSE = :P_FACILITY  -- BI Publisher data model bind parameter (CHAR compare ignores trailing blanks)
ORDER BY 1, 3, 12, 13
-- Read uncommitted: reporting never waits on (or locks) warehouse transactions.
-- (The Db2 CLP only treats ';' as the terminator when it ends the line.)
WITH UR;
