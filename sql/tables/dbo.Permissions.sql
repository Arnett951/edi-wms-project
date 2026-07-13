-- =====================================================
-- TABLE: dbo.Permissions
-- =====================================================
IF OBJECT_ID('dbo.Permissions', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Permissions (
        [PermissionId] int IDENTITY(1,1) NOT NULL,
        [PermissionName] nvarchar(100) NOT NULL
    );
END;
