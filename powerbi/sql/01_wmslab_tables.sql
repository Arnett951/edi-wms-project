-- =====================================================
-- Power BI copy of the Db2 lab tables (TIREWMS, schema WMS) in Azure SQL.
-- Schema wmslab mirrors WMS.* column for column, so the T-SQL view below is a
-- straight translation of bip-report/reports/inventory-aging/dataset.sql.
-- Loaded by powerbi/copy_db2_to_azuresql.py (full truncate + reload).
-- Kept out of sql/tables on purpose: deploy.py runs that folder in CI.
-- =====================================================
IF SCHEMA_ID('wmslab') IS NULL EXEC('CREATE SCHEMA wmslab');
GO

IF OBJECT_ID('wmslab.WAREHOUSE', 'U') IS NULL
CREATE TABLE wmslab.WAREHOUSE (
    WAREHOUSE_ID   int          NOT NULL PRIMARY KEY,
    WAREHOUSE_CODE varchar(12)  NOT NULL,
    WAREHOUSE_NAME varchar(80)  NOT NULL,
    ADDRESS_LINE1  varchar(60)  NULL,
    CITY           varchar(40)  NULL,
    STATE_CODE     char(2)      NULL,
    POSTAL_CODE    varchar(10)  NULL,
    SHIPPER_ID     varchar(20)  NULL
);
GO

IF OBJECT_ID('wmslab.ITEM', 'U') IS NULL
CREATE TABLE wmslab.ITEM (
    ITEM_ID          int           NOT NULL PRIMARY KEY,
    SKU              varchar(24)   NOT NULL,
    DESCRIPTION      varchar(100)  NOT NULL,
    TIRE_SIZE        varchar(24)   NOT NULL,
    UNIT_COST        decimal(12,2) NOT NULL,
    UNIT_WEIGHT_LBS  decimal(6,2)  NULL,
    UNITS_PER_PALLET smallint      NULL
);
GO

IF OBJECT_ID('wmslab.LOCATION', 'U') IS NULL
CREATE TABLE wmslab.LOCATION (
    LOCATION_ID   int         NOT NULL PRIMARY KEY,
    WAREHOUSE_ID  int         NOT NULL,
    LOCATION_CODE varchar(20) NOT NULL,
    ZONE          varchar(12) NOT NULL,
    AISLE         varchar(4)  NULL,
    BAY           smallint    NULL,
    RACK_LEVEL    smallint    NULL
);
GO

IF OBJECT_ID('wmslab.INVENTORY', 'U') IS NULL
CREATE TABLE wmslab.INVENTORY (
    INVENTORY_ID  int         NOT NULL PRIMARY KEY,
    LOCATION_ID   int         NOT NULL,
    ITEM_ID       int         NOT NULL,
    LOT_NUMBER    varchar(24) NOT NULL,
    RECEIVED_DATE date        NOT NULL,
    STOCK_STATUS  varchar(12) NOT NULL,
    ON_HAND_QTY   int         NOT NULL,
    RESERVED_QTY  int         NOT NULL
);
GO

IF OBJECT_ID('wmslab.LOT_ATTRIBUTE', 'U') IS NULL
CREATE TABLE wmslab.LOT_ATTRIBUTE (
    LOT_NUMBER varchar(24) NOT NULL,
    ITEM_ID    int         NOT NULL,
    DOT_CODE   varchar(40) NOT NULL,
    MFG_WEEK   smallint    NOT NULL,
    MFG_YEAR   smallint    NOT NULL,
    MFG_DATE   date        NOT NULL,
    CONSTRAINT PK_wmslab_LOT_ATTRIBUTE PRIMARY KEY (ITEM_ID, LOT_NUMBER)
);
GO

-- One row per copy run; the report shows the latest as "Data as of".
IF OBJECT_ID('wmslab.LOAD_LOG', 'U') IS NULL
CREATE TABLE wmslab.LOAD_LOG (
    LOAD_ID      int IDENTITY(1,1) NOT NULL PRIMARY KEY,
    LOADED_AT    datetime2(0) NOT NULL DEFAULT (sysutcdatetime()),
    SOURCE       varchar(40)  NOT NULL,
    ROW_COUNTS   varchar(400) NOT NULL
);
GO

-- Same rows and column names as the BIP dataset, all facilities (the Power BI
-- facility slicer replaces :P_FACILITY). Ages are as of the Power BI refresh.
CREATE OR ALTER VIEW wmslab.vw_InventoryAging AS
SELECT w.WAREHOUSE_CODE, w.WAREHOUSE_NAME, i.SKU, i.DESCRIPTION, i.TIRE_SIZE,
       l.LOCATION_CODE, l.ZONE, inv.LOT_NUMBER,
       la.DOT_CODE, la.MFG_WEEK, la.MFG_YEAR, la.MFG_DATE, inv.RECEIVED_DATE,
       MIN(inv.RECEIVED_DATE) OVER (PARTITION BY w.WAREHOUSE_CODE, i.SKU) AS OLDEST_RECEIVED_DATE,
       DATEDIFF(day, inv.RECEIVED_DATE, CAST(GETDATE() AS date)) AS WAREHOUSE_AGE_DAYS,
       DATEDIFF(day, la.MFG_DATE, CAST(GETDATE() AS date)) AS TIRE_AGE_DAYS,
       inv.STOCK_STATUS, inv.ON_HAND_QTY, inv.RESERVED_QTY,
       CASE WHEN inv.STOCK_STATUS = 'AVAILABLE' THEN inv.ON_HAND_QTY - inv.RESERVED_QTY ELSE 0 END AS AVAILABLE_QTY,
       CAST(inv.ON_HAND_QTY * i.UNIT_COST AS decimal(14,2)) AS INVENTORY_VALUE
FROM wmslab.INVENTORY inv
JOIN wmslab.ITEM i ON i.ITEM_ID = inv.ITEM_ID
JOIN wmslab.LOCATION l ON l.LOCATION_ID = inv.LOCATION_ID
JOIN wmslab.WAREHOUSE w ON w.WAREHOUSE_ID = l.WAREHOUSE_ID
LEFT JOIN wmslab.LOT_ATTRIBUTE la ON la.ITEM_ID = inv.ITEM_ID AND la.LOT_NUMBER = inv.LOT_NUMBER
WHERE DATEDIFF(day, inv.RECEIVED_DATE, CAST(GETDATE() AS date)) >= 7;
GO
