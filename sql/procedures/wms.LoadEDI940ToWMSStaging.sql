CREATE   PROCEDURE [wms].[LoadEDI940ToWMSStaging]
    @FileName NVARCHAR(255) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO wms.OrderHeader_Staging (
        SourceHeaderId,
        SourceFileName,
        WarehouseOrderNumber,
        OrderType,
        ShipDate,
        ShipToName,
        ShipToId
    )
    SELECT
        h.HeaderId,
        h.FileName,
        h.WarehouseOrderNumber,
        h.TransactionSetCode,
        TRY_CONVERT(DATE, h.ShipDate, 112),
        a.Name,
        a.IdCode
    FROM dbo.EDI940_Header h
    OUTER APPLY (
        SELECT TOP 1 *
        FROM dbo.EDI940_Address a
        WHERE a.HeaderId = h.HeaderId
          AND a.EntityCode = 'ST'
    ) a
    WHERE (@FileName IS NULL OR h.FileName = @FileName)
      AND NOT EXISTS (
          SELECT 1
          FROM wms.OrderHeader_Staging s
          WHERE s.SourceHeaderId = h.HeaderId
      );

    INSERT INTO wms.OrderDetail_Staging (
        WMSOrderHeaderStagingId,
        SourceDetailId,
        LineNumber,
        SKU,
        QuantityOrdered,
        UOM
    )
    SELECT
        s.WMSOrderHeaderStagingId,
        d.DetailId,
        ROW_NUMBER() OVER (
            PARTITION BY d.HeaderId
            ORDER BY d.DetailId
        ) AS LineNumber,
        COALESCE(d.ProductId, d.ProductQualifier),
        d.QuantityOrdered,
        d.UOM
    FROM dbo.EDI940_Detail d
    INNER JOIN wms.OrderHeader_Staging s
        ON s.SourceHeaderId = d.HeaderId
    WHERE (@FileName IS NULL OR s.SourceFileName = @FileName)
      AND NOT EXISTS (
          SELECT 1
          FROM wms.OrderDetail_Staging sd
          WHERE sd.SourceDetailId = d.DetailId
      );

    INSERT INTO wms.OrderIntegrationLog (
        SourceFileName,
        EventType,
        EventStatus,
        EventMessage
    )
    VALUES (
        @FileName,
        'LOAD_STAGING',
        'SUCCESS',
        'EDI 940 records loaded to WMS staging tables.'
    );
        UPDATE r
        SET ProcessStatus = 'STAGED'
        FROM dbo.EDI940_Raw r
        WHERE r.FileName = @FileName
          AND r.ProcessStatus = 'PARSED';
END;
