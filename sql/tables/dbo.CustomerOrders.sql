-- =====================================================
-- TABLE: dbo.CustomerOrders
-- =====================================================
CREATE TABLE dbo.CustomerOrders (
    [OrderID] int NULL,
    [CustomerID] int NULL,
    [OrderDate] date NULL,
    [OrderAmount] decimal(10,2) NULL,
    [Status] varchar(50) NULL,
    [CreatedDate] datetime NULL DEFAULT (getdate()),
    [ModifiedDate] datetime NULL DEFAULT (getdate()),
    [UnitPrice] smallmoney NULL,
    [ShipToState] varchar(64) NULL,
    [CustomerName] varchar(50) NULL,
    [sku] varchar(50) NULL,
    [quantity] int NULL
);
