import os
import json
import time
import base64
import re
from datetime import datetime
import requests
from google import genai
from google.genai import types

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

# ---------------------------------------------------------------------------
# Provider fallback chain
# When a provider's quota is hit, the next one is tried automatically.
# All are free-tier options with vision (image) support.
# ---------------------------------------------------------------------------
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-1.5-flash",
]
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

RECEIPT_PROMPT = '''
You are an expert receipt parser. Analyze this receipt image (which may be in Arabic, English, or both).
Extract the following information and return it STRICTLY as a JSON object:
- "merchant": The name of the store, restaurant, or business. Ignore taglines like "Welcome" or "Tax Invoice".
- "date": The date of the receipt in YYYY-MM-DD format. If missing, return null.
- "total": The final grand total amount as a float number (e.g. 125.50).
- "currency": The currency code (e.g. "EGP", "SAR", "USD"). Default to "EGP" if unsure.
- "raw_text": A brief 1-2 sentence summary of the items purchased, for context.

Return ONLY valid JSON with no markdown code blocks.
'''


def _parse_retry_delay(error_str: str, default: int = 5) -> int:
    try:
        match = re.search(r"retry.*?(\d+)s", error_str, re.IGNORECASE)
        if match:
            return min(int(match.group(1)), 15)
    except Exception:
        pass
    return default


def _try_gemini(image_bytes: bytes) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")
    client = genai.Client(api_key=api_key)
    contents = [
        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
        RECEIPT_PROMPT,
    ]
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.1,
    )
    for model in GEMINI_MODELS:
        try:
            print(f"[OCR] Trying Gemini model: {model}")
            resp = client.models.generate_content(model=model, contents=contents, config=config)
            print(f"[OCR] Gemini success: {model}")
            return resp.text
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                delay = _parse_retry_delay(err)
                print(f"[OCR] Gemini {model} quota hit. Waiting {delay}s...")
                time.sleep(delay)
            else:
                raise
    raise Exception("All Gemini models quota exhausted")


def _try_groq(image_bytes: bytes) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set — skipping Groq fallback")
    try:
        from groq import Groq
    except ImportError:
        raise ValueError("groq package not installed")

    print(f"[OCR] Trying Groq: {GROQ_VISION_MODEL}")
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    client = Groq(api_key=api_key)
    resp = client.chat.completions.create(
        model=GROQ_VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": RECEIPT_PROMPT},
                ],
            }
        ],
        temperature=0.1,
        max_tokens=512,
    )
    print("[OCR] Groq success")
    return resp.choices[0].message.content


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
    Parses a receipt image using Gemini first, then falls back to Groq
    if Gemini quota is exhausted. Both providers are free-tier.
    """
    raw_json = None
    errors = []

    # 1. Try Gemini
    try:
        raw_json = _try_gemini(image_bytes)
    except Exception as e:
        errors.append(f"Gemini: {e}")
        print(f"[OCR] Gemini failed: {e}")

    # 2. Fall back to Groq
    if raw_json is None:
        try:
            raw_json = _try_groq(image_bytes)
        except Exception as e:
            errors.append(f"Groq: {e}")
            print(f"[OCR] Groq failed: {e}")

    if raw_json is None:
        raise Exception("All OCR providers failed: " + " | ".join(errors))

    # Strip markdown code fences if model returned them
    raw_json = re.sub(r"^```[a-z]*\n?", "", raw_json.strip(), flags=re.IGNORECASE)
    raw_json = re.sub(r"```$", "", raw_json.strip())

    try:
        parsed = json.loads(raw_json)
    except Exception:
        print(f"[OCR ERROR] Failed to parse JSON: {raw_json}")
        parsed = {}

    return {
        "merchant": parsed.get("merchant"),
        "date": parsed.get("date") or datetime.utcnow().strftime("%Y-%m-%d"),
        "total": parsed.get("total"),
        "currency": parsed.get("currency") or "EGP",
        "raw_text": parsed.get("raw_text") or "No text extracted.",
    }
