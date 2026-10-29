"""Copies the five WMS lab tables from Azure SQL (schema wmslab) into Snowflake
(WMSLAB.RAW) through an internal stage, then reconciles the two sides.

One-time setup: snowflake/sql/00_setup.sql in Snowsight, then
`python snowflake/make_keypair.py` and register the printed public key.
After that, with `az login` done:

    python snowflake/copy_azuresql_to_snowflake.py

Steps:
  1. Extract each table from Azure SQL to a local CSV (header row, ISO dates).
  2. PUT each CSV to @WMSLAB.RAW.LOAD_STAGE/<table>/ (gzip on upload).
  3. In one transaction: DELETE + COPY INTO every table, ON_ERROR=ABORT_STATEMENT.
     FORCE=TRUE because COPY skips files it loaded in the last 64 days, and
     every run re-uses the same file names.
  4. Reconcile row counts plus SUM/MIN/MAX checks on both sides; any mismatch
     exits non-zero and is recorded in LOAD_LOG.

Azure SQL connection reuses powerbi/copy_db2_to_azuresql.py (az token auth,
retry while the free-tier database resumes).
"""
import csv
import os
import sys
import tempfile
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives import serialization

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "powerbi"))
from copy_db2_to_azuresql import DATABASE, TABLES, connect_sql  # noqa: E402

SF_ACCOUNT = os.environ.get("SNOWFLAKE_ACCOUNT", "rrtrzrl-tj58203")
SF_USER = os.environ.get("SNOWFLAKE_USER", "CARNETT909")
SF_ROLE = os.environ.get("SNOWFLAKE_ROLE", "WMSLAB_LOADER")
SF_WAREHOUSE = os.environ.get("SNOWFLAKE_WAREHOUSE", "WMSLAB_WH")
KEY_PATH = Path(os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH", Path.home() / ".snowflake" / "wmslab_rsa_key.p8"))
DDL_PATH = HERE / "sql" / "01_tables.sql"
STAGE = "@WMSLAB.RAW.LOAD_STAGE"

# Fingerprint per table: row count plus a few aggregates that catch truncated,
# duplicated, or mis-typed rows. Same SQL text runs on both sides; {len} is
# LEN on SQL Server and LENGTH on Snowflake.
CHECKS = {
    "WAREHOUSE": "COUNT(*), MIN(WAREHOUSE_ID), MAX(WAREHOUSE_ID)",
    "ITEM": "COUNT(*), SUM(UNIT_COST), MAX({len}(DESCRIPTION))",
    "LOCATION": "COUNT(*), COUNT(DISTINCT LOCATION_CODE), SUM(BAY)",
    "INVENTORY": "COUNT(*), SUM(ON_HAND_QTY), SUM(RESERVED_QTY), MIN(RECEIVED_DATE), MAX(RECEIVED_DATE)",
    "LOT_ATTRIBUTE": "COUNT(*), MIN(MFG_DATE), MAX(MFG_DATE), SUM(MFG_WEEK)",
}
VALUE_CHECK = ("SUM(inv.ON_HAND_QTY * i.UNIT_COST)",
               "{s}.INVENTORY inv JOIN {s}.ITEM i ON i.ITEM_ID = inv.ITEM_ID")


def connect_snowflake():
    if not KEY_PATH.exists():
        sys.exit(f"No private key at {KEY_PATH}; run snowflake/make_keypair.py first.")
    key = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
    return snowflake.connector.connect(
        account=SF_ACCOUNT, user=SF_USER, role=SF_ROLE, warehouse=SF_WAREHOUSE,
        private_key=key.private_bytes(serialization.Encoding.DER,
                                      serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()),
        session_parameters={"QUERY_TAG": "wmslab-copy"},
    )


def extract(cursor, workdir: Path) -> dict[str, int]:
    counts = {}
    for table, cols in TABLES.items():
        names = [c for c, _ in cols]
        cursor.execute(f"SELECT {', '.join(names)} FROM wmslab.{table}")
        rows = cursor.fetchall()
        with open(workdir / f"{table.lower()}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
            w.writerow(names)
            for row in rows:
                w.writerow("" if v is None else v.isoformat() if hasattr(v, "isoformat") else v for v in row)
        counts[table] = len(rows)
        print(f"Azure SQL wmslab.{table}: {len(rows)} rows")
    return counts


def load(sf, workdir: Path):
    sf.execute_string(DDL_PATH.read_text(encoding="utf-8"), remove_comments=True)
    cur = sf.cursor()

    for table in TABLES:
        path = (workdir / f"{table.lower()}.csv").as_posix()
        cur.execute(f"PUT 'file://{path}' {STAGE}/{table.lower()}/ OVERWRITE = TRUE AUTO_COMPRESS = TRUE")

    cur.execute("BEGIN")
    try:
        for table, cols in TABLES.items():
            names = ", ".join(c for c, _ in cols)
            cur.execute(f"DELETE FROM WMSLAB.RAW.{table}")
            cur.execute(f"COPY INTO WMSLAB.RAW.{table} ({names}) FROM {STAGE}/{table.lower()}/ "
                        "ON_ERROR = ABORT_STATEMENT FORCE = TRUE")
            loaded = sum(r[3] for r in cur.fetchall())  # (file, status, rows_parsed, rows_loaded, ...)
            print(f"Snowflake RAW.{table}: COPY loaded {loaded} rows")
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise


def fingerprint(cursor, schema: str, len_fn: str) -> dict[str, tuple]:
    out = {}
    for table, exprs in CHECKS.items():
        cursor.execute(f"SELECT {exprs.format(len=len_fn)} FROM {schema}.{table}")
        out[table] = tuple(cursor.fetchone())
    expr, src = VALUE_CHECK
    cursor.execute(f"SELECT {expr} FROM {src.format(s=schema)}")
    out["INVENTORY_VALUE"] = tuple(cursor.fetchone())
    return out


def norm(v):
    # Driver types differ (Decimal vs int, date vs datetime.date): compare as text.
    if v is None:
        return None
    if hasattr(v, "normalize"):
        return format(v.normalize(), "f")
    return str(v)


def main():
    az = connect_sql()
    az_cur = az.cursor()
    sf = connect_snowflake()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            counts = extract(az_cur, Path(tmp))
            load(sf, Path(tmp))

        sf_cur = sf.cursor()
        sf_cur.execute("ALTER SESSION SET QUERY_TAG = 'wmslab-reconcile'")
        src = fingerprint(az_cur, "wmslab", "LEN")
        dst = fingerprint(sf_cur, "WMSLAB.RAW", "LENGTH")

        ok = True
        print("\nReconcile (Azure SQL vs Snowflake):")
        for name in src:
            a, b = [tuple(norm(v) for v in t) for t in (src[name], dst[name])]
            match = a == b
            ok &= match
            print(f"  {'OK  ' if match else 'DIFF'} {name}: {a}" + ("" if match else f" vs {b}"))

        row_counts = ", ".join(f"{t}={n}" for t, n in counts.items())
        sf_cur.execute("INSERT INTO WMSLAB.RAW.LOAD_LOG (SOURCE, ROW_COUNTS, RECONCILED) VALUES (%s, %s, %s)",
                       (f"Azure SQL {DATABASE}.wmslab", row_counts, ok))
        print(f"\n{'Reconciled' if ok else 'MISMATCH'}: {row_counts}")
        if not ok:
            sys.exit(2)
    finally:
        sf.close()
        az.close()


if __name__ == "__main__":
    main()
