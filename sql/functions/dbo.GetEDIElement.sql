CREATE   FUNCTION dbo.GetEDIElement
(
    @Segment NVARCHAR(MAX),
    @Position INT
)
RETURNS NVARCHAR(MAX)
AS
BEGIN
    DECLARE 
        @Work NVARCHAR(MAX),
        @CurrentPosition INT = 0,
        @NextDelimiter INT,
        @ElementValue NVARCHAR(MAX);

    -- Add final delimiter so the last element can be captured
    SET @Work = ISNULL(@Segment, '') + '*';

    WHILE CHARINDEX('*', @Work) > 0
    BEGIN
        SET @NextDelimiter = CHARINDEX('*', @Work);
        SET @ElementValue = LEFT(@Work, @NextDelimiter - 1);

        IF @CurrentPosition = @Position
            RETURN NULLIF(LTRIM(RTRIM(@ElementValue)), '');

        SET @Work = SUBSTRING(@Work, @NextDelimiter + 1, LEN(@Work));
        SET @CurrentPosition += 1;
    END;

    RETURN NULL;
END;
