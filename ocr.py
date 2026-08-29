"""
Handles turning a receipt photo into structured data:
  1. download the image bytes from Telegram
  2. run Tesseract OCR to get raw text
  3. run light heuristics to pull out merchant / date / total / currency
This is intentionally simple and free (no paid vision API). Accuracy on
messy or crumpled receipts will be imperfect -- that's the tradeoff for
$0 cost. See README.md for how to swap in a paid OCR/LLM step later if
you ever want higher accuracy.
"""
import io
import re
from datetime import datetime

import pytesseract
import requests
from dateutil import parser as dateparser
from PIL import Image, ImageOps

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

TOTAL_KEYWORDS_PRIORITY = [
    "grand total",
    "total due",
    "amount due",
    "balance due",
    "total amount",
    "total",
    "amount",
    "الإجمالي",
    "الاجمالي",
    "الإجمالى",
    "الاجمالى",
    "المجموع",
    "الصافي",
    "المطلوب",
    "اجمالي",
]

DATE_LINE_RE = re.compile(
    r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2}"
    r"|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4})"
)

NUMBER_RE = re.compile(r"(\d{1,3}(?:[,.]\d{3})*(?:[.,]\d{1,2})?)")
# Stricter pattern for the "no keyword found" fallback: real prices are
# printed with exactly 2 decimal places. Barcodes, phone numbers, and
# product codes are long digit runs with no decimal point, so requiring
# one here stops those from being mistaken for a total.
AMOUNT_RE = re.compile(r"\b(\d{1,6}[.,]\d{2})\b")

CURRENCY_SYMBOLS = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "EGP": "EGP",
    "LE": "EGP",
    "ج.م": "EGP",
    "SAR": "SAR",
    "AED": "AED",
}


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


MAX_DIMENSION = 1400  # cap image size: Render's free tier has only 512MB RAM,
# and Tesseract's memory use grows fast with image size — this keeps it safe.


def extract_text(image_bytes: bytes) -> str:
    """Run Tesseract OCR on the image bytes and return raw text."""
    image = Image.open(io.BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image)

    # Phone photos are often 3000px+ wide / several MB — that's overkill for
    # OCR and risks exhausting RAM on a free-tier instance. Downscale first.
    if max(image.size) > MAX_DIMENSION:
        image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)

    # Basic preprocessing: grayscale + auto-contrast noticeably helps
    # Tesseract on photographed (not scanned) receipts.
    image = image.convert("L")
    image = ImageOps.autocontrast(image)
    # ara+eng: receipts here are often bilingual (Arabic merchant/item
    # names, various numeral styles for prices). --psm 6 assumes a block
    # of text laid out in lines, which fits most receipt layouts better
    # than Tesseract's default "auto-detect page layout" mode.
    return pytesseract.image_to_string(image, lang="ara+eng", config="--psm 6")


def _parse_amount(raw: str):
    raw = raw.replace(",", "")
    try:
        return round(float(raw), 2)
    except ValueError:
        return None


ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _find_total(lines):
    lines = [l.translate(ARABIC_INDIC_DIGITS) for l in lines]
    lowered = [l.lower() for l in lines]
    for keyword in TOTAL_KEYWORDS_PRIORITY:
        for line, low in zip(lines, lowered):
            if keyword in low:
                # Prefer a properly-formatted amount (X.XX); only fall
                # back to a bare number if that's all the line has.
                nums = AMOUNT_RE.findall(line) or NUMBER_RE.findall(line)
                if nums:
                    amt = _parse_amount(nums[-1])
                    if amt is not None:
                        return amt
    # Fallback: largest properly-formatted amount (X.XX) anywhere in the
    # text. Deliberately does NOT fall back to bare integers — those are
    # too easily a misread barcode, phone number, or product code.
    all_nums = []
    for line in lines:
        for n in AMOUNT_RE.findall(line):
            amt = _parse_amount(n)
            if amt is not None:
                all_nums.append(amt)
    return max(all_nums) if all_nums else None


def _find_date(text: str):
    match = DATE_LINE_RE.search(text)
    if not match:
        return None
    try:
        dt = dateparser.parse(match.group(1), dayfirst=True, fuzzy=True)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        return None


def _find_currency(text: str):
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    return None


def _find_merchant(lines):
    # Heuristic: the merchant name is usually one of the first few
    # non-empty lines, and isn't itself a date or a pure number.
    for line in lines[:5]:
        stripped = line.strip()
        if len(stripped) < 3:
            continue
        if DATE_LINE_RE.search(stripped):
            continue
        if NUMBER_RE.fullmatch(stripped):
            continue
        return stripped
    return None


def parse_receipt(text: str) -> dict:
    lines = [l for l in text.splitlines() if l.strip()]
    return {
        "merchant": _find_merchant(lines),
        "date": _find_date(text) or datetime.utcnow().strftime("%Y-%m-%d"),
        "total": _find_total(lines),
        "currency": _find_currency(text) or "EGP",
        "raw_text": text.strip(),
    }
