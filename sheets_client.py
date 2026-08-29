"""
Thin wrapper around gspread for appending expense rows to a Google Sheet.
Auth uses a free Google Cloud service account (no billing required for
Sheets API at this volume). See README.md for setup steps.
"""
import json
import os
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

HEADER = ["Timestamp", "Sender", "Merchant", "Date", "Total", "Currency", "Raw Text"]

_sheet = None


def _get_sheet():
    global _sheet
    if _sheet is not None:
        return _sheet

    creds_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    sheet_id = os.environ["SHEET_ID"]

    info = json.loads(creds_json)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    client = gspread.authorize(creds)

    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.sheet1

    if worksheet.row_values(1) != HEADER:
        worksheet.insert_row(HEADER, 1)

    _sheet = worksheet
    return _sheet


def append_expense(sender: str, parsed: dict):
    ws = _get_sheet()
    ws.append_row(
        [
            datetime.utcnow().isoformat(timespec="seconds"),
            sender,
            parsed.get("merchant") or "",
            parsed.get("date") or "",
            parsed.get("total") if parsed.get("total") is not None else "",
            parsed.get("currency") or "",
            parsed.get("raw_text") or "",
        ],
        value_input_option="USER_ENTERED",
    )
