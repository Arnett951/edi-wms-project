CREATE OR ALTER PROCEDURE [dbo].[usp_LogPipelineRun]

    @PipelineName VARCHAR(100),

    @FileName VARCHAR(255),

    @RowsLoaded INT,

    @LoadStatus VARCHAR(20),

    @MessageText VARCHAR(500),

    @PipelineRunID VARCHAR(100),

    @dt      SMALLDATETIME

AS

BEGIN

    INSERT INTO dbo.PipelineLoadLog

    (

        PipelineName,

        FileName,

        RowsLoaded,

        LoadStatus,

        MessageText,

        PipelineRunId,

        RunDateTime

    )

    VALUES

    (

        @PipelineName,

        @FileName,

        @RowsLoaded,

        @LoadStatus,

        @MessageText,

        @PipelineRunID,

        @dt

    );

END
