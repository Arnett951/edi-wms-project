CREATE VIEW dbo.v_RecentLoadActivity AS
SELECT TOP 100
    LoadLogID,
    PipelineName,
    PipelineRunID,
    ActivityName,
    LoadStatus,
    RowsCopied,
    RowsAffected,
    ErrorCode,
    ErrorMessage,
    LoadDurationSeconds,
    CreatedDate,
    CASE 
        WHEN LoadStatus = 'SUCCESS' THEN 'Complete'
        WHEN LoadStatus = 'FAILURE' THEN 'Failed'
        ELSE 'In Progress'
    END AS StatusDisplay
FROM dbo.PipelineLoadLog
ORDER BY CreatedDate DESC;
