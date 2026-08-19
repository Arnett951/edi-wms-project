-- =====================================================
-- TABLE: dbo.ChatFeedback
-- Thumbs up/down + optional comment on an AI chat panel response (CR-025).
-- QuestionText/ResponseText are stored directly (not a FK to a chat-history
-- table -- none exists; each chat turn is client-side only) so a response
-- can still be reviewed later. MessageHash is a stable SHA-256 of the
-- question+response pair, useful for spotting repeat complaints about the
-- same reply without depending on any client-generated id.
-- =====================================================
IF OBJECT_ID('dbo.ChatFeedback', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ChatFeedback (
        [FeedbackId] int IDENTITY(1,1) NOT NULL,
        [UserOid] varchar(100) NOT NULL,
        [MessageHash] char(64) NOT NULL,
        [Channel] varchar(20) NOT NULL,
        [Source] varchar(20) NOT NULL,
        [QuestionText] nvarchar(MAX) NOT NULL,
        [ResponseText] nvarchar(MAX) NOT NULL,
        [Rating] smallint NOT NULL,
        [Comment] nvarchar(1000) NULL,
        [CreatedDateTime] datetime2(7) NOT NULL DEFAULT (sysutcdatetime())
    );
END;
