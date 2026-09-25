-- ============================================================================
-- Impact analysis practice: which views / procedures / triggers use
-- WMS.SHIPMENT.BOL_NUMBER?
--
-- Part 1 creates three objects to find (kept in the lab on purpose):
--   V_BOL_TEST      view that uses BOL_NUMBER
--   V_TRAILER_TEST  view on SHIPMENT that does NOT use BOL_NUMBER
--   P_BOL_TEST      SQL procedure that uses BOL_NUMBER
-- Part 2 is the lookup.
--   Dependency catalog = table level: finds all three (V_TRAILER_TEST is a false positive).
--   Text search        = column level: finds V_BOL_TEST and P_BOL_TEST only.
-- Use dependencies for the complete list, text search to narrow it to the column.
--
-- Blind spot: SQL outside the database (BI Publisher data models, RPG programs,
-- Query/400, ETL jobs, the report folders in this repo) is invisible to the catalog.
--
-- Part 1 once:  db2 -td@ -f 03_impact_analysis.sql   (uses @ as the terminator)
-- ============================================================================

CONNECT TO TIREWMS@

-- ---------------------------------------------------------------- part 1: objects to find
CREATE VIEW BAK20260925.V_BOL_TEST AS
    SELECT BOL_NUMBER, TRAILER_NUMBER FROM WMS.SHIPMENT@

CREATE VIEW BAK20260925.V_TRAILER_TEST AS
    SELECT SHIPMENT_ID, TRAILER_NUMBER FROM WMS.SHIPMENT@

CREATE PROCEDURE BAK20260925.P_BOL_TEST (IN P_BOL CHAR(17), OUT P_TRAILER VARCHAR(15))
LANGUAGE SQL
BEGIN
    SELECT TRAILER_NUMBER INTO P_TRAILER FROM WMS.SHIPMENT WHERE BOL_NUMBER = P_BOL;
END@

-- ---------------------------------------------------------------- part 2: the lookup
-- Column level: search the stored SQL. REGEXP_LIKE with the i flag works on the CLOB
-- directly; UPPER(TEXT) LIKE fails on large definitions (SQL0433N too long).
-- Skip the SYS schemas or the catalog's own views flood the results.
SELECT 'VIEW text' AS FOUND_BY, VIEWSCHEMA AS OBJ_SCHEMA, VIEWNAME AS OBJ_NAME
FROM SYSCAT.VIEWS
WHERE VIEWSCHEMA NOT LIKE 'SYS%' AND REGEXP_LIKE(TEXT, 'BOL_NUMBER', 'i')
UNION ALL
SELECT 'ROUTINE text', ROUTINESCHEMA, ROUTINENAME
FROM SYSCAT.ROUTINES
WHERE ROUTINESCHEMA NOT LIKE 'SYS%' AND REGEXP_LIKE(TEXT, 'BOL_NUMBER', 'i')
UNION ALL
SELECT 'TRIGGER text', TRIGSCHEMA, TRIGNAME
FROM SYSCAT.TRIGGERS
WHERE REGEXP_LIKE(TEXT, 'BOL_NUMBER', 'i')
UNION ALL
-- Table level: every view that depends on WMS.SHIPMENT
SELECT 'VIEW depends on table', VIEWSCHEMA, VIEWNAME
FROM SYSCAT.VIEWDEP
WHERE BSCHEMA = 'WMS' AND BNAME = 'SHIPMENT' AND BTYPE = 'T'
UNION ALL
-- Table level: SQL procedures record dependencies through their compiled package
SELECT 'ROUTINE depends on table', r.ROUTINESCHEMA, r.ROUTINENAME
FROM SYSCAT.ROUTINEDEP d
JOIN SYSCAT.PACKAGEDEP p ON p.PKGSCHEMA = d.BSCHEMA AND p.PKGNAME = d.BNAME AND d.BTYPE = 'K'
JOIN SYSCAT.ROUTINES r ON r.SPECIFICNAME = d.SPECIFICNAME AND r.ROUTINESCHEMA = d.ROUTINESCHEMA
WHERE p.BSCHEMA = 'WMS' AND p.BNAME = 'SHIPMENT' AND p.BTYPE = 'T'
ORDER BY 1, 2, 3@

-- Db2 for i equivalents (not tested here; check column names on the system):
--   QSYS2.SYSVIEWS (VIEW_DEFINITION), QSYS2.SYSROUTINES (ROUTINE_DEFINITION),
--   QSYS2.SYSTRIGGERS (ACTION_STATEMENT), QSYS2.SYSVIEWDEP, QSYS2.SYSROUTINEDEP;
--   DSPPGMREF for which files an RPG / COBOL program uses.

CONNECT RESET@
