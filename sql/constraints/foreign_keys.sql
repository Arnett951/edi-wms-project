-- Foreign key constraints
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_EDI940_Address_Header')
BEGIN
    ALTER TABLE dbo.EDI940_Address ADD CONSTRAINT [FK_EDI940_Address_Header] FOREIGN KEY ([HeaderId]) REFERENCES dbo.EDI940_Header ([HeaderId]);
END;
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_EDI940_Control_Header')
BEGIN
    ALTER TABLE dbo.EDI940_Control ADD CONSTRAINT [FK_EDI940_Control_Header] FOREIGN KEY ([HeaderId]) REFERENCES dbo.EDI940_Header ([HeaderId]);
END;
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_EDI940_Detail_Header')
BEGIN
    ALTER TABLE dbo.EDI940_Detail ADD CONSTRAINT [FK_EDI940_Detail_Header] FOREIGN KEY ([HeaderId]) REFERENCES dbo.EDI940_Header ([HeaderId]);
END;
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK__GroupRole__Group__74444068')
BEGIN
    ALTER TABLE dbo.GroupRoles ADD CONSTRAINT [FK__GroupRole__Group__74444068] FOREIGN KEY ([GroupId]) REFERENCES dbo.Groups ([GroupId]);
END;
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK__GroupRole__RoleI__753864A1')
BEGIN
    ALTER TABLE dbo.GroupRoles ADD CONSTRAINT [FK__GroupRole__RoleI__753864A1] FOREIGN KEY ([RoleId]) REFERENCES dbo.Roles ([RoleId]);
END;
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK__RolePermi__Permi__7167D3BD')
BEGIN
    ALTER TABLE dbo.RolePermissions ADD CONSTRAINT [FK__RolePermi__Permi__7167D3BD] FOREIGN KEY ([PermissionId]) REFERENCES dbo.Permissions ([PermissionId]);
END;
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK__RolePermi__RoleI__7073AF84')
BEGIN
    ALTER TABLE dbo.RolePermissions ADD CONSTRAINT [FK__RolePermi__RoleI__7073AF84] FOREIGN KEY ([RoleId]) REFERENCES dbo.Roles ([RoleId]);
END;
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK__UserGroup__Group__7814D14C')
BEGIN
    ALTER TABLE dbo.UserGroups ADD CONSTRAINT [FK__UserGroup__Group__7814D14C] FOREIGN KEY ([GroupId]) REFERENCES dbo.Groups ([GroupId]);
END;
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK__UserRoles__RoleI__7AF13DF7')
BEGIN
    ALTER TABLE dbo.UserRoles ADD CONSTRAINT [FK__UserRoles__RoleI__7AF13DF7] FOREIGN KEY ([RoleId]) REFERENCES dbo.Roles ([RoleId]);
END;
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_OrderDetailStaging_Header')
BEGIN
    ALTER TABLE wms.OrderDetail_Staging ADD CONSTRAINT [FK_OrderDetailStaging_Header] FOREIGN KEY ([WMSOrderHeaderStagingId]) REFERENCES wms.OrderHeader_Staging ([WMSOrderHeaderStagingId]);
END;
