"""Deploys sql/ objects to Azure SQL Database in dependency order.

Auth: expects an Azure AD access token for https://database.windows.net/
scope to already be available via `az account get-access-token` (the
GitHub Actions workflow logs in via OIDC using azure/login before this
runs). Each .sql file is executed as a single batch.
"""
import glob
import os
import shutil
import struct
import subprocess
import sys

import pyodbc

SERVER = os.environ["SQL_SERVER"]
DATABASE = os.environ["SQL_DATABASE"]
SQL_DIR = os.path.dirname(os.path.abspath(__file__))

SQL_COPT_SS_ACCESS_TOKEN = 1256


def get_access_token() -> bytes:
    az_cmd = shutil.which("az")
    if az_cmd is None:
        raise RuntimeError("az CLI not found on PATH")
    result = subprocess.run(
        [az_cmd, "account", "get-access-token", "--resource", "https://database.windows.net/",
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, check=True,
    )
    token = result.stdout.strip()
    token_bytes = token.encode("utf-16-le")
    return struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)


def deploy_files(cursor, paths: list[str]):
    for path in paths:
        rel = os.path.relpath(path, SQL_DIR)
        sql = open(path, encoding="utf-8").read()
        print(f"-- deploying {rel}")
        try:
            cursor.execute(sql)
            cursor.commit()
        except Exception as exc:
            print(f"FAILED: {rel}\n{exc}", file=sys.stderr)
            raise


def main():
    token_struct = get_access_token()
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={SERVER};DATABASE={DATABASE};Encrypt=yes;TrustServerCertificate=no;"
    )
    conn = pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct}, timeout=60)
    conn.autocommit = False
    cursor = conn.cursor()

    ordered_groups = [
        sorted(glob.glob(os.path.join(SQL_DIR, "tables", "*.sql"))),
        [os.path.join(SQL_DIR, "constraints", "primary_keys.sql")],
        [os.path.join(SQL_DIR, "constraints", "foreign_keys.sql")],
        [os.path.join(SQL_DIR, "indexes", "indexes.sql")],
        sorted(glob.glob(os.path.join(SQL_DIR, "functions", "*.sql"))),
        sorted(glob.glob(os.path.join(SQL_DIR, "views", "*.sql"))),
        sorted(glob.glob(os.path.join(SQL_DIR, "procedures", "*.sql"))),
    ]

    for group in ordered_groups:
        deploy_files(cursor, group)

    conn.close()
    print("Deploy complete.")


if __name__ == "__main__":
    main()
