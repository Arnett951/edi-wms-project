-- =====================================================
-- TABLE: dbo.EDI940_Header
-- =====================================================
IF OBJECT_ID('dbo.EDI940_Header', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.EDI940_Header (
        [HeaderId] int IDENTITY(1,1) NOT NULL,
        [RawId] int NOT NULL,
        [FileName] nvarchar(255) NOT NULL,
        [ISAControlNumber] nvarchar(50) NULL,
        [GSControlNumber] nvarchar(50) NULL,
        [STControlNumber] nvarchar(50) NULL,
        [TransactionSetCode] nvarchar(10) NULL,
        [WarehouseOrderNumber] nvarchar(50) NULL,
        [ShipDate] nvarchar(20) NULL,
        [CreatedDateTime] datetime2(7) NOT NULL DEFAULT (sysutcdatetime()),
        [STSegmentSeq] int NULL,
        [SESegmentSeq] int NULL
    );
END;
