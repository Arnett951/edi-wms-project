import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pyodbc


def get_sql_connection() -> pyodbc.Connection:
    server = os.getenv("SQL_SERVER")
    database = os.getenv("SQL_DATABASE")
    username = os.getenv("SQL_USERNAME")
    password = os.getenv("SQL_PASSWORD")

    missing = [
        name
        for name, value in {
            "SQL_SERVER": server,
            "SQL_DATABASE": database,
            "SQL_USERNAME": username,
            "SQL_PASSWORD": password,
        }.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            f"Missing SQL settings: {', '.join(missing)}"
        )

    connection_string = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )

    return pyodbc.connect(connection_string)


def make_sheet_safe(value: Any) -> Any:
    if value is None:
        return ""

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    return value


def query_to_sheet_values(query: str) -> list[list[Any]]:
    with get_sql_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(query)

        column_names = [
            column[0]
            for column in cursor.description
        ]

        rows = cursor.fetchall()

    sheet_rows = [
        [make_sheet_safe(value) for value in row]
        for row in rows
    ]

    return [column_names] + sheet_rows