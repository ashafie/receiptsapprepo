import os
import json
from google import genai
from google.genai import types

def parse_sms_bulk(text_content: str) -> list:
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    if not GEMINI_API_KEY:
        raise ValueError('GEMINI_API_KEY is not set.')

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = (
        'You are an expert financial parser. I am providing you with a raw text dump of bank SMS messages or bank statements. '
        'Extract every single expense/transaction you can find.\n'
        'Return the data STRICTLY as a JSON array of objects, where each object has these exact keys:\n'
        '- "merchant": The name of the store or business (clean it up, remove raw SMS noise like "POS PUR").\n'
        '- "date": The date of the transaction in YYYY-MM-DD format.\n'
        '- "total": The amount as a float (e.g. 150.00).\n'
        '- "currency": The currency code (e.g. "EGP", "USD"). Default to "EGP" if not stated.\n'
        '- "raw_text": A brief 1-sentence summary of the transaction from the SMS.\n\n'
        'Return ONLY the JSON array (e.g. [{"merchant": "...", ...}, ...]) with no markdown blocks or extra text.'
    )

    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=[text_content, prompt],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            )
        )
        data = json.loads(response.text)
        if isinstance(data, dict) and "transactions" in data:
            return data["transactions"]
        elif isinstance(data, list):
            return data
        else:
            return []
    except Exception as e:
        print(f"Failed to parse SMS bulk: {e}")
        return []
