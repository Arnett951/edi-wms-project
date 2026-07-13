CREATE   PROCEDURE wms.MarkOrderFailed
    @WMSOrderHeaderStagingId INT,
    @ErrorMessage NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE wms.OrderHeader_Staging
    SET
        IntegrationStatus = 'FAILED',
        ErrorMessage = @ErrorMessage,
        LastAttemptDateTime = SYSUTCDATETIME()
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
        'FAILED',
        @ErrorMessage
    FROM wms.OrderHeader_Staging
    WHERE WMSOrderHeaderStagingId = @WMSOrderHeaderStagingId;
END;
