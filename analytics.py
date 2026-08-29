import os
import io
import pandas as pd
from datetime import datetime
from sheets_client import _get_sheet
from google import genai
from google.genai import types

def perform_analysis(query: str) -> str:
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    if not GEMINI_API_KEY:
        return '❌ GEMINI_API_KEY is not set.'

    # Fetch data from Google Sheet
    try:
        ws = _get_sheet()
        records = ws.get_all_records()
        if not records:
            return '📭 No expenses logged yet.'
    except Exception as e:
        return f'❌ Failed to fetch data from Google Sheets: {e}'

    # Convert to DataFrame for basic cleaning
    df = pd.DataFrame(records)
    
    # We only send essential columns to Gemini to save tokens
    # Expected cols: Timestamp, Sender, Merchant, Date, Total, Currency, Raw Text
    cols_to_keep = ['Date', 'Merchant', 'Total', 'Currency']
    available_cols = [c for c in cols_to_keep if c in df.columns]
    df_clean = df[available_cols].copy()
    
    csv_data = df_clean.to_csv(index=False)
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    if not query:
        prompt = (
            'You are a financial advisor. I am providing you with my family expense data in CSV format. '
            'Please provide a brief, well-formatted markdown summary of our spending. '
            'Include:\n'
            '- Total amount spent\n'
            '- Top 3 merchants by spending\n'
            '- A quick insight or trend if any.\n'
            'Keep it concise and readable for a Telegram message.'
        )
    else:
        prompt = (
            'You are a financial advisor. I am providing you with my family expense data in CSV format. '
            f'Please answer the following question based on the data: {query}\n'
            'Keep your answer concise and well-formatted for a Telegram message.'
        )

    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=[csv_data, prompt],
        )
        return response.text
    except Exception as e:
        return f'❌ AI Analysis failed: {e}'
