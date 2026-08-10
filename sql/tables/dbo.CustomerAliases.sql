-- =====================================================
-- TABLE: dbo.CustomerAliases
-- Maps free-text customer names the chat sees ("Lowes", "Lowe's") to the
-- canonical ISASender code stored on dbo.EDI940_Raw ("LOW"), so lookups
-- work regardless of how the user or the AI model phrases the customer.
-- SQL Server's default collation is already case-insensitive, so this is
-- only needed for genuinely different spellings, not for LOW vs low.
-- =====================================================
IF OBJECT_ID('dbo.CustomerAliases', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.CustomerAliases (
        [AliasId] int IDENTITY(1,1) NOT NULL PRIMARY KEY,
        [Alias] nvarchar(100) NOT NULL,
        [CustomerCode] nvarchar(50) NOT NULL,
        [CreatedDateTime] datetime2(7) NOT NULL DEFAULT (sysutcdatetime())
    );
END;
