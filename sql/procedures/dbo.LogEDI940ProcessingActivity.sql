-- =====================================================
-- STORED PROCEDURE: Log Individual File Processing
-- =====================================================
CREATE OR ALTER PROCEDURE [dbo].[LogEDI940ProcessingActivity]
    @FileName NVARCHAR(255),
    @ProcessStatus NVARCHAR(50),
    @ProcessDateTime DATETIME2,
    @ErrorMessage NVARCHAR(MAX) = NULL,
    @RecordsProcessed INT = NULL
AS
BEGIN
    SET NOCOUNT ON;
    
    BEGIN TRY
        INSERT INTO dbo.EDI940_ProcessingLog 
        (FileName, ProcessStatus, ProcessDateTime, ErrorMessage, RecordsProcessed)
        VALUES 
        (@FileName, @ProcessStatus, @ProcessDateTime, @ErrorMessage, @RecordsProcessed);
        
        -- Log to audit table
        INSERT INTO dbo.EDI940_AuditLog
        (FileName, Action, ActionDateTime, Details)
        VALUES
        (@FileName, @ProcessStatus, @ProcessDateTime, CONCAT('Records Processed: ', @RecordsProcessed));
        
    END TRY
    BEGIN CATCH
        INSERT INTO dbo.EDI940_ProcessingLog 
        (FileName, ProcessStatus, ProcessDateTime, ErrorMessage)
        VALUES 
        (@FileName, 'ERROR', @ProcessDateTime, ERROR_MESSAGE());
    END CATCH
END;
