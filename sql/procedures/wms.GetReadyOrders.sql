CREATE   PROCEDURE wms.GetReadyOrders
    @MaxRows INT = 10
AS
BEGIN
    SET NOCOUNT ON;

    SELECT TOP (@MaxRows)
        WMSOrderHeaderStagingId,
        SourceHeaderId,
        SourceFileName,
        WarehouseOrderNumber,
        CustomerOrderNumber,
        OrderType,
        ShipDate,
        ShipToName,
        ShipToId,
        AttemptCount,
        CreatedDateTime
    FROM wms.OrderHeader_Staging
    WHERE IntegrationStatus IN ('READY', 'FAILED')
      AND AttemptCount < 3
    ORDER BY CreatedDateTime;
END;
