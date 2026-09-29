-- ============================================================================
-- Trailer Manifest dataset: the facility's single most recent trailer.
--
-- Same single-trailer scope as the VICS BOL report: the trailer still at the
-- dock (LOADED) first, otherwise the most recent shipment. One row per customer
-- PO (customer, PO, quantity, weight); the template groups the rows by customer,
-- subtotals each PO and each customer, and prints a grand total.
--
-- Quantity and weight are computed exactly as the VICS BOL does (ordered qty,
-- weight = tires + 40 lb per pallet), so the grand total reconciles with the
-- VICS BOL for the same trailer. Trailer / seal / PRO and the totals ride on
-- every row so the template can print them outside the group loop.
-- ============================================================================
WITH SHIP AS (
    SELECT s.*
    FROM WMS.SHIPMENT s
    JOIN WMS.WAREHOUSE w ON w.WAREHOUSE_ID = s.WAREHOUSE_ID
    WHERE w.WAREHOUSE_CODE = :P_FACILITY
      AND s.SHIPMENT_STATUS IN ('LOADED', 'SHIPPED')
    -- The trailer still at the dock (LOADED) first; otherwise the most recent shipment
    ORDER BY CASE WHEN s.SHIPMENT_STATUS = 'LOADED' THEN 0 ELSE 1 END, s.SHIP_DATE DESC, s.SHIPMENT_ID DESC
    FETCH FIRST 1 ROW ONLY
),
LINES AS (
    -- One row per order line, same qty/weight arithmetic as the VICS BOL LINES CTE.
    SELECT o.CUSTOMER_NAME, o.CUSTOMER_PO, l.ORDERED_QTY AS QTY,
           l.ORDERED_QTY * i.UNIT_WEIGHT_LBS + CEILING(DECIMAL(l.ORDERED_QTY) / i.UNITS_PER_PALLET) * 40 AS WEIGHT
    FROM SHIP s
    JOIN WMS.OUTBOUND_ORDER o ON o.SHIPMENT_ID = s.SHIPMENT_ID
    JOIN WMS.OUTBOUND_LINE l ON l.ORDER_ID = o.ORDER_ID
    JOIN WMS.ITEM i ON i.ITEM_ID = l.ITEM_ID
),
PO_ROWS AS (
    -- One row per customer PO (the PO-level subtotal).
    SELECT CUSTOMER_NAME, CUSTOMER_PO,
           SUM(QTY) AS PO_QTY, INTEGER(SUM(WEIGHT)) AS PO_WEIGHT
    FROM LINES
    GROUP BY CUSTOMER_NAME, CUSTOMER_PO
),
TOT AS (
    -- Grand total over the order lines, not PO_ROWS: summing the already
    -- truncated PO_WEIGHTs could drift from the VICS BOL TOTAL_WEIGHT, which
    -- is INTEGER(SUM(WEIGHT)) over LINES.
    SELECT SUM(QTY) AS TOTAL_QTY, INTEGER(SUM(WEIGHT)) AS TOTAL_WEIGHT,
           (SELECT COUNT(*) FROM PO_ROWS) AS PO_COUNT
    FROM LINES
),
HDR AS (
    SELECT s.TRAILER_NUMBER, s.SEAL_NUMBER, s.PRO_NUMBER, s.BOL_NUMBER,
           VARCHAR_FORMAT(s.SHIP_DATE, 'MM/DD/YYYY') AS SHIP_DATE,
           s.SHIPMENT_STATUS,
           VARCHAR_FORMAT(CURRENT DATE, 'MM/DD/YYYY') AS RUN_DATE,
           w.WAREHOUSE_CODE, w.WAREHOUSE_NAME,
           c.CARRIER_NAME, c.SCAC,
           tot.TOTAL_QTY, tot.TOTAL_WEIGHT, tot.PO_COUNT
    FROM SHIP s
    JOIN WMS.WAREHOUSE w ON w.WAREHOUSE_ID = s.WAREHOUSE_ID
    JOIN WMS.CARRIER c ON c.CARRIER_CODE = s.CARRIER_CODE
    CROSS JOIN TOT tot
)
SELECT p.CUSTOMER_NAME, p.CUSTOMER_PO, p.PO_QTY, p.PO_WEIGHT, h.*
FROM PO_ROWS p CROSS JOIN HDR h
ORDER BY p.CUSTOMER_NAME, p.CUSTOMER_PO
WITH UR;
