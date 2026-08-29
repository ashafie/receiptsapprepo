FROM python:3.11-slim

# Tesseract is the free, local OCR engine we use to read receipt text.
# Includes the Arabic language pack alongside English, since receipts are
# often bilingual (Arabic merchant/item names, Latin-script or Arabic-Indic
# numerals for prices).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-ara libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Tesseract can multithread internally, which multiplies memory use — not
# worth it on a 512MB free-tier instance, and receipts are single images
# processed one at a time anyway.
ENV OMP_THREAD_LIMIT=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=10000
EXPOSE 10000

# Render (and most free PaaS platforms) inject $PORT; gunicorn binds to it.
CMD gunicorn -b 0.0.0.0:${PORT:-10000} app:app
