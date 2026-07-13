CREATE PROCEDURE dbo.usp_MergeCustomerOrders
AS
BEGIN

MERGE dbo.CustomerOrders AS target
USING (
    SELECT DISTINCT
        OrderID,
        CustomerName,
        OrderDate,
        SKU,
        Quantity,
        UnitPrice,
        ShipToState
    FROM dbo.CustomerOrders_Staging
) AS source
ON target.OrderID = source.OrderID

WHEN MATCHED THEN
UPDATE SET
    CustomerName = source.CustomerName,
    OrderDate = source.OrderDate,
    SKU = source.SKU,
    Quantity = source.Quantity,
    UnitPrice = source.UnitPrice,
    ShipToState = source.ShipToState

WHEN NOT MATCHED THEN
INSERT (
    OrderID,
    CustomerName,
    OrderDate,
    SKU,
    Quantity,
    UnitPrice,
    ShipToState
)
VALUES (
    source.OrderID,
    source.CustomerName,
    source.OrderDate,
    source.SKU,
    source.Quantity,
    source.UnitPrice,
    source.ShipToState
);

TRUNCATE TABLE dbo.CustomerOrders_Staging;

END
