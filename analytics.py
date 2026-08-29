import os
import time
import re
import pandas as pd
from sheets_client import _get_sheet
from google import genai
from google.genai import types

# Same fallback model chain as ocr.py
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
]

def _generate_with_fallback(client, contents):
    last_error = None
    for model in GEMINI_MODELS:
        try:
            print(f"[Analytics] Trying model: {model}")
            response = client.models.generate_content(
                model=model,
                contents=contents,
            )
            print(f"[Analytics] Success with model: {model}")
            return response
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                retry_delay = 5
                try:
                    match = re.search(r"retry.*?(\d+)s", error_str, re.IGNORECASE)
                    if match:
                        retry_delay = min(int(match.group(1)), 10)
                except Exception:
                    pass
                print(f"[Analytics] Model {model} quota exhausted. Waiting {retry_delay}s then trying next...")
                time.sleep(retry_delay)
                last_error = e
                continue
            else:
                raise
    raise Exception(f"All Gemini models exhausted. Last error: {last_error}")


def perform_analysis(query: str) -> str:
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        return "[Error] GEMINI_API_KEY is not set."

    try:
        ws = _get_sheet()
        records = ws.get_all_records()
        if not records:
            return "[Empty] No expenses logged yet."
    except Exception as e:
        return f"[Error] Failed to fetch data from Google Sheets: {e}"

    df = pd.DataFrame(records)
    cols_to_keep = ["Date", "Merchant", "Total", "Currency"]
    available_cols = [c for c in cols_to_keep if c in df.columns]
    df_clean = df[available_cols].copy()
    csv_data = df_clean.to_csv(index=False)

    client = genai.Client(api_key=GEMINI_API_KEY)

    if not query:
        prompt = (
            "You are a financial advisor. I am providing you with my family expense data in CSV format.\n"
            "Please provide a brief, well-formatted summary of our spending. Include:\n"
            "- Total amount spent\n"
            "- Top 3 merchants by spending\n"
            "- A quick insight or trend if any.\n"
            "Keep it concise and readable for a Telegram message (no markdown headers, use plain text)."
        )
    else:
        prompt = (
            "You are a financial advisor. I am providing you with my family expense data in CSV format.\n"
            f"Please answer the following question based on the data: {query}\n"
            "Keep your answer concise and readable for a Telegram message."
        )

    try:
        response = _generate_with_fallback(client, [csv_data, prompt])
        return response.text
    except Exception as e:
        return f"[Error] AI Analysis failed after trying all models: {e}"
