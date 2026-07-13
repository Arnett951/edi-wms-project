-- =====================================================
-- TABLE: dbo.UserActivityLog
-- =====================================================
IF OBJECT_ID('dbo.UserActivityLog', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.UserActivityLog (
        [EventId] int IDENTITY(1,1) NOT NULL,
        [UserOid] varchar(100) NOT NULL,
        [EventType] varchar(50) NOT NULL,
        [EventName] varchar(150) NOT NULL,
        [EventDateTime] datetime2(7) NOT NULL DEFAULT (sysutcdatetime()),
        [Details] nvarchar(MAX) NULL
    );
END;
