-- =====================================================
-- TABLE: dbo.Groups
-- =====================================================
IF OBJECT_ID('dbo.Groups', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Groups (
        [GroupId] int IDENTITY(1,1) NOT NULL,
        [GroupName] nvarchar(100) NOT NULL
    );
END;
