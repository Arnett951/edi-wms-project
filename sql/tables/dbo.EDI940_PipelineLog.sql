-- =====================================================
-- TABLE: dbo.EDI940_PipelineLog
-- =====================================================
CREATE TABLE dbo.EDI940_PipelineLog (
    [PipelineRunID] int IDENTITY(1,1) NOT NULL,
    [AdfPipelineRunId] varchar(255) NOT NULL,
    [PipelineStatus] varchar(50) NOT NULL,
    [ProcessDateTime] datetime2(7) NOT NULL,
    [FilesProcessed] int NULL,
    [FilesFailed] int NULL,
    [ExecutionDuration] int NULL,
    [CreatedDate] datetime2(7) NULL DEFAULT (sysutcdatetime())
);
