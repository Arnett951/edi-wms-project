-- =====================================================
-- TABLE: dbo.PipelineLoadLog
-- =====================================================
IF OBJECT_ID('dbo.PipelineLoadLog', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.PipelineLoadLog (
        [LoadLogID] int IDENTITY(1,1) NOT NULL,
        [PipelineName] nvarchar(255) NOT NULL,
        [PipelineRunID] nvarchar(255) NOT NULL,
        [ActivityName] nvarchar(255) NULL,
        [LoadStatus] nvarchar(50) NOT NULL,
        [RowsCopied] int NULL DEFAULT ((0)),
        [RowsAffected] int NULL DEFAULT ((0)),
        [ErrorCode] nvarchar(50) NULL,
        [ErrorMessage] nvarchar(MAX) NULL,
        [ErrorStackTrace] nvarchar(MAX) NULL,
        [LoadStartTime] datetime NULL,
        [LoadEndTime] datetime NULL,
        [LoadDurationSeconds] int NULL,
        [SourceFilePath] nvarchar(500) NULL,
        [LoadBatchID] int NULL,
        [CreatedDate] datetime NULL DEFAULT (getdate()),
        [ModifiedDate] datetime NULL DEFAULT (getdate()),
        [FileName] varchar(500) NULL,
        [RowsLoaded] int NULL,
        [MessageText] varchar(MAX) NULL,
        [RunDateTime] smalldatetime NULL
    );
END;
