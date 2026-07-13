CREATE OR ALTER PROCEDURE wms.ProcessOrders_Mock

AS

BEGIN

    SET NOCOUNT ON;



    DECLARE @Id INT;



    DECLARE order_cursor CURSOR LOCAL FAST_FORWARD FOR

        SELECT WMSOrderHeaderStagingId

        FROM wms.OrderHeader_Staging

        WHERE IntegrationStatus IN ('READY', 'FAILED')

          AND AttemptCount < 3;



    OPEN order_cursor;



    FETCH NEXT FROM order_cursor INTO @Id;



    WHILE @@FETCH_STATUS = 0

    BEGIN

        EXEC wms.MarkOrderSent @WMSOrderHeaderStagingId = @Id;



        -- simulate success/failure

        IF (ABS(CHECKSUM(NEWID())) % 100) < 80

        BEGIN

            EXEC wms.MarkOrderSuccess 

                @WMSOrderHeaderStagingId = @Id,

                @Message = 'Mock WMS accepted order';

        END

        ELSE

        BEGIN

            EXEC wms.MarkOrderFailed 

                @WMSOrderHeaderStagingId = @Id,

                @ErrorMessage = 'Mock failure: invalid SKU';

        END;



        FETCH NEXT FROM order_cursor INTO @Id;

    END;



    CLOSE order_cursor;

    DEALLOCATE order_cursor;

END;
