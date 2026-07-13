-- View: Files Requiring Attention
CREATE OR ALTER VIEW vw_EDI940_FilesNeedingAttention AS
SELECT 
    FileName,
    ProcessStatus,
    ProcessDateTime,
    ErrorMessage,
    DATEDIFF(HOUR, ProcessDateTime, GETDATE()) AS [Hours Since Processing]
FROM 
    dbo.EDI940_ProcessingLog
WHERE 
    ProcessStatus IN ('ERROR', 'PENDING', 'FAILED')
