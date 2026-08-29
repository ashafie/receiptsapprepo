# Handoff: Family Receipt Bot

Paste this whole file as your first message to Antigravity, along with the
project zip, to get it up to speed instantly.

## What this is

A Telegram bot: family members send it a photo of a receipt, it OCRs the
text (free, local Tesseract — no paid vision API), extracts merchant/
date/total/currency with regex heuristics, replies in chat with what it
found, and logs a row to a shared Google Sheet.

Stack (all free tier): Python/Flask app → Docker → Render (free web
service, webhook-driven, not polling) → Tesseract OCR (local, incl.
Arabic language pack) → Google Sheets API (service account).

## Current live deployment

- GitHub repo: **[fill in your repo URL]**
- Render service: **[fill in — e.g. https://receiptsapprepo.onrender.com]**
- Render env vars already set: `TELEGRAM_BOT_TOKEN`, `WEBHOOK_SECRET`,
  `GOOGLE_SERVICE_ACCOUNT_JSON`, `SHEET_ID`, `ALLOWED_USER_IDS` (see
  `.env.example` in the zip for what each is).
- Telegram webhook is already registered pointing at
  `https://<render-url>/webhook/<WEBHOOK_SECRET>`.

## ⚠️ Known issue to fix first — Arabic OCR not actually active yet

The code in this zip installs and uses Tesseract's Arabic language pack
(`tesseract-ocr-ara`, `lang="ara+eng"` in `ocr.py`). But the **live Render
deployment was still running the old English-only Dockerfile** as of the
last test — a real Arabic pharmacy receipt came back with garbled
Latin-lookalike text (e.g. `"las laal,a Cilltna"`) instead of actual
Arabic characters, which is the signature of Tesseract guessing Latin
shapes for Arabic letters it has no model for.

**First task**: push this zip's contents to the GitHub repo (replacing
what's there), then on Render do **Manual Deploy → Clear build cache &
deploy** (not a normal deploy — Docker layer caching can silently skip
re-running the `apt-get install tesseract-ocr-ara` line otherwise).
Then send a test Arabic receipt through and confirm the raw-OCR-text
snippet in the bot's reply contains real Arabic characters.

## What's already confirmed working (don't regress these)

- Total extraction: correct on both a short pharmacy receipt (754.00 EGP)
  and closer on a long 20-item supermarket receipt after a fix — was
  previously grabbing barcode fragments as fake totals (e.g. read
  `23900.00` off a receipt whose real total was `3646.19`). Fixed by
  requiring an actual `X.XX` decimal format for any fallback-matched
  amount (see `AMOUNT_RE` vs `NUMBER_RE` in `ocr.py`) — barcodes/phone
  numbers/product codes are long digit runs with no decimal point, so
  this filters them out.
- Date extraction: correct on the pharmacy receipt (23/02/2026) once a
  clean keyword-adjacent date was present.
- Memory: Render free tier is 512MB RAM. Tesseract on a full-size phone
  photo previously caused a `SIGKILL... out of memory` crash with zero
  reply to the user. Fixed via: resizing images to max 1400px before OCR
  (`MAX_DIMENSION` in `ocr.py`), and `ENV OMP_THREAD_LIMIT=1` in the
  Dockerfile (stops Tesseract multithreading from multiplying memory
  use). Worth stress-testing with a few more large photos to confirm
  this holds.

## Known remaining weak point — merchant name

Even with Arabic OCR working, merchant-name extraction is a simple
heuristic (`_find_merchant` in `ocr.py`): "first non-empty line that
isn't a date or a bare number." This is unreliable because Egyptian
receipts often lead with a slogan/tagline (e.g. "نخدمكم بحب" — "we serve
you with love") before the actual store name. This has NOT been fixed
yet and is a good next task — options discussed but not built:
- Try to detect and skip common tagline patterns (fragile, receipt-specific).
- Look for a line containing a known business-suffix word.
- Accept it as a rule-based ceiling and lean on the raw-OCR-text snippet
  already included in the bot's reply so the user can read it off
  themselves in a couple of seconds.
- The "real" fix discussed with the user: swap free Tesseract for a
  vision-capable LLM call (e.g. Claude with an image). Far more
  accurate on mixed Arabic/Latin receipts, but no longer free — this
  was explicitly flagged to the user as a tradeoff, not decided yet.

## Design constraints to preserve

- **Cost must stay $0** unless the user explicitly agrees to change that
  — this was the core requirement from the start. Don't introduce a
  paid API without flagging it clearly first.
- Runs on Render's free tier: 512MB RAM, spins down after ~15 min
  idle. The app is intentionally webhook-based (not polling) so Telegram
  just retries until it wakes up — don't switch to polling.
- OCR is local/free (Tesseract), not a cloud vision API — same reasoning.
- Data lives in a Google Sheet the family can view directly, via a free
  service-account, not a database.

## Files in this zip

- `app.py` — Flask webhook handler, formats the reply message
- `ocr.py` — image download, Tesseract OCR call, all the parsing heuristics
- `sheets_client.py` — Google Sheets logging via service account
- `Dockerfile` — installs Tesseract + Arabic language pack
- `requirements.txt`, `.env.example`, `README.md` (full original setup
  instructions, still accurate for env vars / architecture — just skip
  its deploy steps since that's already done)
