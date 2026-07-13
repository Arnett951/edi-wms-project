-- =====================================================
-- TABLE: dbo.EDI940_FileProcessLog
-- =====================================================
IF OBJECT_ID('dbo.EDI940_FileProcessLog', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.EDI940_FileProcessLog (
        [FileProcessLogId] int IDENTITY(1,1) NOT NULL,
        [FileName] nvarchar(255) NOT NULL,
        [ProcessStatus] nvarchar(50) NOT NULL,
        [ProcessDateTime] datetime2(7) NOT NULL DEFAULT (sysutcdatetime()),
        [ErrorMessage] nvarchar(MAX) NULL
    );
END;
