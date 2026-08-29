import os
import json
from datetime import datetime
import requests
from google import genai
from google.genai import types

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

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

def extract_text(image_bytes: bytes) -> str:
    """
    Since we merged extraction and parsing into a single Gemini call, 
    we just return a placeholder or bypass this in app.py.
    For compatibility with app.py's current flow, we will pass the bytes directly.
    """
    return image_bytes

def parse_receipt(image_bytes: bytes) -> dict:
    """
    Sends the receipt image to Gemini 1.5 Flash to extract structured data.
    Returns the exact same dictionary format the rest of the app expects.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set. Please add it to your environment variables.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    
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
    
    # We pass the raw image bytes to Gemini
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=[
            types.Part.from_bytes(
                data=image_bytes,
                mime_type='image/jpeg',
            ),
            prompt
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1
        )
    )
    
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
