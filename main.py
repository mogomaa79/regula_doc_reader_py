# main.py
from __future__ import annotations
import os, json, pathlib
import pandas as pd
import time
from typing import List, Dict

from src.adapters.regula_client import recognize_images
from src.adapters.regula_mapper import regula_to_universal
from src.utils import postprocess, ResultsAgent 

from dotenv import load_dotenv
load_dotenv()

IMAGE_PATH = os.getenv("IMAGE_PATH")
DATASET_COUNTRY = IMAGE_PATH.split("/")[-1]
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CREDENTIALS_PATH = os.getenv("CREDENTIALS_PATH")
RESULTS_CSV = f"results/regula_{DATASET_COUNTRY}_results.csv"

API_DELAY = float(os.getenv("REGULA_API_DELAY", "0.3")) 

VALID_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

def _list_image_files(folder: str) -> List[str]:
    paths = []
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        if os.path.isfile(p) and pathlib.Path(p).suffix.lower() in VALID_EXTS:
            paths.append(p)
    return paths

def _merge_universal(records: List[Dict[str, str]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    keys = set().union(*[r.keys() for r in records]) if records else set()
    for k in keys:
        vals = [str((r.get(k) or "")).strip() for r in records]
        # special-case MRZ lines: prefer the longest line
        if k in ("mrzLine1", "mrzLine2"):
            out[k] = max(vals, key=lambda s: len(s)) if any(vals) else ""
        else:
            # first non-empty value
            out[k] = next((v for v in vals if v), "")
    return out

def _collect_universal_from_raw(raw: Dict) -> Dict[str, str]:
    base = regula_to_universal(raw)
    items = raw.get("list", []) or []
    if items:
        merged = _merge_universal([base] + [regula_to_universal(it) for it in items])
        return merged
    return base

def run(image_root: str, dataset_country: str, spreadsheet_id: str, credentials_path: str, results_csv: str, delay_between_calls: float = 6.0):
    rows = []
    skipped = []
    processed = 0
    current_delay = delay_between_calls
    consecutive_successes = 0
    
    # Load existing results for resumption
    existing_ids = set()
    if os.path.exists(results_csv):
        try:
            existing_df = pd.read_csv(results_csv)
            existing_ids = set(existing_df["inputs.image_id"].astype(str))
            print(f"Found {len(existing_ids)} existing records, will resume processing...")
        except Exception as e:
            print(f"Could not load existing results: {e}")
            existing_ids = set()

    for entry in sorted(os.scandir(image_root), key=lambda e: e.name):
        if not entry.is_dir():
            continue
        maid_id = entry.name
        folder = entry.path
        
        # Skip if already processed
        if maid_id in existing_ids:
            continue
            
        images = _list_image_files(folder)

        if not images:
            skipped.append((maid_id, "no images"))
            continue

        try:
            print(f"Processing {maid_id} ({processed + 1}) - {len(images)} image(s)... (delay: {current_delay:.1f}s)")
            
            # 1) Regula call with all images in this Maid's folder
            raw = recognize_images(images)
            with open(f"results/test/{maid_id}.json", "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)

            uni = _collect_universal_from_raw(raw)
    
            uni = postprocess(uni)

            # Extract probabilities for each field from Regula
            probs = uni.get("probabilities", {})
            
            row = {
                "inputs.image_id": maid_id,  # key used for merging in your sheet
                "outputs.number": uni.get("number", ""),
                "outputs.country": uni.get("country", ""),
                "outputs.name": uni.get("name", ""),
                "outputs.surname": uni.get("surname", ""),
                "outputs.middle name": uni.get("middle name", ""),
                "outputs.gender": uni.get("gender", ""),
                "outputs.place of birth": uni.get("place of birth", ""),
                "outputs.birth date": uni.get("birth date", ""),
                "outputs.issue date": uni.get("issue date", ""),
                "outputs.expiry date": uni.get("expiry date", ""),
                "outputs.mother name": uni.get("mother name", ""),
                "outputs.father name": uni.get("father name", ""),
                "outputs.spouse name": uni.get("spouse name", ""),
                "outputs.place of issue": uni.get("place of issue", ""),
                "outputs.country of issue": uni.get("country of issue", ""),
                "outputs.mrzLine1": uni.get("mrzLine1", ""),
                "outputs.mrzLine2": uni.get("mrzLine2", ""),
                "outputs.original number": uni.get("number", ""),
                # Add Regula probability scores for each field
                "probability.number": probs.get("number", 0.0),
                "probability.country": probs.get("country", 0.0),
                "probability.name": probs.get("name", 0.0),
                "probability.surname": probs.get("surname", 0.0),
                "probability.middle name": probs.get("middle name", 0.0),
                "probability.gender": probs.get("gender", 0.0),
                "probability.place of birth": probs.get("place of birth", 0.0),
                "probability.birth date": probs.get("birth date", 0.0),
                "probability.issue date": probs.get("issue date", 0.0),
                "probability.expiry date": probs.get("expiry date", 0.0),
                "probability.mother name": probs.get("mother name", 0.0),
                "probability.father name": probs.get("father name", 0.0),
                "probability.spouse name": probs.get("spouse name", 0.0),
                "probability.place of issue": probs.get("place of issue", 0.0),
                "probability.country of issue": probs.get("country of issue", 0.0),
                "probability.mrzLine1": probs.get("mrzLine1", 0.0),
                "probability.mrzLine2": probs.get("mrzLine2", 0.0),
            }
            rows.append(row)
            processed += 1
            
            # For per-minute rate limits, don't reduce delay below 6 seconds
            consecutive_successes += 1
            if consecutive_successes >= 5 and current_delay > 6.0:
                current_delay = max(6.0, current_delay * 0.9)  # Reduce delay by 10% but never below 6s
                consecutive_successes = 0
                print(f"  → Reduced delay to {current_delay:.1f}s after consecutive successes")
            
            # Rate limiting: wait between API calls to avoid overwhelming the server
            if current_delay > 0:
                time.sleep(current_delay)

        except Exception as e:
            error_msg = str(e).lower()
            is_rate_limit = any(keyword in error_msg for keyword in [
                'rate limit', 'too many requests', '429', 'quota', 'throttle', 'ratelimit_exceeded'
            ])
            
            if is_rate_limit:
                # For per-minute rate limits, wait a full minute then reset to normal delay
                print(f"  → Rate limit hit, cooling down for 60 seconds...")
                time.sleep(60)  # Wait full minute for rate limit reset
                current_delay = delay_between_calls  # Reset to original delay
                consecutive_successes = 0
                print(f"  → Cooldown complete, resumed with {current_delay:.1f}s delay")
            
            print(f"Error: {e} in {maid_id}")
            # Optional: write raw payload for debugging
            with open(f"results/test/debug_{maid_id}.json", "w", encoding="utf-8") as f:
                json.dump(raw if 'raw' in locals() and isinstance(raw, dict) else {"error": str(e)}, f, ensure_ascii=False, indent=2)

    # 4) Save CSV (append to existing if resuming)
    os.makedirs(os.path.dirname(results_csv), exist_ok=True)
    if rows:
        if existing_ids:
            # Append new results to existing file
            pd.DataFrame(rows).to_csv(results_csv, mode='a', header=False, index=False)
            total_records = len(existing_ids) + len(rows)
            print(f"✅ Appended {len(rows)} new rows to {results_csv} (total={total_records}, processed={processed}, skipped={len(skipped)})")
        else:
            # Create new file
            pd.DataFrame(rows).to_csv(results_csv, index=False)
            print(f"✅ Saved {len(rows)} rows to {results_csv} (processed={processed}, skipped={len(skipped)})")
    else:
        print(f"ℹ️  No new records to process (total existing={len(existing_ids)}, skipped={len(skipped)})")

    # 5) Upload to Google Sheet via your existing agent
    ResultsAgent(
        spreadsheet_id=SPREADSHEET_ID,
        credentials_path=CREDENTIALS_PATH,
        country=DATASET_COUNTRY,
    ).upload_results(results_csv)
    print("✅ Uploaded to Google Sheet")

if __name__ == "__main__":
    print(f"Starting processing with {API_DELAY}s delay (optimized for per-minute rate limits)...")
    print(f"To change delay, set REGULA_API_DELAY environment variable (e.g., REGULA_API_DELAY=8.0)")
    run(IMAGE_PATH, DATASET_COUNTRY, SPREADSHEET_ID, CREDENTIALS_PATH, RESULTS_CSV, API_DELAY)