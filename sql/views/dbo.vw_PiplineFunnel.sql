-- View: Pipeline Funnel
-- One row per pipeline gate: how many items are currently sitting in that
-- gate, and how long the oldest one has been waiting there. Every gate in
-- GateDefs always appears (LEFT JOIN), even when it currently has zero
-- items, so the funnel doesn't drop stages with nothing in them.
-- IsMonitoredGate flags the gates where "waiting too long" indicates a
-- stuck pipeline ('Parsed Successfully' awaiting WMS staging load, and
-- 'WMS Awaiting Pickup' awaiting the warehouse system) - GateStatusColor is
-- RED for those gates once the oldest item has been waiting over 60
-- minutes, GREEN otherwise (including when the gate is empty).
CREATE OR ALTER VIEW dbo.vw_PiplineFunnel AS
WITH GateDefs AS (
    SELECT 'Files Received' AS GateName, 1 AS GateOrder, 0 AS IsMonitoredGate
    UNION ALL SELECT 'Parsed Successfully', 2, 1
    UNION ALL SELECT 'Parse Failed', 3, 0
    UNION ALL SELECT 'WMS Awaiting Pickup', 4, 1
    UNION ALL SELECT 'WMS Sent', 5, 0
    UNION ALL SELECT 'WMS Success', 6, 0
    UNION ALL SELECT 'WMS Failed', 7, 0
),
GateItems AS (
    SELECT 'Files Received' AS GateName, RawId AS ItemId, LoadDateTime AS GateEnteredDateTime
    FROM dbo.EDI940_Raw

    UNION ALL

    SELECT 'Parsed Successfully', RawId, COALESCE(ParsedDateTime, LoadDateTime)
    FROM dbo.EDI940_Raw
    WHERE ProcessStatus = 'PARSED'

    UNION ALL

    SELECT 'Parse Failed', RawId, COALESCE(ParsedDateTime, LoadDateTime)
    FROM dbo.EDI940_Raw
    WHERE ProcessStatus = 'PARSE_FAILED'

    UNION ALL

    SELECT 'WMS Awaiting Pickup', WMSOrderHeaderStagingId, CreatedDateTime
    FROM wms.OrderHeader_Staging
    WHERE IntegrationStatus = 'READY'

    UNION ALL

    SELECT 'WMS Sent', WMSOrderHeaderStagingId, COALESCE(LastAttemptDateTime, CreatedDateTime)
    FROM wms.OrderHeader_Staging
    WHERE IntegrationStatus = 'SENT'

    UNION ALL

    SELECT 'WMS Success', WMSOrderHeaderStagingId, COALESCE(ProcessedDateTime, CreatedDateTime)
    FROM wms.OrderHeader_Staging
    WHERE IntegrationStatus = 'SUCCESS'

    UNION ALL

    SELECT 'WMS Failed', WMSOrderHeaderStagingId, COALESCE(LastAttemptDateTime, CreatedDateTime)
    FROM wms.OrderHeader_Staging
    WHERE IntegrationStatus = 'FAILED'
)
SELECT
    gd.GateName,
    gd.GateOrder,
    gd.IsMonitoredGate,
    COUNT(gi.ItemId) AS ItemCount,
    MIN(gi.GateEnteredDateTime) AS OldestItemDateTime,
    DATEDIFF(MINUTE, MIN(gi.GateEnteredDateTime), SYSUTCDATETIME()) AS OldestItemAgeMinutes,
    CASE
        WHEN gd.IsMonitoredGate = 1
             AND COUNT(gi.ItemId) > 0
             AND DATEDIFF(MINUTE, MIN(gi.GateEnteredDateTime), SYSUTCDATETIME()) > 60
        THEN 'RED'
        ELSE 'GREEN'
    END AS GateStatusColor
FROM GateDefs gd
LEFT JOIN GateItems gi ON gi.GateName = gd.GateName
GROUP BY gd.GateName, gd.GateOrder, gd.IsMonitoredGate;
