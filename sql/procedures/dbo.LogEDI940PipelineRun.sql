-- =====================================================
-- STORED PROCEDURE: Log Pipeline Completion
-- =====================================================
CREATE PROCEDURE [dbo].[LogEDI940PipelineRun]
    @PipelineRunId NVARCHAR(255),
    @PipelineStatus NVARCHAR(50),
    @ProcessDateTime DATETIME2,
    @FilesProcessed INT = NULL,
    @FilesFailed INT = NULL,
    @ExecutionDuration INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    
    BEGIN TRY
        INSERT INTO dbo.EDI940_PipelineLog 
        (AdfPipelineRunId, PipelineStatus, ProcessDateTime, FilesProcessed, FilesFailed, ExecutionDuration)
        VALUES 
        (@PipelineRunId, @PipelineStatus, @ProcessDateTime, @FilesProcessed, @FilesFailed, @ExecutionDuration);
        
    END TRY
    BEGIN CATCH
        INSERT INTO dbo.EDI940_PipelineLog 
        (AdfPipelineRunId, PipelineStatus, ProcessDateTime)
        VALUES 
        (@PipelineRunId, 'ERROR', @ProcessDateTime);
    END CATCH
END;
