-- View: Pipeline Funnel
-- One row per pipeline gate: how many items are currently sitting in that
-- gate, and how long the oldest one has been waiting there. IsMonitoredGate
-- flags the gates where "waiting too long" indicates a stuck pipeline
-- ('Parsed Successfully' awaiting WMS staging load, and 'WMS Awaiting
-- Pickup' awaiting the warehouse system) - GateStatusColor is RED for those
-- gates once the oldest item has been waiting over 60 minutes, GREEN
-- otherwise. Non-monitored gates (received/failed/terminal counts) always
-- report GREEN since "age" isn't a stuck-pipeline signal for them.
CREATE OR ALTER VIEW dbo.vw_PiplineFunnel AS
WITH GateItems AS (
    SELECT 'Files Received' AS GateName, 1 AS GateOrder, 0 AS IsMonitoredGate,
           RawId AS ItemId, LoadDateTime AS GateEnteredDateTime
    FROM dbo.EDI940_Raw

    UNION ALL

    SELECT 'Parsed Successfully', 2, 1,
           RawId, COALESCE(ParsedDateTime, LoadDateTime)
    FROM dbo.EDI940_Raw
    WHERE ProcessStatus = 'PARSED'

    UNION ALL

    SELECT 'Parse Failed', 3, 0,
           RawId, COALESCE(ParsedDateTime, LoadDateTime)
    FROM dbo.EDI940_Raw
    WHERE ProcessStatus = 'PARSE_FAILED'

    UNION ALL

    SELECT 'WMS Awaiting Pickup', 4, 1,
           WMSOrderHeaderStagingId, CreatedDateTime
    FROM wms.OrderHeader_Staging
    WHERE IntegrationStatus = 'READY'

    UNION ALL

    SELECT 'WMS Sent', 5, 0,
           WMSOrderHeaderStagingId, COALESCE(LastAttemptDateTime, CreatedDateTime)
    FROM wms.OrderHeader_Staging
    WHERE IntegrationStatus = 'SENT'

    UNION ALL

    SELECT 'WMS Success', 6, 0,
           WMSOrderHeaderStagingId, COALESCE(ProcessedDateTime, CreatedDateTime)
    FROM wms.OrderHeader_Staging
    WHERE IntegrationStatus = 'SUCCESS'

    UNION ALL

    SELECT 'WMS Failed', 7, 0,
           WMSOrderHeaderStagingId, COALESCE(LastAttemptDateTime, CreatedDateTime)
    FROM wms.OrderHeader_Staging
    WHERE IntegrationStatus = 'FAILED'
)
SELECT
    GateName,
    GateOrder,
    IsMonitoredGate,
    COUNT(*) AS ItemCount,
    MIN(GateEnteredDateTime) AS OldestItemDateTime,
    DATEDIFF(MINUTE, MIN(GateEnteredDateTime), SYSUTCDATETIME()) AS OldestItemAgeMinutes,
    CASE
        WHEN IsMonitoredGate = 1
             AND DATEDIFF(MINUTE, MIN(GateEnteredDateTime), SYSUTCDATETIME()) > 60
        THEN 'RED'
        ELSE 'GREEN'
    END AS GateStatusColor
FROM GateItems
GROUP BY GateName, GateOrder, IsMonitoredGate;
