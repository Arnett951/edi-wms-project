-- =====================================================
-- TABLE: dbo.UserGroups
-- =====================================================
IF OBJECT_ID('dbo.UserGroups', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.UserGroups (
        [UserOid] nvarchar(64) NOT NULL,
        [GroupId] int NOT NULL
    );
END;
