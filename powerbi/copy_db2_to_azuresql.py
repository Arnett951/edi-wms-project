"""Copies the five inventory-aging tables from Db2 (Skynet, TIREWMS / WMS) into
Azure SQL (schema wmslab) so Power BI can refresh without a gateway.

Run from a machine on the tailnet with `ssh skynet` working and `az login` done:

    python powerbi/copy_db2_to_azuresql.py

Extract: `db2 EXPORT ... OF DEL` inside the dhl-db2 container over ssh (SELECTs only).
Load: creates the wmslab tables/view if missing, then truncates and reloads all
five tables in one transaction, so a failed run leaves the previous copy intact.
Auth to Azure SQL is the same az access-token pattern as sql/deploy.py.
"""
import csv
import io
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from datetime import date
from decimal import Decimal

import pyodbc

SERVER = os.environ.get("SQL_SERVER", "sql-lab-data-eng-baby.database.windows.net")
DATABASE = os.environ.get("SQL_DATABASE", "free-sql-db-5402162")
SSH_HOST = os.environ.get("DB2_SSH_HOST", "skynet")
DDL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sql", "01_wmslab_tables.sql")

SQL_COPT_SS_ACCESS_TOKEN = 1256

# Column lists are explicit so the DEL field order is fixed. Types: i=int, s=str, d=date, n=decimal.
TABLES = {
    "WAREHOUSE": [("WAREHOUSE_ID", "i"), ("WAREHOUSE_CODE", "s"), ("WAREHOUSE_NAME", "s"),
                  ("ADDRESS_LINE1", "s"), ("CITY", "s"), ("STATE_CODE", "s"),
                  ("POSTAL_CODE", "s"), ("SHIPPER_ID", "s")],
    "ITEM": [("ITEM_ID", "i"), ("SKU", "s"), ("DESCRIPTION", "s"), ("TIRE_SIZE", "s"),
             ("UNIT_COST", "n"), ("UNIT_WEIGHT_LBS", "n"), ("UNITS_PER_PALLET", "i")],
    "LOCATION": [("LOCATION_ID", "i"), ("WAREHOUSE_ID", "i"), ("LOCATION_CODE", "s"),
                 ("ZONE", "s"), ("AISLE", "s"), ("BAY", "i"), ("RACK_LEVEL", "i")],
    "INVENTORY": [("INVENTORY_ID", "i"), ("LOCATION_ID", "i"), ("ITEM_ID", "i"),
                  ("LOT_NUMBER", "s"), ("RECEIVED_DATE", "d"), ("STOCK_STATUS", "s"),
                  ("ON_HAND_QTY", "i"), ("RESERVED_QTY", "i")],
    "LOT_ATTRIBUTE": [("LOT_NUMBER", "s"), ("ITEM_ID", "i"), ("DOT_CODE", "s"),
                      ("MFG_WEEK", "i"), ("MFG_YEAR", "i"), ("MFG_DATE", "d")],
}

CONVERT = {
    "i": int,
    "s": str,
    "d": date.fromisoformat,
    "n": Decimal,
}


def export_db2(table: str, cols: list[tuple[str, str]]) -> list[tuple]:
    select = f"SELECT {', '.join(c for c, _ in cols)} FROM WMS.{table} WITH UR"
    tmp = f"/tmp/pbi_{table.lower()}.del"
    inner = (
        "db2 connect to TIREWMS >/dev/null && "
        f"db2 \\\"EXPORT TO {tmp} OF DEL MODIFIED BY DATESISO STRIPLZEROS DECPLUSBLANK {select}\\\" >/dev/null && "
        f"cat {tmp}; rm -f {tmp}"
    )
    cmd = ["ssh", SSH_HOST, f"docker exec dhl-db2 su - db2inst1 -c \"{inner}\""]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout

    rows = []
    for rec in csv.reader(io.StringIO(out)):
        if not rec:
            continue
        if len(rec) != len(cols):
            raise ValueError(f"WMS.{table}: expected {len(cols)} fields, got {len(rec)}: {rec}")
        rows.append(tuple(
            None if v.strip() == "" else CONVERT[t](v.strip() if t != "s" else v.rstrip())
            for v, (_, t) in zip(rec, cols)
        ))
    return rows


def get_access_token() -> bytes:
    az_cmd = shutil.which("az")
    if az_cmd is None:
        raise RuntimeError("az CLI not found on PATH")
    token = subprocess.run(
        [az_cmd, "account", "get-access-token", "--resource", "https://database.windows.net/",
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, check=True,
    ).stdout.strip().encode("utf-16-le")
    return struct.pack(f"<I{len(token)}s", len(token), token)


def connect_sql(attempts: int = 6):
    # The free-tier database auto-pauses; the first connect wakes it and fails with 40613.
    for n in range(1, attempts + 1):
        try:
            return pyodbc.connect(
                f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={SERVER};DATABASE={DATABASE};"
                "Encrypt=yes;TrustServerCertificate=no;",
                attrs_before={SQL_COPT_SS_ACCESS_TOKEN: get_access_token()},
                timeout=90,
            )
        except pyodbc.Error as exc:
            if "40613" not in str(exc) or n == attempts:
                raise
            print(f"Azure SQL is resuming (attempt {n}/{attempts}), retrying in 20s...")
            time.sleep(20)


def ensure_schema(cursor):
    ddl = open(DDL_PATH, encoding="utf-8").read()
    for batch in re.split(r"^\s*GO\s*$", ddl, flags=re.MULTILINE):
        if batch.strip():
            cursor.execute(batch)
    cursor.commit()


def main():
    extracted = {}
    for table, cols in TABLES.items():
        extracted[table] = export_db2(table, cols)
        print(f"Db2 WMS.{table}: {len(extracted[table])} rows")

    conn = connect_sql()
    conn.autocommit = False
    cursor = conn.cursor()
    ensure_schema(cursor)

    cursor.fast_executemany = True
    try:
        for table, cols in TABLES.items():
            names = ", ".join(c for c, _ in cols)
            marks = ", ".join("?" for _ in cols)
            cursor.execute(f"DELETE FROM wmslab.{table}")
            if extracted[table]:
                cursor.executemany(f"INSERT INTO wmslab.{table} ({names}) VALUES ({marks})", extracted[table])
        counts = ", ".join(f"{t}={len(r)}" for t, r in extracted.items())
        cursor.execute("INSERT INTO wmslab.LOAD_LOG (SOURCE, ROW_COUNTS) VALUES (?, ?)",
                       "Db2 TIREWMS.WMS", counts)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f"Loaded into {DATABASE}.wmslab: {counts}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"Command failed: {exc.cmd}\n{exc.stderr}", file=sys.stderr)
        sys.exit(1)
