-- =====================================================
-- TABLE: dbo.UserRoles
-- =====================================================
IF OBJECT_ID('dbo.UserRoles', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.UserRoles (
        [UserOid] nvarchar(64) NOT NULL,
        [RoleId] int NOT NULL,
        [GrantedAt] datetime2(7) NULL DEFAULT (sysutcdatetime())
    );
END;
