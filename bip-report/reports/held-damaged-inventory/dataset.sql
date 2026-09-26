-- Held and Damaged Inventory dataset (lot level), one facility.
-- :P_FACILITY is bound by the report service, like a BI Publisher data model parameter.
-- Every lot whose STOCK_STATUS is not AVAILABLE (HOLD, DAMAGED, QC or any other value),
-- sorted by status, then oldest receipt first. The template groups rows by STOCK_STATUS
-- in this order and totals quantity and value per status.
-- Extended value = on-hand qty x ITEM.UNIT_COST, the same valuation as Inventory Aging.
-- The warehouse is the driving table, so a facility with nothing held still returns one
-- row (header fields only, detail columns null) and the template prints a no-lots message.
SELECT w.WAREHOUSE_CODE, w.WAREHOUSE_NAME,
       VARCHAR_FORMAT(CURRENT DATE, 'MM/DD/YYYY') AS RUN_DATE,
       inv.STOCK_STATUS, l.LOCATION_CODE, i.SKU, i.DESCRIPTION, inv.LOT_NUMBER,
       inv.ON_HAND_QTY,
       VARCHAR_FORMAT(inv.RECEIVED_DATE, 'MM/DD/YYYY') AS RECEIVED_DATE,
       DAYS(CURRENT DATE) - DAYS(inv.RECEIVED_DATE) AS AGE_DAYS,
       DECIMAL(inv.ON_HAND_QTY * i.UNIT_COST, 14, 2) AS EXTENDED_VALUE
FROM WMS.WAREHOUSE w
LEFT JOIN (WMS.LOCATION l
           JOIN WMS.INVENTORY inv ON inv.LOCATION_ID = l.LOCATION_ID
                                 AND inv.STOCK_STATUS <> 'AVAILABLE'
           JOIN WMS.ITEM i ON i.ITEM_ID = inv.ITEM_ID)
       ON l.WAREHOUSE_ID = w.WAREHOUSE_ID
WHERE w.WAREHOUSE_CODE = :P_FACILITY
ORDER BY inv.STOCK_STATUS, inv.RECEIVED_DATE, l.LOCATION_CODE, i.SKU, inv.LOT_NUMBER
WITH UR;
