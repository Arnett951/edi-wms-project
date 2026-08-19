-- Non-PK indexes
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_EDI940_AuditLog_FileName' AND object_id = OBJECT_ID('dbo.EDI940_AuditLog'))
BEGIN
    CREATE NONCLUSTERED INDEX [IX_EDI940_AuditLog_FileName] ON dbo.EDI940_AuditLog ([FileName]);
END;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_EDI940_AuditLog_RawID' AND object_id = OBJECT_ID('dbo.EDI940_AuditLog'))
BEGIN
    CREATE NONCLUSTERED INDEX [IX_EDI940_AuditLog_RawID] ON dbo.EDI940_AuditLog ([RawID]);
END;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_EDI940_ProcessingLog_FileName' AND object_id = OBJECT_ID('dbo.EDI940_ProcessingLog'))
BEGIN
    CREATE NONCLUSTERED INDEX [IX_EDI940_ProcessingLog_FileName] ON dbo.EDI940_ProcessingLog ([FileName]);
END;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_EDI940_ProcessingLog_Status' AND object_id = OBJECT_ID('dbo.EDI940_ProcessingLog'))
BEGIN
    CREATE NONCLUSTERED INDEX [IX_EDI940_ProcessingLog_Status] ON dbo.EDI940_ProcessingLog ([ProcessStatus]);
END;
