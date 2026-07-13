-- =====================================================
-- TABLE: dbo.EDI940_AuditLog
-- =====================================================
IF OBJECT_ID('dbo.EDI940_AuditLog', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.EDI940_AuditLog (
        [AuditID] int IDENTITY(1,1) NOT NULL,
        [RawID] int NULL,
        [FileName] varchar(255) NOT NULL,
        [Action] varchar(100) NOT NULL,
        [ActionDateTime] datetime2(7) NOT NULL,
        [ActionedBy] varchar(255) NULL DEFAULT (suser_sname()),
        [Details] nvarchar(MAX) NULL
    );
END;
