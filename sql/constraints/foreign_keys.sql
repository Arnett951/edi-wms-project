-- Foreign key constraints
ALTER TABLE dbo.EDI940_Address ADD CONSTRAINT [FK_EDI940_Address_Header] FOREIGN KEY ([HeaderId]) REFERENCES dbo.EDI940_Header ([HeaderId]);
ALTER TABLE dbo.EDI940_Control ADD CONSTRAINT [FK_EDI940_Control_Header] FOREIGN KEY ([HeaderId]) REFERENCES dbo.EDI940_Header ([HeaderId]);
ALTER TABLE dbo.EDI940_Detail ADD CONSTRAINT [FK_EDI940_Detail_Header] FOREIGN KEY ([HeaderId]) REFERENCES dbo.EDI940_Header ([HeaderId]);
ALTER TABLE dbo.GroupRoles ADD CONSTRAINT [FK__GroupRole__Group__74444068] FOREIGN KEY ([GroupId]) REFERENCES dbo.Groups ([GroupId]);
ALTER TABLE dbo.GroupRoles ADD CONSTRAINT [FK__GroupRole__RoleI__753864A1] FOREIGN KEY ([RoleId]) REFERENCES dbo.Roles ([RoleId]);
ALTER TABLE dbo.RolePermissions ADD CONSTRAINT [FK__RolePermi__Permi__7167D3BD] FOREIGN KEY ([PermissionId]) REFERENCES dbo.Permissions ([PermissionId]);
ALTER TABLE dbo.RolePermissions ADD CONSTRAINT [FK__RolePermi__RoleI__7073AF84] FOREIGN KEY ([RoleId]) REFERENCES dbo.Roles ([RoleId]);
ALTER TABLE dbo.UserGroups ADD CONSTRAINT [FK__UserGroup__Group__7814D14C] FOREIGN KEY ([GroupId]) REFERENCES dbo.Groups ([GroupId]);
ALTER TABLE dbo.UserRoles ADD CONSTRAINT [FK__UserRoles__RoleI__7AF13DF7] FOREIGN KEY ([RoleId]) REFERENCES dbo.Roles ([RoleId]);
ALTER TABLE wms.OrderDetail_Staging ADD CONSTRAINT [FK_OrderDetailStaging_Header] FOREIGN KEY ([WMSOrderHeaderStagingId]) REFERENCES wms.OrderHeader_Staging ([WMSOrderHeaderStagingId]);
