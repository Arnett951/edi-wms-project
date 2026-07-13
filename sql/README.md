# SQL Objects

Source-controlled snapshot of the database objects for `free-sql-db-5402162`
(Azure SQL Database, server `sql-lab-data-eng-baby.database.windows.net`),
scripted directly from the live database.

## Deployment order

Objects have cross-dependencies (foreign keys, procedures referencing
tables), so apply them in this order:

1. `tables/` - `CREATE TABLE` for every base table (dbo and wms schemas)
2. `constraints/primary_keys.sql`
3. `constraints/foreign_keys.sql`
4. `indexes/indexes.sql` - non-PK indexes
5. `functions/`
6. `views/`
7. `procedures/`

## Layout

- `tables/` - one file per table, named `<schema>.<table>.sql`
- `constraints/` - primary key and foreign key `ALTER TABLE` statements
- `indexes/` - non-PK nonclustered/unique indexes
- `functions/` - scalar and table-valued functions
- `views/` - views
- `procedures/` - stored procedures (dbo and wms schemas)

## Regenerating

These files were scripted from the live database via `INFORMATION_SCHEMA`,
`sys.sql_modules`, and related catalog views, using Azure AD (az login)
authentication. Re-run the same extraction after schema changes to keep
this folder in sync - there is currently no automated CI step for it.
