CREATE PROCEDURE dbo.sp_LogPipelineActivity
    @PipelineName NVARCHAR(255),
    @PipelineRunID NVARCHAR(255),
    @ActivityName NVARCHAR(255),
    @LoadStatus NVARCHAR(50),
    @RowsCopied INT = 0,
    @RowsAffected INT = 0,
    @ErrorCode NVARCHAR(50) = NULL,
    @ErrorMessage NVARCHAR(MAX) = NULL,
    @ErrorStackTrace NVARCHAR(MAX) = NULL,
    @LoadStartTime DATETIME,
    @LoadEndTime DATETIME = NULL,
    @SourceFilePath NVARCHAR(500) = NULL,
    @LoadBatchID INT = NULL
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        DECLARE @DurationSeconds INT;

        -- Calculate duration if end time provided
        IF @LoadEndTime IS NOT NULL
            SET @DurationSeconds = DATEDIFF(SECOND, @LoadStartTime, @LoadEndTime);
        ELSE
            SET @LoadEndTime = GETDATE();

        -- Insert log record
        INSERT INTO dbo.PipelineLoadLog (
            PipelineName,
            PipelineRunID,
            ActivityName,
            LoadStatus,
            RowsCopied,
            RowsAffected,
            ErrorCode,
            ErrorMessage,
            ErrorStackTrace,
            LoadStartTime,
            LoadEndTime,
            LoadDurationSeconds,
            SourceFilePath,
            LoadBatchID
        )
        VALUES (
            @PipelineName,
            @PipelineRunID,
            @ActivityName,
            @LoadStatus,
            @RowsCopied,
            @RowsAffected,
            @ErrorCode,
            @ErrorMessage,
            @ErrorStackTrace,
            @LoadStartTime,
            @LoadEndTime,
            @DurationSeconds,
            @SourceFilePath,
            @LoadBatchID
        );

        -- Return inserted LoadLogID
        SELECT CAST(SCOPE_IDENTITY() AS INT) AS LoadLogID;

    END TRY
    BEGIN CATCH
        -- Log the error that occurred during logging
        DECLARE @ErrorMsg NVARCHAR(MAX) = ERROR_MESSAGE();
        DECLARE @ErrorNum INT = ERROR_NUMBER();
        
        RAISERROR('Error in sp_LogPipelineActivity: %s (Error %d)', 16, 1, @ErrorMsg, @ErrorNum);
    END CATCH
END;
