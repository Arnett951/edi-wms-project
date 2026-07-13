-- =====================================================
-- TABLE: wms.OrderHeader_Staging
-- =====================================================
CREATE TABLE wms.OrderHeader_Staging (
    [WMSOrderHeaderStagingId] int IDENTITY(1,1) NOT NULL,
    [SourceSystem] nvarchar(50) NOT NULL DEFAULT ('EDI940'),
    [SourceHeaderId] int NOT NULL,
    [SourceFileName] nvarchar(255) NOT NULL,
    [WarehouseOrderNumber] nvarchar(50) NOT NULL,
    [CustomerOrderNumber] nvarchar(50) NULL,
    [OrderType] nvarchar(30) NULL,
    [ShipDate] date NULL,
    [ShipToName] nvarchar(100) NULL,
    [ShipToId] nvarchar(50) NULL,
    [IntegrationStatus] nvarchar(30) NOT NULL DEFAULT ('READY'),
    [AttemptCount] int NOT NULL DEFAULT ((0)),
    [LastAttemptDateTime] datetime2(7) NULL,
    [ErrorMessage] nvarchar(MAX) NULL,
    [CreatedDateTime] datetime2(7) NOT NULL DEFAULT (sysutcdatetime()),
    [ProcessedDateTime] datetime2(7) NULL
);
