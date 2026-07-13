CREATE   PROCEDURE [dbo].[ParseEDI940RawByFile]
    @FileName NVARCHAR(255)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE 
        @RawId INT,
        @RawEDIText NVARCHAR(MAX),
        @ISAControlNumber NVARCHAR(50),
        @GSControlNumber NVARCHAR(50),
        @GE01_TransactionCount INT,
        @GE02_GroupControlNumber NVARCHAR(50),
        @IEA01_GroupCount INT,
        @IEA02_InterchangeControlNumber NVARCHAR(50);

    SELECT TOP 1
        @RawId = RawId,
        @RawEDIText = RawEDIText
    FROM dbo.EDI940_Raw
    WHERE FileName = @FileName
      AND ProcessStatus = 'RAW_LOADED'
    ORDER BY RawId DESC;

    IF @RawId IS NULL
        RETURN;

    BEGIN TRY

        /* Remove prior parse results for this RawId, if rerunning */
        DELETE c
        FROM dbo.EDI940_Control c
        INNER JOIN dbo.EDI940_Header h ON c.HeaderId = h.HeaderId
        WHERE h.RawId = @RawId;

        DELETE d
        FROM dbo.EDI940_Detail d
        INNER JOIN dbo.EDI940_Header h ON d.HeaderId = h.HeaderId
        WHERE h.RawId = @RawId;

        DELETE a
        FROM dbo.EDI940_Address a
        INNER JOIN dbo.EDI940_Header h ON a.HeaderId = h.HeaderId
        WHERE h.RawId = @RawId;

        DELETE FROM dbo.EDI940_Header
        WHERE RawId = @RawId;

        DECLARE @Segments TABLE (
            SegmentSeq INT IDENTITY(1,1) NOT NULL,
            SegmentText NVARCHAR(MAX) NOT NULL,
            SegmentId NVARCHAR(20) NOT NULL
        );
        DECLARE 
    @Work NVARCHAR(MAX),
    @NextTilde INT,
    @Segment NVARCHAR(MAX);

    SET @Work = REPLACE(REPLACE(@RawEDIText, CHAR(13), ''), CHAR(10), '') + '~';

    WHILE CHARINDEX('~', @Work) > 0
    BEGIN
        SET @NextTilde = CHARINDEX('~', @Work);
        SET @Segment = LTRIM(RTRIM(LEFT(@Work, @NextTilde - 1)));

        IF @Segment <> ''
        BEGIN
            INSERT INTO @Segments (SegmentText, SegmentId)
            VALUES (
                @Segment,
                LEFT(@Segment, CHARINDEX('*', @Segment + '*') - 1)
            );
        END;

        SET @Work = SUBSTRING(@Work, @NextTilde + 1, LEN(@Work));
    END;

        SELECT TOP 1 @ISAControlNumber = dbo.GetEDIElement(SegmentText, 13)
        FROM @Segments
        WHERE SegmentId = 'ISA';

        SELECT TOP 1 @GSControlNumber = dbo.GetEDIElement(SegmentText, 6)
        FROM @Segments
        WHERE SegmentId = 'GS';

        SELECT TOP 1
            @GE01_TransactionCount = TRY_CAST(dbo.GetEDIElement(SegmentText, 1) AS INT),
            @GE02_GroupControlNumber = dbo.GetEDIElement(SegmentText, 2)
        FROM @Segments
        WHERE SegmentId = 'GE';

        SELECT TOP 1
            @IEA01_GroupCount = TRY_CAST(dbo.GetEDIElement(SegmentText, 1) AS INT),
            @IEA02_InterchangeControlNumber = dbo.GetEDIElement(SegmentText, 2)
        FROM @Segments
        WHERE SegmentId = 'IEA';

        DECLARE 
            @STSegmentSeq INT,
            @SESegmentSeq INT,
            @HeaderId INT,
            @STSegmentText NVARCHAR(MAX);

        DECLARE st_cursor CURSOR LOCAL FAST_FORWARD FOR
            SELECT SegmentSeq, SegmentText
            FROM @Segments
            WHERE SegmentId = 'ST'
              AND dbo.GetEDIElement(SegmentText, 1) = '940'
            ORDER BY SegmentSeq;

        OPEN st_cursor;

        FETCH NEXT FROM st_cursor INTO @STSegmentSeq, @STSegmentText;

        WHILE @@FETCH_STATUS = 0
        BEGIN
            SELECT TOP 1 @SESegmentSeq = SegmentSeq
            FROM @Segments
            WHERE SegmentId = 'SE'
              AND SegmentSeq > @STSegmentSeq
            ORDER BY SegmentSeq;

            IF @SESegmentSeq IS NOT NULL
            BEGIN
                INSERT INTO dbo.EDI940_Header
                (
                    RawId,
                    FileName,
                    ISAControlNumber,
                    GSControlNumber,
                    STControlNumber,
                    TransactionSetCode,
                    WarehouseOrderNumber,
                    ShipDate,
                    STSegmentSeq,
                    SESegmentSeq
                )
                SELECT
                    @RawId,
                    @FileName,
                    @ISAControlNumber,
                    @GSControlNumber,
                    dbo.GetEDIElement(@STSegmentText, 2),
                    dbo.GetEDIElement(@STSegmentText, 1),
                    (
                        SELECT TOP 1 dbo.GetEDIElement(SegmentText, 2)
                        FROM @Segments
                        WHERE SegmentId = 'W05'
                          AND SegmentSeq BETWEEN @STSegmentSeq AND @SESegmentSeq
                    ),
                    (
                        SELECT TOP 1 dbo.GetEDIElement(SegmentText, 4)
                        FROM @Segments
                        WHERE SegmentId = 'W05'
                          AND SegmentSeq BETWEEN @STSegmentSeq AND @SESegmentSeq
                    ),
                    @STSegmentSeq,
                    @SESegmentSeq;

                SET @HeaderId = SCOPE_IDENTITY();

                INSERT INTO dbo.EDI940_Address
                (
                    HeaderId,
                    EntityCode,
                    Name,
                    IdQualifier,
                    IdCode
                )
                SELECT
                    @HeaderId,
                    dbo.GetEDIElement(SegmentText, 1),
                    dbo.GetEDIElement(SegmentText, 2),
                    dbo.GetEDIElement(SegmentText, 3),
                    dbo.GetEDIElement(SegmentText, 4)
                FROM @Segments
                WHERE SegmentId = 'N1'
                  AND SegmentSeq BETWEEN @STSegmentSeq AND @SESegmentSeq;

                INSERT INTO dbo.EDI940_Detail
                (
                    HeaderId,
                    LineNumber,
                    QuantityOrdered,
                    UOM,
                    ProductQualifier,
                    ProductId,
                    ProductQualifier2,
                    ProductId2
                )
                SELECT
                    @HeaderId,
                    CAST(SegmentSeq AS NVARCHAR(50)),
                    TRY_CAST(dbo.GetEDIElement(SegmentText, 1) AS DECIMAL(18,4)),
                    dbo.GetEDIElement(SegmentText, 2),
                    dbo.GetEDIElement(SegmentText, 3),
                    dbo.GetEDIElement(SegmentText, 4),
                    dbo.GetEDIElement(SegmentText, 5),
                    dbo.GetEDIElement(SegmentText, 6)
                FROM @Segments
                WHERE SegmentId = 'W01'
                  AND SegmentSeq BETWEEN @STSegmentSeq AND @SESegmentSeq;

                /* Validate W01 quantity */
                IF EXISTS (
                    SELECT 1
                    FROM dbo.EDI940_Detail d
                    WHERE d.HeaderId = @HeaderId
                      AND (
                            d.QuantityOrdered IS NULL
                         OR d.QuantityOrdered <= 0
                      )
                )
                BEGIN
                    ;THROW 51001,
                        'EDI 940 validation failed: W01 quantity is missing, invalid, or zero.',
                        1;
                END

                INSERT INTO dbo.EDI940_Control
                (
                    HeaderId,
                    SE01_SegmentCount,
                    SE02_ControlNumber,
                    GE01_TransactionCount,
                    GE02_GroupControlNumber,
                    IEA01_GroupCount,
                    IEA02_InterchangeControlNumber
                )
                VALUES
                (
                    @HeaderId,
                    TRY_CAST((
                        SELECT TOP 1 dbo.GetEDIElement(SegmentText, 1)
                        FROM @Segments
                        WHERE SegmentId = 'SE'
                          AND SegmentSeq = @SESegmentSeq
                    ) AS INT),
                    (
                        SELECT TOP 1 dbo.GetEDIElement(SegmentText, 2)
                        FROM @Segments
                        WHERE SegmentId = 'SE'
                          AND SegmentSeq = @SESegmentSeq
                    ),
                    @GE01_TransactionCount,
                    @GE02_GroupControlNumber,
                    @IEA01_GroupCount,
                    @IEA02_InterchangeControlNumber
                );
            END;

            FETCH NEXT FROM st_cursor INTO @STSegmentSeq, @STSegmentText;
        END;

        CLOSE st_cursor;
        DEALLOCATE st_cursor;

        UPDATE dbo.EDI940_Raw
        SET 
            ProcessStatus = 'PARSED',
            ParsedDateTime = SYSUTCDATETIME(),
            ErrorMessage = NULL
        WHERE RawId = @RawId;

    END TRY
    BEGIN CATCH

        IF CURSOR_STATUS('local', 'st_cursor') >= -1
        BEGIN
            CLOSE st_cursor;
            DEALLOCATE st_cursor;
        END;

        UPDATE dbo.EDI940_Raw
        SET 
            ProcessStatus = 'PARSE_FAILED',
            ErrorMessage = ERROR_MESSAGE()
        WHERE RawId = @RawId;

        THROW;
    END CATCH
END;
