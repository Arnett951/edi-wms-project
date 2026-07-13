-- =====================================================
-- TABLE: dbo.EDI940_Raw
-- =====================================================
CREATE TABLE dbo.EDI940_Raw (
    [RawId] int IDENTITY(1,1) NOT NULL,
    [FileName] nvarchar(255) NOT NULL,
    [RawEDIText] nvarchar(MAX) NULL,
    [LoadDateTime] datetime2(7) NOT NULL DEFAULT (sysutcdatetime()),
    [ProcessStatus] nvarchar(50) NOT NULL DEFAULT ('RAW_LOADED'),
    [ParsedDateTime] datetime2(7) NULL,
    [ErrorMessage] nvarchar(MAX) NULL,
    [ISASender] varchar(50) NULL,
    [ISAReceiver] varchar(50) NULL,
    [ISA_ControlNumber] varchar(50) NULL
);
