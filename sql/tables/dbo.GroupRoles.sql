-- =====================================================
-- TABLE: dbo.GroupRoles
-- =====================================================
IF OBJECT_ID('dbo.GroupRoles', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.GroupRoles (
        [GroupId] int NOT NULL,
        [RoleId] int NOT NULL
    );
END;
