-- =====================================================
-- STORED PROCEDURE: Generate Processing Report
-- =====================================================
CREATE OR ALTER PROCEDURE [dbo].[GetEDI940ProcessingReport]
    @StartDate DATETIME2 = NULL,
    @EndDate DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Default to last 7 days if not specified
    IF @StartDate IS NULL
        SET @StartDate = DATEADD(DAY, -7, CAST(GETDATE() AS DATE));
    
    IF @EndDate IS NULL
        SET @EndDate = CAST(GETDATE() AS DATE);
    
    SELECT 
        ppl.AdfPipelineRunId,
        ppl.PipelineStatus,
        ppl.ProcessDateTime,
        ppl.FilesProcessed,
        ppl.FilesFailed,
        ppl.ExecutionDuration,
        COUNT(DISTINCT pl.FileName) AS UniqueFilesInRun,
        SUM(CASE WHEN pl.ProcessStatus = 'SUCCESS' THEN 1 ELSE 0 END) AS SuccessfulFiles,
        SUM(CASE WHEN pl.ProcessStatus = 'ERROR' THEN 1 ELSE 0 END) AS FailedFiles
    FROM 
        dbo.EDI940_PipelineLog ppl
    LEFT JOIN 
        dbo.EDI940_ProcessingLog pl 
        ON ppl.ProcessDateTime = pl.ProcessDateTime
    WHERE 
        ppl.ProcessDateTime BETWEEN @StartDate AND @EndDate
    GROUP BY 
        ppl.AdfPipelineRunId,
        ppl.PipelineStatus,
        ppl.ProcessDateTime,
        ppl.FilesProcessed,
        ppl.FilesFailed,
        ppl.ExecutionDuration
    ORDER BY 
        ppl.ProcessDateTime DESC;
END;
