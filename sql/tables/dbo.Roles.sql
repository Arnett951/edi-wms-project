-- =====================================================
-- TABLE: dbo.Roles
-- =====================================================
IF OBJECT_ID('dbo.Roles', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Roles (
        [RoleId] int IDENTITY(1,1) NOT NULL,
        [RoleName] nvarchar(50) NOT NULL
    );
END;
