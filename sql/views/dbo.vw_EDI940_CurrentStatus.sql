-- View: Current Processing Status
CREATE OR ALTER VIEW vw_EDI940_CurrentStatus AS
SELECT 
    CAST(GETDATE() AS DATE) AS [Date],
    COUNT(DISTINCT FileName) AS [Total Files Processed],
    SUM(CASE WHEN ProcessStatus = 'SUCCESS' THEN 1 ELSE 0 END) AS [Successful],
    SUM(CASE WHEN ProcessStatus = 'ERROR' THEN 1 ELSE 0 END) AS [Failed],
    CAST(SUM(CASE WHEN ProcessStatus = 'SUCCESS' THEN 1 ELSE 0 END) AS FLOAT) 
        / NULLIF(COUNT(DISTINCT FileName), 0) * 100 AS [Success Rate %]
FROM 
    dbo.EDI940_ProcessingLog
WHERE 
    CAST(ProcessDateTime AS DATE) = CAST(GETDATE() AS DATE)
