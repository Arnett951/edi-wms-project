-- =====================================================
-- TABLE: wms.OrderIntegrationLog
-- =====================================================
IF OBJECT_ID('wms.OrderIntegrationLog', 'U') IS NULL
BEGIN
    CREATE TABLE wms.OrderIntegrationLog (
        [WMSOrderIntegrationLogId] int IDENTITY(1,1) NOT NULL,
        [WMSOrderHeaderStagingId] int NULL,
        [SourceHeaderId] int NULL,
        [SourceFileName] nvarchar(255) NULL,
        [EventType] nvarchar(50) NOT NULL,
        [EventStatus] nvarchar(30) NOT NULL,
        [EventMessage] nvarchar(MAX) NULL,
        [CreatedDateTime] datetime2(7) NOT NULL DEFAULT (sysutcdatetime())
    );
END;
