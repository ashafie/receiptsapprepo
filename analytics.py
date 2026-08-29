import os
import time
import re
import pandas as pd
from sheets_client import _get_sheet

# Fallback chain for text analysis (no vision needed here)
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-1.5-flash",
]
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"


def _parse_retry_delay(error_str: str, default: int = 5) -> int:
    try:
        match = re.search(r"retry.*?(\d+)s", error_str, re.IGNORECASE)
        if match:
            return min(int(match.group(1)), 15)
    except Exception:
        pass
    return default


def _try_gemini_text(prompt_parts: list) -> str:
    from google import genai
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")
    client = genai.Client(api_key=api_key)
    for model in GEMINI_MODELS:
        try:
            print(f"[Analytics] Trying Gemini: {model}")
            resp = client.models.generate_content(model=model, contents=prompt_parts)
            print(f"[Analytics] Gemini success: {model}")
            return resp.text
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                delay = _parse_retry_delay(err)
                print(f"[Analytics] Gemini {model} quota hit. Waiting {delay}s...")
                time.sleep(delay)
            else:
                raise
    raise Exception("All Gemini models quota exhausted")


def _try_groq_text(prompt: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set")
    from groq import Groq
    print(f"[Analytics] Trying Groq: {GROQ_TEXT_MODEL}")
    client = Groq(api_key=api_key)
    resp = client.chat.completions.create(
        model=GROQ_TEXT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1024,
    )
    print("[Analytics] Groq success")
    return resp.choices[0].message.content


def perform_analysis(query: str) -> str:
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

    if not query:
        analysis_request = (
            "You are a financial advisor. Here is family expense data in CSV format:\n\n"
            f"{csv_data}\n\n"
            "Provide a brief spending summary including:\n"
            "- Total amount spent\n"
            "- Top 3 merchants by spending\n"
            "- A quick insight or trend.\n"
            "Keep it concise and readable for a Telegram message."
        )
    else:
        analysis_request = (
            "You are a financial advisor. Here is family expense data in CSV format:\n\n"
            f"{csv_data}\n\n"
            f"Please answer this question: {query}\n"
            "Keep your answer concise and readable for a Telegram message."
        )

    errors = []

    # 1. Try Gemini
    try:
        return _try_gemini_text([analysis_request])
    except Exception as e:
        errors.append(f"Gemini: {e}")
        print(f"[Analytics] Gemini failed: {e}")

    # 2. Fall back to Groq
    try:
        return _try_groq_text(analysis_request)
    except Exception as e:
        errors.append(f"Groq: {e}")
        print(f"[Analytics] Groq failed: {e}")

    return "[Error] All AI providers failed: " + " | ".join(errors)
