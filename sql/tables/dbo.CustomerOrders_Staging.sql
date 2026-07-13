-- =====================================================
-- TABLE: dbo.CustomerOrders_Staging
-- =====================================================
CREATE TABLE dbo.CustomerOrders_Staging (
    [OrderID] int NULL,
    [CustomerID] int NULL,
    [CustomerName] varchar(64) NULL,
    [OrderDate] date NULL,
    [OrderAmount] decimal(10,2) NULL,
    [Status] varchar(50) NULL,
    [LoadBatchID] int NULL,
    [SKU] varchar(64) NULL,
    [Quantity] int NULL,
    [UnitPrice] smallmoney NULL,
    [ShipToState] varchar(46) NULL
);
