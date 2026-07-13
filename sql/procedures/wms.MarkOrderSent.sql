CREATE   PROCEDURE wms.MarkOrderSent
    @WMSOrderHeaderStagingId INT
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE wms.OrderHeader_Staging
    SET
        IntegrationStatus = 'SENT',
        AttemptCount = AttemptCount + 1,
        LastAttemptDateTime = SYSUTCDATETIME(),
        ErrorMessage = NULL
    WHERE WMSOrderHeaderStagingId = @WMSOrderHeaderStagingId
      AND IntegrationStatus IN ('READY', 'FAILED');

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
        'SEND_ATTEMPT',
        'SENT',
        'Order marked as sent to WMS.'
    FROM wms.OrderHeader_Staging
    WHERE WMSOrderHeaderStagingId = @WMSOrderHeaderStagingId;
END;
