-- =====================================================
-- TABLE: dbo.EDI940_ProcessingLog
-- =====================================================
CREATE TABLE dbo.EDI940_ProcessingLog (
    [LogID] int IDENTITY(1,1) NOT NULL,
    [FileName] varchar(255) NOT NULL,
    [ProcessStatus] varchar(50) NOT NULL,
    [ProcessDateTime] datetime2(7) NOT NULL,
    [ErrorMessage] nvarchar(MAX) NULL,
    [RecordsProcessed] int NULL,
    [CreatedDate] datetime2(7) NULL DEFAULT (sysutcdatetime())
);
