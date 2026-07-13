CREATE   PROCEDURE dbo.UpdateEDI940RawISAFields
    @FileName NVARCHAR(255)
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE r
    SET
        ISASender          = LTRIM(RTRIM(dbo.GetEDIElement(isa.SegmentText, 6))),
        ISAReceiver        = LTRIM(RTRIM(dbo.GetEDIElement(isa.SegmentText, 8))),
        ISA_ControlNumber  = LTRIM(RTRIM(dbo.GetEDIElement(isa.SegmentText, 13)))
    FROM dbo.EDI940_Raw r
    OUTER APPLY (
        SELECT TOP 1
            LTRIM(RTRIM(value)) AS SegmentText
        FROM STRING_SPLIT(
            REPLACE(REPLACE(r.RawEDIText, CHAR(13), ''), CHAR(10), ''),
            '~'
        )
        WHERE LEFT(LTRIM(RTRIM(value)), 4) = 'ISA*'
    ) isa
    WHERE r.FileName = @FileName;
END;
