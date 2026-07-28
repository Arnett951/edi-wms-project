-- View: File Reconciliation
-- One row per inbound file (EDI940_Raw), rolled up to a single outcome so
-- every file received can be accounted for:
--   Parse Failed     - never produced any orders (dbo.EDI940_Header rows)
--   Needs Attention  - stuck parsing/staging past the 60-min staleness
--                       threshold, or produced at least one WMS order that
--                       IntegrationStatus = 'FAILED'
--   In Progress      - still moving through the pipeline within normal time
--   Delivered         - staged, and every resulting order reached WMS SUCCESS
-- Order count is unknowable until a file is parsed (EDI940_Header rows don't
-- exist yet), so files are only joined out to their orders once parsed; the
-- file's own ProcessStatus (RAW_LOADED -> PARSED -> STAGED, or
-- PARSE_FAILED) drives the early states.
-- "Worst status wins": one FAILED order anywhere in a file is enough to mark
-- the whole file Needs Attention, so a partially-failed file never reads as
-- fine.
CREATE OR ALTER VIEW dbo.vw_FileReconciliation AS
WITH FileOrders AS (
    SELECT
        r.RawId,
        h.HeaderId,
        s.IntegrationStatus,
        s.LastAttemptDateTime,
        s.CreatedDateTime AS OrderCreatedDateTime,
        s.ErrorMessage AS OrderErrorMessage
    FROM dbo.EDI940_Raw r
    LEFT JOIN dbo.EDI940_Header h ON h.RawId = r.RawId
    LEFT JOIN wms.OrderHeader_Staging s ON s.SourceHeaderId = h.HeaderId
),
FileRollup AS (
    SELECT
        RawId,
        COUNT(HeaderId) AS OrderCount,
        SUM(CASE WHEN IntegrationStatus = 'SUCCESS' THEN 1 ELSE 0 END) AS SuccessCount,
        SUM(CASE WHEN IntegrationStatus = 'FAILED' THEN 1 ELSE 0 END) AS FailedOrderCount,
        SUM(CASE WHEN IntegrationStatus IN ('READY', 'SENT') THEN 1 ELSE 0 END) AS InFlightCount,
        MIN(CASE WHEN IntegrationStatus IN ('READY', 'SENT')
                 THEN COALESCE(LastAttemptDateTime, OrderCreatedDateTime) END) AS OldestInFlightDateTime,
        MAX(CASE WHEN IntegrationStatus = 'FAILED' THEN OrderErrorMessage END) AS SampleOrderError
    FROM FileOrders
    GROUP BY RawId
)
SELECT
    r.RawId,
    r.FileName,
    CONVERT(varchar(19), r.LoadDateTime, 120) AS LoadDateTime,
    r.ProcessStatus,
    fr.OrderCount,
    fr.SuccessCount,
    fr.FailedOrderCount,
    fr.InFlightCount,
    CASE
        WHEN r.ProcessStatus = 'PARSE_FAILED' THEN 'Parse Failed'

        WHEN r.ProcessStatus IN ('RAW_LOADED', 'PARSED')
             AND DATEDIFF(MINUTE, r.LoadDateTime, SYSUTCDATETIME()) > 60
            THEN 'Needs Attention'
        WHEN r.ProcessStatus IN ('RAW_LOADED', 'PARSED') THEN 'In Progress'

        WHEN r.ProcessStatus = 'STAGED' AND fr.FailedOrderCount > 0 THEN 'Needs Attention'
        WHEN r.ProcessStatus = 'STAGED' AND fr.InFlightCount > 0
             AND DATEDIFF(MINUTE, fr.OldestInFlightDateTime, SYSUTCDATETIME()) > 60
            THEN 'Needs Attention'
        WHEN r.ProcessStatus = 'STAGED' AND fr.InFlightCount > 0 THEN 'In Progress'
        WHEN r.ProcessStatus = 'STAGED' AND fr.SuccessCount > 0 THEN 'Delivered'

        ELSE 'Needs Attention'
    END AS FileStatus,
    CASE
        WHEN r.ProcessStatus = 'PARSE_FAILED' THEN r.ErrorMessage

        WHEN r.ProcessStatus IN ('RAW_LOADED', 'PARSED')
             AND DATEDIFF(MINUTE, r.LoadDateTime, SYSUTCDATETIME()) > 60
            THEN CONCAT('Not staged to WMS after ', DATEDIFF(MINUTE, r.LoadDateTime, SYSUTCDATETIME()), ' min')

        WHEN r.ProcessStatus = 'STAGED' AND fr.FailedOrderCount > 0
            THEN CONCAT(fr.FailedOrderCount, ' of ', fr.OrderCount, ' order(s) rejected by WMS: ', fr.SampleOrderError)

        WHEN r.ProcessStatus = 'STAGED' AND fr.InFlightCount > 0
             AND DATEDIFF(MINUTE, fr.OldestInFlightDateTime, SYSUTCDATETIME()) > 60
            THEN CONCAT(fr.InFlightCount, ' order(s) stuck awaiting WMS pickup')

        ELSE NULL
    END AS AttentionReason
FROM dbo.EDI940_Raw r
LEFT JOIN FileRollup fr ON fr.RawId = r.RawId;
