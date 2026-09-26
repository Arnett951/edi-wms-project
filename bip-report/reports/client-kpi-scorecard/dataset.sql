-- ============================================================================
-- Client KPI Scorecard: one facility, the 4 weeks ending on its last shipping day.
--
-- ROW_TYPE = KPI   one row per metric: value, target, status (MET / MISSED / INFO)
-- ROW_TYPE = WEEK  one row per week for the trend table (oldest week first)
-- Header fields (client, facility, period) are on every row.
--
-- Definitions (the part to agree with the client in writing):
--   On-time ship %  shipped orders with actual ship date on or before promised ship date
--   Unit fill rate  units shipped / units ordered, on orders shipped in the period
--   Past due        orders not shipped whose promised ship date is before period end
--   Shipments       distinct BOLs on orders shipped in the period; trailers = distinct pickup trailers
--   Dock-to-stock   hours from receipt to first putaway of the same item and lot
--   Aged > 180 days share of on-hand units received more than 180 days before period end
-- ============================================================================
WITH FAC AS (
    SELECT WAREHOUSE_ID, WAREHOUSE_CODE, WAREHOUSE_NAME
    FROM WMS.WAREHOUSE
    WHERE WAREHOUSE_CODE = :P_FACILITY
),
PERIOD AS (
    -- Fixed to the data (last shipping day), so the scorecard does not drift with today
    SELECT MAX(o.ACTUAL_SHIP_DATE) - 27 DAYS AS P_START, MAX(o.ACTUAL_SHIP_DATE) AS P_END
    FROM WMS.OUTBOUND_ORDER o
    JOIN FAC f ON f.WAREHOUSE_ID = o.WAREHOUSE_ID
    WHERE o.ORDER_STATUS = 'SHIPPED'
),
SHIPPED AS (
    -- One row per order shipped in the period, with its week bucket (0 = most recent)
    SELECT o.ORDER_ID, o.SHIPMENT_ID,
           CASE WHEN o.ACTUAL_SHIP_DATE <= o.PROMISED_SHIP_DATE THEN 1 ELSE 0 END AS ON_TIME,
           SUM(l.ORDERED_QTY) AS UNITS_ORDERED, SUM(l.SHIPPED_QTY) AS UNITS_SHIPPED,
           (DAYS(p.P_END) - DAYS(o.ACTUAL_SHIP_DATE)) / 7 AS WK
    FROM WMS.OUTBOUND_ORDER o
    JOIN FAC f ON f.WAREHOUSE_ID = o.WAREHOUSE_ID
    JOIN WMS.OUTBOUND_LINE l ON l.ORDER_ID = o.ORDER_ID
    CROSS JOIN PERIOD p
    WHERE o.ORDER_STATUS = 'SHIPPED'
      AND o.ACTUAL_SHIP_DATE BETWEEN p.P_START AND p.P_END
    GROUP BY o.ORDER_ID, o.SHIPMENT_ID, o.ACTUAL_SHIP_DATE, o.PROMISED_SHIP_DATE, p.P_END
),
RECEIPTS AS (
    -- Receipts into this facility in the period, with hours until first putaway
    SELECT r.QUANTITY,
           (DAYS(p.P_END) - DAYS(DATE(r.TRANSACTION_TS))) / 7 AS WK,
           (SELECT DECIMAL(TIMESTAMPDIFF(4, CHAR(MIN(m.TRANSACTION_TS) - r.TRANSACTION_TS)), 9, 2) / 60
            FROM WMS.INVENTORY_TRANSACTION m
            WHERE m.ITEM_ID = r.ITEM_ID AND m.LOT_NUMBER = r.LOT_NUMBER
              AND m.TRANSACTION_TYPE = 'MOVE' AND m.REASON_CODE = 'PUTAWAY'
              AND m.TRANSACTION_TS >= r.TRANSACTION_TS) AS DOCK_TO_STOCK_HRS
    FROM WMS.INVENTORY_TRANSACTION r
    JOIN WMS.LOCATION l ON l.LOCATION_ID = r.TO_LOCATION_ID
    JOIN FAC f ON f.WAREHOUSE_ID = l.WAREHOUSE_ID
    CROSS JOIN PERIOD p
    WHERE r.TRANSACTION_TYPE = 'RECEIPT'
      AND DATE(r.TRANSACTION_TS) BETWEEN p.P_START AND p.P_END
),
INV AS (
    -- Inventory on hand, aged as of period end
    SELECT SUM(n.ON_HAND_QTY) AS ON_HAND,
           SUM(n.ON_HAND_QTY * i.UNIT_COST) AS VALUE_ON_HAND,
           SUM(CASE WHEN DAYS(p.P_END) - DAYS(n.RECEIVED_DATE) > 180 THEN n.ON_HAND_QTY ELSE 0 END) AS AGED_180,
           SUM(CASE WHEN n.STOCK_STATUS <> 'AVAILABLE' THEN n.ON_HAND_QTY ELSE 0 END) AS NOT_AVAILABLE
    FROM WMS.INVENTORY n
    JOIN WMS.ITEM i ON i.ITEM_ID = n.ITEM_ID
    JOIN WMS.LOCATION l ON l.LOCATION_ID = n.LOCATION_ID
    JOIN FAC f ON f.WAREHOUSE_ID = l.WAREHOUSE_ID
    CROSS JOIN PERIOD p
),
M AS (
    -- Every metric as a number, in one row
    SELECT (SELECT COUNT(*) FROM SHIPPED) AS ORDERS_SHIPPED,
           (SELECT COALESCE(SUM(UNITS_SHIPPED), 0) FROM SHIPPED) AS UNITS_SHIPPED,
           (SELECT COUNT(DISTINCT SHIPMENT_ID) FROM SHIPPED) AS SHIPMENTS,
           (SELECT COUNT(DISTINCT sh.TRAILER_NUMBER) FROM SHIPPED x
             JOIN WMS.SHIPMENT sh ON sh.SHIPMENT_ID = x.SHIPMENT_ID) AS TRAILERS,
           (SELECT ROUND(100.0 * SUM(ON_TIME) / NULLIF(COUNT(*), 0), 1) FROM SHIPPED) AS ON_TIME_PCT,
           (SELECT ROUND(100.0 * SUM(UNITS_SHIPPED) / NULLIF(SUM(UNITS_ORDERED), 0), 1) FROM SHIPPED) AS FILL_PCT,
           (SELECT COUNT(*) FROM WMS.OUTBOUND_ORDER o JOIN FAC f ON f.WAREHOUSE_ID = o.WAREHOUSE_ID
             CROSS JOIN PERIOD p
             WHERE o.ORDER_STATUS <> 'SHIPPED' AND o.PROMISED_SHIP_DATE < p.P_END) AS PAST_DUE,
           (SELECT COUNT(*) FROM RECEIPTS) AS RECEIPT_COUNT,
           (SELECT COALESCE(SUM(QUANTITY), 0) FROM RECEIPTS) AS UNITS_RECEIVED,
           (SELECT ROUND(AVG(DOCK_TO_STOCK_HRS), 1) FROM RECEIPTS) AS DOCK_TO_STOCK_HRS,
           (SELECT ON_HAND FROM INV) AS ON_HAND,
           (SELECT VALUE_ON_HAND FROM INV) AS VALUE_ON_HAND,
           (SELECT ROUND(100.0 * AGED_180 / NULLIF(ON_HAND, 0), 1) FROM INV) AS AGED_180_PCT,
           (SELECT NOT_AVAILABLE FROM INV) AS NOT_AVAILABLE
    FROM SYSIBM.SYSDUMMY1
),
KPI AS (
    -- One row per metric: display value, target, status. Targets are illustrative SLA terms.
    SELECT 1 AS SEQ, 'Outbound' AS SECTION, 'Orders shipped' AS KPI_NAME,
           VARCHAR(ORDERS_SHIPPED) AS KPI_VALUE, '' AS KPI_TARGET, 'INFO' AS KPI_STATUS FROM M
    UNION ALL SELECT 2, 'Outbound', 'Units shipped', TRIM(VARCHAR_FORMAT(UNITS_SHIPPED, '999,999,990')), '', 'INFO' FROM M
    UNION ALL SELECT 3, 'Outbound', 'Shipments (BOLs)', VARCHAR(SHIPMENTS), '', 'INFO' FROM M
    UNION ALL SELECT 4, 'Outbound', 'Trailers dispatched', VARCHAR(TRAILERS), '', 'INFO' FROM M
    UNION ALL SELECT 5, 'Outbound', 'On-time ship %', TRIM(VARCHAR_FORMAT(ON_TIME_PCT, '990.0')) || '%', '>= 98.0%',
           CASE WHEN ON_TIME_PCT >= 98 THEN 'MET' ELSE 'MISSED' END FROM M
    UNION ALL SELECT 6, 'Outbound', 'Unit fill rate', TRIM(VARCHAR_FORMAT(FILL_PCT, '990.0')) || '%', '>= 99.5%',
           CASE WHEN FILL_PCT >= 99.5 THEN 'MET' ELSE 'MISSED' END FROM M
    UNION ALL SELECT 7, 'Outbound', 'Open orders past due', VARCHAR(PAST_DUE), '0',
           CASE WHEN PAST_DUE = 0 THEN 'MET' ELSE 'MISSED' END FROM M
    UNION ALL SELECT 8, 'Inbound', 'Receipts', VARCHAR(RECEIPT_COUNT), '', 'INFO' FROM M
    UNION ALL SELECT 9, 'Inbound', 'Units received', TRIM(VARCHAR_FORMAT(UNITS_RECEIVED, '999,999,990')), '', 'INFO' FROM M
    UNION ALL SELECT 10, 'Inbound', 'Avg dock-to-stock (hours)',
           COALESCE(TRIM(VARCHAR_FORMAT(DOCK_TO_STOCK_HRS, '990.0')), 'n/a'), '<= 24.0',
           CASE WHEN DOCK_TO_STOCK_HRS IS NULL THEN 'INFO' WHEN DOCK_TO_STOCK_HRS <= 24 THEN 'MET' ELSE 'MISSED' END FROM M
    UNION ALL SELECT 11, 'Inventory', 'Units on hand', TRIM(VARCHAR_FORMAT(ON_HAND, '999,999,990')), '', 'INFO' FROM M
    UNION ALL SELECT 12, 'Inventory', 'Inventory value', '$' || TRIM(VARCHAR_FORMAT(VALUE_ON_HAND, '999,999,990')), '', 'INFO' FROM M
    UNION ALL SELECT 13, 'Inventory', 'Units aged over 180 days', TRIM(VARCHAR_FORMAT(AGED_180_PCT, '990.0')) || '%', '<= 10.0%',
           CASE WHEN AGED_180_PCT <= 10 THEN 'MET' ELSE 'MISSED' END FROM M
    UNION ALL SELECT 14, 'Inventory', 'Units on hold or damaged', TRIM(VARCHAR_FORMAT(NOT_AVAILABLE, '999,999,990')), '', 'INFO' FROM M
),
W (WK) AS (VALUES 0, 1, 2, 3),
WEEKS AS (
    -- One row per week, including weeks with no activity
    SELECT w.WK,
           VARCHAR_FORMAT(p.P_END - (w.WK * 7) DAYS, 'MM/DD') AS WEEK_ENDING,
           (SELECT COUNT(*) FROM SHIPPED s WHERE s.WK = w.WK) AS WK_ORDERS,
           (SELECT COALESCE(SUM(UNITS_SHIPPED), 0) FROM SHIPPED s WHERE s.WK = w.WK) AS WK_UNITS,
           (SELECT ROUND(100.0 * SUM(ON_TIME) / NULLIF(COUNT(*), 0), 1) FROM SHIPPED s WHERE s.WK = w.WK) AS WK_ON_TIME,
           (SELECT ROUND(100.0 * SUM(UNITS_SHIPPED) / NULLIF(SUM(UNITS_ORDERED), 0), 1) FROM SHIPPED s WHERE s.WK = w.WK) AS WK_FILL,
           (SELECT COUNT(*) FROM RECEIPTS r WHERE r.WK = w.WK) AS WK_RECEIPTS
    FROM W CROSS JOIN PERIOD p
),
HDR AS (
    SELECT 'Hello World Tire' AS CLIENT_NAME, f.WAREHOUSE_CODE AS FACILITY_CODE, f.WAREHOUSE_NAME AS FACILITY_NAME,
           VARCHAR_FORMAT(p.P_START, 'MM/DD/YYYY') AS PERIOD_START, VARCHAR_FORMAT(p.P_END, 'MM/DD/YYYY') AS PERIOD_END,
           (SELECT COUNT(*) FROM KPI WHERE KPI_STATUS = 'MET') AS KPIS_MET,
           (SELECT COUNT(*) FROM KPI WHERE KPI_STATUS IN ('MET', 'MISSED')) AS KPIS_WITH_TARGET
    FROM FAC f CROSS JOIN PERIOD p
)
SELECT 'KPI' AS ROW_TYPE, k.SEQ AS SORT_KEY, k.SECTION, k.KPI_NAME, k.KPI_VALUE, k.KPI_TARGET, k.KPI_STATUS,
       CAST(NULL AS VARCHAR(10)) AS WEEK_ENDING, CAST(NULL AS INTEGER) AS WK_ORDERS, CAST(NULL AS INTEGER) AS WK_UNITS,
       CAST(NULL AS VARCHAR(10)) AS WK_ON_TIME, CAST(NULL AS VARCHAR(10)) AS WK_FILL, CAST(NULL AS INTEGER) AS WK_RECEIPTS,
       h.*
FROM KPI k CROSS JOIN HDR h
UNION ALL
SELECT 'WEEK', 100 - wk.WK, NULL, NULL, NULL, NULL, NULL,
       wk.WEEK_ENDING, wk.WK_ORDERS, wk.WK_UNITS,
       COALESCE(TRIM(VARCHAR_FORMAT(wk.WK_ON_TIME, '990.0')) || '%', '-'),
       COALESCE(TRIM(VARCHAR_FORMAT(wk.WK_FILL, '990.0')) || '%', '-'),
       wk.WK_RECEIPTS,
       h.*
FROM WEEKS wk CROSS JOIN HDR h
ORDER BY 1, 2
WITH UR;
