-- =====================================================
-- TABLE: dbo.ChangeRequests
-- Backs the AI change-request pipeline (see docs/ai-delivery-pipeline.md).
-- Replaces the markdown-file storage under api/change-requests/ -- files on
-- a zip-deployed Azure App Service get wiped on every redeploy, and a SQL
-- table is also the same store local dev and the deployed API both read
-- from, closing the local-vs-deployed split that's been a recurring problem.
-- =====================================================
IF OBJECT_ID('dbo.ChangeRequests', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ChangeRequests (
        [CRNumber] int NOT NULL,
        [Title] nvarchar(255) NOT NULL,
        [Tier] char(1) NOT NULL,
        [TierLabel] nvarchar(255) NULL,
        [Status] nvarchar(255) NOT NULL,
        [OriginalRequest] nvarchar(MAX) NOT NULL,
        [ClarificationJson] nvarchar(MAX) NULL,
        [RiskNotes] nvarchar(MAX) NULL,
        [RequirementsJson] nvarchar(MAX) NULL,
        [TouchPointsJson] nvarchar(MAX) NULL,
        [OutOfScopeJson] nvarchar(MAX) NULL,
        [EstimatedTokens] int NULL,
        [EstimatedCostUsd] decimal(10,4) NULL,
        [CostRatioPct] decimal(6,2) NULL,
        [Branch] nvarchar(255) NULL,
        [MergeReadiness] nvarchar(255) NULL,
        [MergeCommit] varchar(64) NULL,
        [RollbackCommit] varchar(64) NULL,
        [ImplementationSummary] nvarchar(MAX) NULL,
        -- Live progress (session id, running token count, last action) --
        -- previously a sidecar progress.json, now columns on the same row
        -- so any process with DB access can read/write it.
        [SessionId] varchar(64) NULL,
        [ProgressStatus] varchar(32) NULL,
        [TokensSoFar] int NULL,
        [LastAction] nvarchar(MAX) NULL,
        [CreatedDateTime] datetime2(7) NOT NULL DEFAULT (sysutcdatetime()),
        [UpdatedDateTime] datetime2(7) NOT NULL DEFAULT (sysutcdatetime())
    );
END;
