# Legacy IBM i-style SQL: lab + reference sheet

`LGCYLIB` is a copy of the WMS lab data reshaped the way RPG-era IBM i applications
often store it: short cryptic names, blank-padded `CHAR`, numeric dates and times,
one-letter status codes, and natural keys. It illustrates the *conventions*; it is not
the schema of Manhattan WMi or any real product.

| File | What it does |
| --- | --- |
| `01_create_lgcylib.sql` | Creates the 5 files, adds column text, and loads them from `WMS.*` with conversions |
| `02_inventory_aging_legacy.sql` | The Inventory Aging dataset rewritten against the legacy files, with the same output columns so `WAREHOUSE.rtf` renders it unchanged |
| `03_reconcile.sql` | Diffs old query vs new query (`EXCEPT ALL` both ways): 0 / 0 rows, 44 = 44, $330,816 = $330,816 |

```
db2 -tf 01_create_lgcylib.sql     # as the instance owner, inside the dhl-db2 container
```

Files: `WHSMSTP` (warehouse), `ITMMSTP` (item), `LOCMSTP` (location), `INVLOTP`
(inventory by lot/location), `LOTATRP` (lot/DOT attributes).

---

## Reference sheet

Tested on Db2 LUW 12.1 in this lab. On Db2 for i these are standard SQL, but confirm
on the real system (IBM i release matters; `VARCHAR_FORMAT` and `TIMESTAMP_FORMAT`
with these patterns need a reasonably current release, 7.2 or later is a safe assumption).
The `SUBSTR` fallbacks work everywhere.

### Numeric date/time → real DATE/TIME/TIMESTAMP

```sql
-- YYYYMMDD  DECIMAL(8,0)  e.g. 20260527
CASE WHEN col = 0 THEN NULL ELSE DATE(TIMESTAMP_FORMAT(DIGITS(col), 'YYYYMMDD')) END

-- CYYMMDD   DECIMAL(7,0)  e.g. 1260527  (C: 0 = 19xx, 1 = 20xx)   add 19000000 -> YYYYMMDD
CASE WHEN col = 0 THEN NULL
     ELSE DATE(TIMESTAMP_FORMAT(DIGITS(DECIMAL(col + 19000000, 8, 0)), 'YYYYMMDD')) END

-- HHMMSS    DECIMAL(6,0)  e.g. 73117 = 07:31:17   (DIGITS restores the leading zero)
TIME(TIMESTAMP_FORMAT(DIGITS(tcol), 'HH24MISS'))

-- date + time columns -> one TIMESTAMP
TIMESTAMP_FORMAT(DIGITS(dcol) || DIGITS(tcol), 'YYYYMMDDHH24MISS')

-- Fallback that works on any release: build an ISO string
DATE(SUBSTR(DIGITS(col),1,4) || '-' || SUBSTR(DIGITS(col),5,2) || '-' || SUBSTR(DIGITS(col),7,2))
```

**Why `DIGITS()` and not `CHAR()`:** `DIGITS` returns fixed-width with leading zeros
(`073117`); `CHAR` drops them (`73117`) and the format mask misreads it.

**`0` means "no date".** Convert it to `NULL` first, or the conversion fails. The same goes
for other garbage (`99999999`, `20260231`): one bad row fails the **whole query**.
When the data is suspect, guard it:
`CASE WHEN col BETWEEN 19000101 AND 20991231 AND MOD(col,100) BETWEEN 1 AND 31 THEN ... END`.

### DATE → numeric (for filters and for writing back)

```sql
YEAR(d) * 10000 + MONTH(d) * 100 + DAY(d)              -- YYYYMMDD, works everywhere
INTEGER(VARCHAR_FORMAT(d, 'YYYYMMDD'))                  -- same, newer releases
(YEAR(d) - 1900) * 10000 + MONTH(d) * 100 + DAY(d)     -- CYYMMDD
```

### Filter on the raw column: convert the constant, not the column

```sql
-- Index-friendly: the numeric column is compared as-is
WHERE ILRCVD > 0
  AND ILRCVD <= INTEGER(VARCHAR_FORMAT(CURRENT DATE - 7 DAYS, 'YYYYMMDD'))

-- Works, but converts every row first (slow on big WMS files)
WHERE DAYS(CURRENT DATE) - DAYS(DATE(TIMESTAMP_FORMAT(DIGITS(ILRCVD), 'YYYYMMDD'))) >= 7
```

### Fixed-length CHAR

- `TRIM()` every `CHAR` column that leaves the query, or XML, Excel and BI Publisher
  output carry trailing blanks (`"TIRE-001       "`).
- Comparisons ignore trailing blanks (`ILWHSE = 'PERRIS'` matches `'PERRIS    '`), so
  equality joins and parameters work untrimmed.
- `LIKE`, `LENGTH()` and `||` do **not** ignore them: `TRIM` first.
- Inserting a longer value errors rather than truncating. The lab hit this: zone
  `RECEIVING` (9 chars) into `CHAR(8)`, `SQL0433N`.

### Codes, keys, isolation

```sql
CASE ILSTAT WHEN 'A' THEN 'AVAILABLE' WHEN 'H' THEN 'HOLD' WHEN 'D' THEN 'DAMAGED' ELSE 'UNKNOWN' END
```

- **No surrogate IDs:** join on *every* natural-key column (`LMWHSE` **and** `LMLOC`).
  Joining on location alone silently multiplies rows across warehouses.
- **Reporting isolation:** end ad hoc and report SQL with `WITH UR` (read uncommitted)
  so it never waits on, or locks, warehouse transactions. On IBM i, `WITH NC` (no commit)
  is also common.

### Finding your way around an unfamiliar schema

| | Db2 for i | Db2 LUW (this lab) |
| --- | --- | --- |
| Tables + description | `QSYS2.SYSTABLES` (`TABLE_SCHEMA`, `TABLE_NAME`, `TABLE_TEXT`, `SYSTEM_TABLE_NAME`) | `SYSCAT.TABLES` (`TABSCHEMA`, `TABNAME`, `REMARKS`) |
| Columns + description | `QSYS2.SYSCOLUMNS` (`COLUMN_NAME`, `COLUMN_TEXT`, `DATA_TYPE`, `LENGTH`, `NUMERIC_SCALE`) | `SYSCAT.COLUMNS` (`COLNAME`, `REMARKS`, `TYPENAME`, `LENGTH`, `SCALE`) |
| Name a schema | a *library* (`LGCYLIB`) | a schema |
| Qualify a table | SQL naming `LIB.FILE`; system naming `LIB/FILE` | `SCHEMA.TABLE` |
| Query tool | IBM i Access Client Solutions → Run SQL Scripts | DBeaver / `db2` CLP |
| BI Publisher JDBC | IBM Toolbox for Java (jt400), `jdbc:as400://host` | `db2jcc4`, `jdbc:db2://host:50000/DB` |

```sql
-- "Which column holds the received date?" Search the column text, not just the names.
SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TEXT, DATA_TYPE, LENGTH, NUMERIC_SCALE
FROM QSYS2.SYSCOLUMNS
WHERE TABLE_SCHEMA = 'LIBNAME'
  AND (UPPER(COLUMN_TEXT) LIKE '%RECV%' OR UPPER(COLUMN_TEXT) LIKE '%RCV%' OR COLUMN_NAME LIKE '%RCV%');
```

### Verify every rewrite

Diff old vs new with `EXCEPT ALL` in **both** directions, plus row counts and a money
total (see `03_reconcile.sql`). "It looks right" isn't proof; 0 / 0 rows and matching
totals are.
