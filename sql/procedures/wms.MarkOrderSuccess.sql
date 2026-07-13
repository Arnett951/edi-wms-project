CREATE OR ALTER PROCEDURE wms.MarkOrderSuccess

    @WMSOrderHeaderStagingId INT,

    @Message NVARCHAR(MAX) = NULL

AS

BEGIN

    SET NOCOUNT ON;



    UPDATE wms.OrderHeader_Staging

    SET

        IntegrationStatus = 'SUCCESS',

        ProcessedDateTime = SYSUTCDATETIME(),

        ErrorMessage = NULL

    WHERE WMSOrderHeaderStagingId = @WMSOrderHeaderStagingId;



    INSERT INTO wms.OrderIntegrationLog

    (

        WMSOrderHeaderStagingId,

        SourceHeaderId,

        SourceFileName,

        EventType,

        EventStatus,

        EventMessage

    )

    SELECT

        WMSOrderHeaderStagingId,

        SourceHeaderId,

        SourceFileName,

        'WMS_RESPONSE',

        'SUCCESS',

        ISNULL(@Message, 'WMS accepted order.')

    FROM wms.OrderHeader_Staging

    WHERE WMSOrderHeaderStagingId = @WMSOrderHeaderStagingId;

END;
