CREATE PROCEDURE dbo.sp_MergeStagingToProduction
    @LoadBatchID INT,
    @RowsAffected INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        DECLARE @StartTime DATETIME = GETDATE();

        -- MERGE operation: Insert new orders, Update existing orders
        MERGE INTO dbo.CustomerOrders AS target
        USING dbo.CustomerOrders_Staging AS source
            ON target.OrderID = source.OrderID
        WHEN MATCHED THEN
            UPDATE SET
                target.CustomerID = source.CustomerID,
                target.OrderDate = source.OrderDate,
                target.OrderAmount = source.OrderAmount,
                target.Status = source.Status,
                target.ModifiedDate = GETDATE()
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (CustomerID, OrderDate, OrderAmount, Status, CreatedDate, ModifiedDate)
            VALUES (source.CustomerID, source.OrderDate, source.OrderAmount, source.Status, GETDATE(), GETDATE());

        -- Get the number of affected rows
        SET @RowsAffected = @@ROWCOUNT;

        -- Clear staging table for next batch (optional - comment out to keep history)
        -- DELETE FROM dbo.CustomerOrders_Staging WHERE LoadBatchID = @LoadBatchID;

        RETURN 0;  -- Success

    END TRY
    BEGIN CATCH
        SET @RowsAffected = -1;
        
        DECLARE @ErrorMsg NVARCHAR(MAX) = ERROR_MESSAGE();
        DECLARE @ErrorNum INT = ERROR_NUMBER();
        
        RAISERROR('Error in sp_MergeStagingToProduction: %s (Error %d)', 16, 1, @ErrorMsg, @ErrorNum);
        RETURN -1;  -- Failure
    END CATCH
END;
