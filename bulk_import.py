import os
import shutil
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from ocr import parse_receipt
from sheets_client import append_expense

INPUT_DIR = 'bulk_photos'
PROCESSED_DIR = 'bulk_photos/processed'

def main():
    if not os.environ.get('GEMINI_API_KEY'):
        print('❌ Error: GEMINI_API_KEY is not set. Please add it to your .env file.')
        return

    if not os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON'):
        print('❌ Error: GOOGLE_SERVICE_ACCOUNT_JSON is not set in .env.')
        return

    Path(INPUT_DIR).mkdir(exist_ok=True)
    Path(PROCESSED_DIR).mkdir(exist_ok=True)

    valid_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
    
    files_to_process = []
    for f in os.listdir(INPUT_DIR):
        file_path = os.path.join(INPUT_DIR, f)
        if os.path.isfile(file_path) and Path(file_path).suffix.lower() in valid_extensions:
            files_to_process.append(file_path)

    if not files_to_process:
        print(f'[Empty] No images found in {INPUT_DIR}/. Place your photos there and run again.')
        return

    print(f'[Start] Found {len(files_to_process)} photos to process. Starting bulk import...\n')

    success_count = 0
    for idx, file_path in enumerate(files_to_process, 1):
        filename = os.path.basename(file_path)
        print(f'[{idx}/{len(files_to_process)}] Processing {filename}...')
        
        try:
            with open(file_path, 'rb') as f:
                image_bytes = f.read()

            parsed = parse_receipt(image_bytes)
            append_expense('Bulk Import', parsed)
            shutil.move(file_path, os.path.join(PROCESSED_DIR, filename))
            
            total = parsed.get('total')
            merchant = parsed.get('merchant') or 'Unknown'
            print(f'   [OK] Logged: {merchant} | Total: {total}')
            success_count += 1
            
        except Exception as e:
            print(f'   [ERROR] Failed to process {filename}: {e}')
            
        # Rate limit protection for Gemini Free Tier (15 requests / minute)
        time.sleep(4.5)

    print(f'\n[Done] Bulk import complete! Successfully logged {success_count}/{len(files_to_process)} receipts.')

if __name__ == '__main__':
    main()
