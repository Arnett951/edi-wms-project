-- =====================================================
-- TABLE: dbo.EDI940_Address
-- =====================================================
IF OBJECT_ID('dbo.EDI940_Address', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.EDI940_Address (
        [AddressId] int IDENTITY(1,1) NOT NULL,
        [HeaderId] int NOT NULL,
        [EntityCode] nvarchar(20) NULL,
        [Name] nvarchar(100) NULL,
        [IdQualifier] nvarchar(20) NULL,
        [IdCode] nvarchar(50) NULL
    );
END;
