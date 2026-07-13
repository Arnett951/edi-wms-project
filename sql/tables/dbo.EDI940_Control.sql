-- =====================================================
-- TABLE: dbo.EDI940_Control
-- =====================================================
CREATE TABLE dbo.EDI940_Control (
    [ControlId] int IDENTITY(1,1) NOT NULL,
    [HeaderId] int NOT NULL,
    [SE01_SegmentCount] int NULL,
    [SE02_ControlNumber] nvarchar(50) NULL,
    [GE01_TransactionCount] int NULL,
    [GE02_GroupControlNumber] nvarchar(50) NULL,
    [IEA01_GroupCount] int NULL,
    [IEA02_InterchangeControlNumber] nvarchar(50) NULL
);
