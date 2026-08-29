import os
import json
import time
from datetime import datetime
import requests
from google import genai
from google.genai import types

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

# Fallback chain: if one model hits its daily/minute quota, the next is tried automatically.
# All are free-tier Gemini models.
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
]

def _get_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set. Please add it to your environment variables.")
    return genai.Client(api_key=api_key)

def _generate_with_fallback(client, contents, config):
    """
    Tries each model in GEMINI_MODELS in order.
    On a 429 quota error, waits the suggested retry delay then tries the next model.
    Raises an exception only if all models are exhausted.
    """
    last_error = None
    for model in GEMINI_MODELS:
        try:
            print(f"[Gemini] Trying model: {model}")
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            print(f"[Gemini] Success with model: {model}")
            return response
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                # Parse retry delay from error message if available
                retry_delay = 5
                try:
                    import re
                    match = re.search(r"retry.*?(\d+)s", error_str, re.IGNORECASE)
                    if match:
                        retry_delay = min(int(match.group(1)), 10)
                except Exception:
                    pass
                print(f"[Gemini] Model {model} quota exhausted. Waiting {retry_delay}s before trying next model...")
                time.sleep(retry_delay)
                last_error = e
                continue
            else:
                # Non-quota error — raise immediately
                raise
    raise Exception(f"All Gemini models exhausted. Last error: {last_error}")


def download_telegram_file(bot_token: str, file_id: str) -> bytes:
    """Resolve a Telegram file_id to bytes using the Bot API."""
    meta_url = TELEGRAM_API.format(token=bot_token, method="getFile")
    resp = requests.get(meta_url, params={"file_id": file_id}, timeout=30)
    resp.raise_for_status()
    file_path = resp.json()["result"]["file_path"]

    file_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
    file_resp = requests.get(file_url, timeout=30)
    file_resp.raise_for_status()
    return file_resp.content


def parse_receipt(image_bytes: bytes) -> dict:
    """
    Sends the receipt image to Gemini to extract structured data.
    Automatically falls back through free-tier models if quota is exceeded.
    """
    client = _get_gemini_client()

    prompt = '''
    You are an expert receipt parser. Analyze this receipt image (which may be in Arabic, English, or both).
    Extract the following information and return it STRICTLY as a JSON object:
    - "merchant": The name of the store, restaurant, or business. Ignore taglines like "Welcome" or "Tax Invoice".
    - "date": The date of the receipt in YYYY-MM-DD format. If missing, return null.
    - "total": The final grand total amount as a float number (e.g. 125.50).
    - "currency": The currency code (e.g. "EGP", "SAR", "USD"). Default to "EGP" if unsure.
    - "raw_text": A brief 1-2 sentence summary of the items purchased, for context.
    
    Return ONLY valid JSON.
    '''

    contents = [
        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
        prompt,
    ]
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.1,
    )

    response = _generate_with_fallback(client, contents, config)

    try:
        parsed = json.loads(response.text)
    except Exception as e:
        print(f"[OCR ERROR] Failed to parse JSON from Gemini: {response.text}")
        parsed = {}

    return {
        "merchant": parsed.get("merchant"),
        "date": parsed.get("date") or datetime.utcnow().strftime("%Y-%m-%d"),
        "total": parsed.get("total"),
        "currency": parsed.get("currency") or "EGP",
        "raw_text": parsed.get("raw_text") or "No text extracted.",
    }
