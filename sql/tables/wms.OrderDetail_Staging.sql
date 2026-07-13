-- =====================================================
-- TABLE: wms.OrderDetail_Staging
-- =====================================================
IF OBJECT_ID('wms.OrderDetail_Staging', 'U') IS NULL
BEGIN
    CREATE TABLE wms.OrderDetail_Staging (
        [WMSOrderDetailStagingId] int IDENTITY(1,1) NOT NULL,
        [WMSOrderHeaderStagingId] int NOT NULL,
        [SourceDetailId] int NOT NULL,
        [LineNumber] int NOT NULL,
        [SKU] nvarchar(100) NOT NULL,
        [QuantityOrdered] decimal(18,4) NOT NULL,
        [UOM] nvarchar(20) NULL,
        [LotNumber] nvarchar(50) NULL,
        [SerialNumber] nvarchar(50) NULL,
        [CreatedDateTime] datetime2(7) NOT NULL DEFAULT (sysutcdatetime())
    );
END;
