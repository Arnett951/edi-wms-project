-- =====================================================
-- TABLE: dbo.EDI940_Raw
-- CustomerReportedDateTime/CustomerReportedBy are set by the Funnel
-- Dashboard's "mark as reported" action once a file's exceptions have been
-- sent to the customer - see sql/views/dbo.vw_FileReconciliation.sql, which
-- treats a non-null CustomerReportedDateTime as an override that reconciles
-- the file to "Reported to Customer" regardless of its underlying
-- ProcessStatus/order outcome.
-- =====================================================
IF OBJECT_ID('dbo.EDI940_Raw', 'U') IS NULL
BEGIN
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
        [ISA_ControlNumber] varchar(50) NULL,
        [CustomerReportedDateTime] datetime2(7) NULL,
        [CustomerReportedBy] nvarchar(200) NULL
    );
END;
