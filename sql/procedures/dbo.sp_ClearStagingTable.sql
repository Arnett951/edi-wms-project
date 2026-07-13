CREATE OR ALTER PROCEDURE dbo.sp_ClearStagingTable
    @LoadBatchID INT = NULL
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        IF @LoadBatchID IS NOT NULL
            DELETE FROM dbo.CustomerOrders_Staging WHERE LoadBatchID = @LoadBatchID;
        ELSE
            DELETE FROM dbo.CustomerOrders_Staging;

        RETURN 0;

    END TRY
    BEGIN CATCH
        DECLARE @ErrorMsg NVARCHAR(MAX) = ERROR_MESSAGE();
        RAISERROR('Error clearing staging table: %s', 16, 1, @ErrorMsg);
        RETURN -1;
    END CATCH
END;
