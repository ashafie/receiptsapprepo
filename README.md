# Family Receipt Bot

A Telegram bot that receives receipt photos from you and your family,
extracts the merchant/date/total with free local OCR (Tesseract), replies
with what it found, and logs every receipt as a row in a shared Google
Sheet. Every piece of this stack has a $0 tier at family-sized volumes.

## How it works

```
You/family -> Telegram photo -> Bot webhook (Render, free) -> Tesseract OCR
                                                              -> Google Sheet
                                                              -> reply in chat
```

The bot runs as a **webhook**, not constant polling. Render's free tier
puts the app to sleep after ~15 minutes of no traffic, but Telegram simply
retries the webhook request until the app wakes up — so the first receipt
after a quiet period might take 20–40 seconds to get a reply, and every
one after that is fast. No paid "keep-alive" tricks needed.

## What you'll set up (all free)

1. A Telegram bot (via @BotFather) — free, no limits.
2. A Google Sheet + a free Google Cloud service account to write to it.
3. This code deployed on Render's free web service tier.

---

## 1. Create the Telegram bot

1. In Telegram, message **@BotFather** → `/newbot` → follow the prompts.
2. Save the **bot token** it gives you (looks like `123456:AA...`).
3. Add the bot to a family group chat, or just talk to it 1:1 — both work.
4. Optional but recommended once it's working: message **@userinfobot**
   from each family member's account to get their numeric user ID, so you
   can restrict the bot to just your family (`ALLOWED_USER_IDS`).

## 2. Set up the Google Sheet

1. Create a new Google Sheet (sheets.new). Name it whatever you like.
2. Copy the **Sheet ID** from its URL:
   `https://docs.google.com/spreadsheets/d/`**`THIS_PART`**`/edit`
3. Go to [Google Cloud Console](https://console.cloud.google.com/) →
   create a new project (free) → enable the **Google Sheets API**.
4. Create a **Service Account** (IAM & Admin → Service Accounts) → create
   a **JSON key** for it and download it.
5. Open the downloaded JSON — copy the `client_email` value.
6. Back in your Google Sheet, click **Share** and give that email
   **Editor** access.
7. Keep the JSON file handy — its full contents go into an environment
   variable in the next step.

## 3. Deploy on Render (free tier)

1. Push this folder to a new **GitHub repository** (Render deploys from
   git). If you're not sure how, GitHub's "upload files" web UI works
   fine for a small project like this.
2. Go to [render.com](https://render.com) → sign up free → **New +** →
   **Web Service** → connect your GitHub repo.
3. Render will detect the `Dockerfile` automatically — leave the default
   build settings.
4. Choose the **Free** instance type.
5. Under **Environment**, add these variables (see `.env.example`):
   - `TELEGRAM_BOT_TOKEN`
   - `WEBHOOK_SECRET` (make up any long random string)
   - `GOOGLE_SERVICE_ACCOUNT_JSON` (paste the *entire* JSON key file
     contents as one value)
   - `SHEET_ID`
   - `ALLOWED_USER_IDS` (optional, add once you've collected family IDs)
6. Click **Deploy**. First build takes a few minutes (it's installing
   Tesseract). Once live, copy your app's URL, e.g.
   `https://family-receipt-bot.onrender.com`.

## 4. Point Telegram at your deployed bot

Run this once (replace the placeholders), from any terminal, or by
pasting the URL into a browser:

```
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<YOUR_RENDER_URL>/webhook/<WEBHOOK_SECRET>
```

You should get back `{"ok":true,"result":true,...}`. That's it — send
the bot a photo of a receipt and watch the row appear in your sheet.

## Notes & limitations (worth knowing since this is a $0 setup)

- **OCR accuracy**: Tesseract is free but not as accurate as paid vision
  APIs, especially on crumpled, faded, or handwritten receipts. Expect
  to occasionally correct a total by hand in the sheet.
- **Cold starts**: the first message after ~15 idle minutes is slow
  (Render free tier sleeping). Everything after that is fast until it
  goes idle again.
- **Google Sheets API** free quota (60 write requests/min per user) is
  far beyond what a family will ever hit.
- **Privacy**: set `ALLOWED_USER_IDS` before sharing the bot outside
  your family — otherwise anyone who finds it can log entries.

## Possible upgrades later (not free)

- Swap Tesseract for a paid OCR/vision API (e.g. Claude's vision, Google
  Cloud Vision beyond free quota) for much higher accuracy on messy
  receipts.
- Add spending categories, monthly summaries, or a `/fix` command to
  correct the last entry from chat.
