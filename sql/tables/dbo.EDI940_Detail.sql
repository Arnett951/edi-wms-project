-- =====================================================
-- TABLE: dbo.EDI940_Detail
-- =====================================================
CREATE TABLE dbo.EDI940_Detail (
    [DetailId] int IDENTITY(1,1) NOT NULL,
    [HeaderId] int NOT NULL,
    [LineNumber] nvarchar(50) NULL,
    [QuantityOrdered] decimal(18,4) NULL,
    [UOM] nvarchar(20) NULL,
    [ProductQualifier] nvarchar(20) NULL,
    [ProductId] nvarchar(100) NULL,
    [ProductQualifier2] nvarchar(20) NULL,
    [ProductId2] nvarchar(100) NULL
);
