-- =====================================================
-- TABLE: dbo.EDI940_FileProcessLog
-- =====================================================
CREATE TABLE dbo.EDI940_FileProcessLog (
    [FileProcessLogId] int IDENTITY(1,1) NOT NULL,
    [FileName] nvarchar(255) NOT NULL,
    [ProcessStatus] nvarchar(50) NOT NULL,
    [ProcessDateTime] datetime2(7) NOT NULL DEFAULT (sysutcdatetime()),
    [ErrorMessage] nvarchar(MAX) NULL
);
