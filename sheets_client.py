import json
import os
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file',
]

HEADER = ['Timestamp', 'Sender', 'Merchant', 'Date', 'Total', 'Currency', 'Raw Text']
_client = None
_spreadsheet = None

def _get_spreadsheet():
    global _client, _spreadsheet
    if _spreadsheet is not None:
        return _spreadsheet

    creds_json = os.environ['GOOGLE_SERVICE_ACCOUNT_JSON']
    sheet_id = os.environ['SHEET_ID']

    info = json.loads(creds_json)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    _client = gspread.authorize(creds)
    _spreadsheet = _client.open_by_key(sheet_id)
    return _spreadsheet

def _get_sheet():
    spreadsheet = _get_spreadsheet()
    worksheet = spreadsheet.sheet1
    if worksheet.row_values(1) != HEADER:
        worksheet.insert_row(HEADER, 1)
    return worksheet

def append_expense(sender: str, parsed: dict):
    ws = _get_sheet()
    ws.append_row(
        [
            datetime.utcnow().isoformat(timespec='seconds'),
            sender,
            parsed.get('merchant') or '',
            parsed.get('date') or '',
            parsed.get('total') if parsed.get('total') is not None else '',
            parsed.get('currency') or '',
            parsed.get('raw_text') or '',
        ],
        value_input_option='USER_ENTERED',
    )

def deduplicate_sheet():
    spreadsheet = _get_spreadsheet()
    ws = spreadsheet.sheet1
    
    try:
        deleted_ws = spreadsheet.worksheet('Deleted Duplicates')
    except gspread.exceptions.WorksheetNotFound:
        deleted_ws = spreadsheet.add_worksheet(title='Deleted Duplicates', rows='100', cols='20')
        deleted_ws.insert_row(HEADER, 1)

    records = ws.get_all_values()
    if len(records) <= 1:
        return 0
        
    seen = set()
    to_delete = []
    to_move = []
    
    # We iterate backwards so deleting rows later doesn't shift the indices of rows we want to delete
    # But wait, gspread's delete_rows takes a list or we delete from bottom to top.
    # We'll identify indices from top to bottom.
    
    # We skip the header (index 0). Row numbers in gspread are 1-based, so row 2 is index 1.
    for idx, row in enumerate(records[1:], start=2):
        if len(row) < 5:
            continue
        # Duplicate key: Date, Merchant, Total
        key = (str(row[3]).strip(), str(row[2]).strip(), str(row[4]).strip())
        if key in seen:
            to_delete.append(idx)
            to_move.append(row)
        else:
            if all(key):  # Only track if not totally empty
                seen.add(key)
                
    if to_move:
        deleted_ws.append_rows(to_move, value_input_option='USER_ENTERED')
        
    # Delete backwards to not mess up indices
    for idx in sorted(to_delete, reverse=True):
        ws.delete_rows(idx)
        
    return len(to_delete)
