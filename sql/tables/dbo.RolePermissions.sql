-- =====================================================
-- TABLE: dbo.RolePermissions
-- =====================================================
IF OBJECT_ID('dbo.RolePermissions', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.RolePermissions (
        [RoleId] int NOT NULL,
        [PermissionId] int NOT NULL
    );
END;
