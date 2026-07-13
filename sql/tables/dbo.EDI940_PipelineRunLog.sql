-- =====================================================
-- TABLE: dbo.EDI940_PipelineRunLog
-- =====================================================
CREATE TABLE dbo.EDI940_PipelineRunLog (
    [PipelineRunLogId] int IDENTITY(1,1) NOT NULL,
    [PipelineRunId] nvarchar(100) NOT NULL,
    [PipelineStatus] nvarchar(50) NOT NULL,
    [ProcessDateTime] datetime2(7) NOT NULL DEFAULT (sysutcdatetime())
);
