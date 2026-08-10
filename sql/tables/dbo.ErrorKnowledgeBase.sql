-- =====================================================
-- TABLE: dbo.ErrorKnowledgeBase
-- Maps a substring of a raw EDI940_Raw.ErrorMessage (set by
-- dbo.ParseEDI940RawByFile's CATCH block, see ERROR_MESSAGE()) to a
-- plain-English explanation and remediation step, so the chat can turn a
-- bare SQL/parse error into something an ops user can act on.
-- Schema-only, like every other file in sql/tables/ -- the deploy pipeline's
-- SQL principal has DDL rights only, not SELECT/INSERT (see
-- dbo.CustomerAliases.sql), so seed rows separately with your own
-- data-plane access.
-- =====================================================
IF OBJECT_ID('dbo.ErrorKnowledgeBase', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ErrorKnowledgeBase (
        [ErrorKnowledgeBaseId] int IDENTITY(1,1) NOT NULL PRIMARY KEY,
        [ErrorPattern] nvarchar(200) NOT NULL,
        [Explanation] nvarchar(500) NOT NULL,
        [RemediationStep] nvarchar(500) NULL,
        [CreatedDateTime] datetime2(7) NOT NULL DEFAULT (sysutcdatetime())
    );
END;
