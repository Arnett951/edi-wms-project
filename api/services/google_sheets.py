import base64
import json
import os

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


def get_sheets_service():
    encoded_credentials = os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_JSON_BASE64"
    )

    if not encoded_credentials:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 is not configured"
        )

    credential_json = base64.b64decode(
        encoded_credentials
    ).decode("utf-8")

    credential_info = json.loads(credential_json)

    credentials = Credentials.from_service_account_info(
        credential_info,
        scopes=[SHEETS_SCOPE],
    )

    return build(
        "sheets",
        "v4",
        credentials=credentials,
        cache_discovery=False,
    )


def update_sheet_values(
    spreadsheet_id: str,
    sheet_range: str,
    values: list[list],
) -> dict:
    service = get_sheets_service()

    return (
        service.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=sheet_range,
            valueInputOption="RAW",
            body={"values": values},
        )
        .execute()
    )