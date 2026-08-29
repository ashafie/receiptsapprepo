import os
import traceback

import requests
from flask import Flask, request, jsonify

from ocr import download_telegram_file, parse_receipt
from sheets_client import append_expense

app = Flask(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
# Optional: comma-separated Telegram numeric user IDs allowed to use the
# bot (your family). Leave unset during testing; set it before sharing
# the bot's username with anyone, so strangers can't log fake expenses.
ALLOWED_USER_IDS = {
    uid.strip() for uid in os.environ.get("ALLOWED_USER_IDS", "").split(",") if uid.strip()
}

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def send_message(chat_id, text):
    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=15,
    )


def format_reply(parsed: dict) -> str:
    total = parsed.get("total")
    total_str = f"{total:.2f}" if total is not None else "not found — check manually"
    lines = [
        "🧾 Receipt logged:",
        f"Merchant: {parsed.get('merchant') or 'not found'}",
        f"Date: {parsed.get('date') or 'not found'}",
        f"Total: {total_str} {parsed.get('currency') or ''}".strip(),
        "",
        "Saved to the shared expenses sheet ✅",
    ]
    # When extraction is weak, show a snippet of the raw OCR text so it's
    # easy to see whether the photo itself read poorly (blur/glare/angle)
    # or the parsing logic just missed it.
    if parsed.get("merchant") is None or total is None:
        snippet = (parsed.get("raw_text") or "").strip().replace("\n", " ")[:200]
        if snippet:
            lines.append("")
            lines.append(f"(raw OCR text: {snippet}…)")
        else:
            lines.append("")
            lines.append("(OCR read no text at all — try a clearer, well-lit photo)")
    return "\n".join(lines)


@app.route("/", methods=["GET"])
def health():
    return "ok"

@app.route("/cron/dedupe", methods=["GET"])
def cron_dedupe():
    try:
        from sheets_client import deduplicate_sheet
        removed = deduplicate_sheet()
        return jsonify({"ok": True, "removed": removed})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/webhook/<secret>", methods=["POST"])
def webhook(secret):
    if secret != WEBHOOK_SECRET:
        return jsonify({"error": "forbidden"}), 403

    update = request.get_json(force=True, silent=True) or {}
    message = update.get("message") or update.get("edited_message")
    if not message:
        return jsonify({"ok": True})

    chat_id = message["chat"]["id"]
    sender = message.get("from", {})
    sender_id = str(sender.get("id", ""))
    sender_name = sender.get("first_name") or sender.get("username") or "Unknown"

    if ALLOWED_USER_IDS and sender_id not in ALLOWED_USER_IDS:
        send_message(chat_id, "Sorry, this bot is private to a specific family group.")
        return jsonify({"ok": True})

    if "photo" in message:
        try:
            # Telegram sends multiple resolutions; the last is the largest.
            file_id = message["photo"][-1]["file_id"]
            image_bytes = download_telegram_file(BOT_TOKEN, file_id)
            parsed = parse_receipt(image_bytes)
            print(f"[OCR] sender={sender_name} parsed={parsed}", flush=True)
            append_expense(sender_name, parsed)
            send_message(chat_id, format_reply(parsed))
        except Exception:
            traceback.print_exc()
            send_message(
                chat_id,
                "Sorry, I couldn't process that receipt. Please try a clearer photo.",
            )
        return jsonify({"ok": True})

    if "document" in message:
        doc = message["document"]
        try:
            file_id = doc["file_id"]
            file_bytes = download_telegram_file(BOT_TOKEN, file_id)
            text_content = file_bytes.decode('utf-8', errors='ignore')
            
            send_message(chat_id, f"📄 Received document. Extracting transactions via Gemini, please wait...")
            from sms_parser import parse_sms_bulk
            transactions = parse_sms_bulk(text_content)
            
            if not transactions:
                send_message(chat_id, "⚠️ Could not extract any valid transactions from the file.")
            else:
                for tx in transactions:
                    append_expense(sender_name + " (SMS Bulk)", tx)
                send_message(chat_id, f"✅ Successfully extracted and logged {len(transactions)} transactions to the Google Sheet!")
        except Exception as e:
            traceback.print_exc()
            send_message(chat_id, f"❌ Failed to process document: {str(e)}")
        return jsonify({"ok": True})

    text_body = message.get("text", "")
    if text_body.startswith("/analyze"):
        query = text_body[len("/analyze"):].strip()
        send_message(chat_id, "📊 Analyzing your expenses, please wait...")
        try:
            from analytics import perform_analysis
            result_text = perform_analysis(query)
            send_message(chat_id, result_text)
        except Exception as e:
            traceback.print_exc()
            send_message(chat_id, f"❌ Failed to analyze: {str(e)}")
            
    elif text_body.startswith("/start") or text_body.startswith("/help"):
        send_message(
            chat_id,
            "Send me a photo of a receipt and I'll extract the merchant, date, "
            "and total, then log it to the family expenses sheet.\n\n"
            "You can also use `/analyze` to get spending insights, or send a .txt file with bank SMS messages for bulk import!"
        )

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
