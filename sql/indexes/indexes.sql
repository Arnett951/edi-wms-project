-- Non-PK indexes
CREATE NONCLUSTERED INDEX [IX_EDI940_AuditLog_FileName] ON dbo.EDI940_AuditLog ([FileName]);
CREATE NONCLUSTERED INDEX [IX_EDI940_AuditLog_RawID] ON dbo.EDI940_AuditLog ([RawID]);
CREATE NONCLUSTERED INDEX [IX_EDI940_ProcessingLog_FileName] ON dbo.EDI940_ProcessingLog ([FileName]);
CREATE NONCLUSTERED INDEX [IX_EDI940_ProcessingLog_Status] ON dbo.EDI940_ProcessingLog ([ProcessStatus]);
