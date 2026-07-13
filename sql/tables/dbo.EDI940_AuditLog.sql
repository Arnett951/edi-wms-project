-- =====================================================
-- TABLE: dbo.EDI940_AuditLog
-- =====================================================
CREATE TABLE dbo.EDI940_AuditLog (
    [AuditID] int IDENTITY(1,1) NOT NULL,
    [RawID] int NULL,
    [FileName] varchar(255) NOT NULL,
    [Action] varchar(100) NOT NULL,
    [ActionDateTime] datetime2(7) NOT NULL,
    [ActionedBy] varchar(255) NULL DEFAULT (suser_sname()),
    [Details] nvarchar(MAX) NULL
);
