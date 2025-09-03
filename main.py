# main.py
from __future__ import annotations
import os, sys, json, pathlib, argparse, traceback
import pandas as pd
from typing import List, Dict

from src.adapters.regula_client import recognize_images
from src.adapters.regula_mapper import regula_to_universal
from src.utils import postprocess, ResultsAgent  # copied from your LLM_passport_info repo

# ======== CONFIG DEFAULTS (change as needed) ========
IMAGE_PATH = "data/Philippines"  # <root>/MaidID/*.{jpg,png,...}
DATASET_COUNTRY = IMAGE_PATH.split("/")[-1]
SPREADSHEET_ID = "1ljIem8te0tTKrN8N9jOOnPIRh2zMvv2WB_3FBa4ycgA"
CREDENTIALS_PATH = "credentials.json"
RESULTS_CSV = f"results/regula_{DATASET_COUNTRY}_results.csv"
# ====================================================

VALID_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

def _list_image_files(folder: str) -> List[str]:
    paths = []
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        if os.path.isfile(p) and pathlib.Path(p).suffix.lower() in VALID_EXTS:
            paths.append(p)
    return paths

def _merge_universal(records: List[Dict[str, str]]) -> Dict[str, str]:
    """
    Merge multiple 'universal' dicts (front/back pages) into one row.
    Rule: first non-empty wins; for MRZ lines pick the longest.
    """
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
    """
    Map Regula response -> universal. Try top-level first, then fill from list items.
    """
    base = regula_to_universal(raw)
    items = raw.get("list", []) or []
    if items:
        merged = _merge_universal([base] + [regula_to_universal(it) for it in items])
        return merged
    return base

def run(image_root: str, dataset_country: str, spreadsheet_id: str, credentials_path: str, results_csv: str):
    rows = []
    skipped = []
    processed = 0

    # Walk one level: each subfolder is a Maid ID
    for entry in sorted(os.scandir(image_root), key=lambda e: e.name)[:1]:
        if not entry.is_dir():
            continue
        maid_id = entry.name
        folder = entry.path
        images = _list_image_files(folder)

        if not images:
            skipped.append((maid_id, "no images"))
            continue

        try:
            # 1) Regula call with all images in this Maid's folder
            raw = recognize_images(images)
            with open(f"results/test/{maid_id}.json", "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)

            uni = _collect_universal_from_raw(raw)
    
            uni = postprocess(uni)

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
            }
            rows.append(row)
            processed += 1

        except Exception as e:
            skipped.append((maid_id, f"error: {e}"))
            # Optional: write raw payload for debugging
            with open(f"results/debug_{maid_id}.json", "w", encoding="utf-8") as f:
                json.dump(raw if isinstance(raw, dict) else {"error": str(e)}, f, ensure_ascii=False, indent=2)

    # 4) Save CSV
    os.makedirs(os.path.dirname(results_csv), exist_ok=True)
    pd.DataFrame(rows).to_csv(results_csv, index=False)
    print(f"✅ Saved {len(rows)} rows to {results_csv} (processed={processed}, skipped={len(skipped)})")
    if skipped:
        for mid, reason in skipped:
            print(f"  - skipped {mid}: {reason}")

    # 5) Upload to Google Sheet via your existing agent
    ResultsAgent(
        spreadsheet_id=SPREADSHEET_ID,
        credentials_path=CREDENTIALS_PATH,
        country=DATASET_COUNTRY,
    ).upload_results(results_csv)
    print("✅ Uploaded to Google Sheet")

if __name__ == "__main__":
    run(IMAGE_PATH, DATASET_COUNTRY, SPREADSHEET_ID, CREDENTIALS_PATH, RESULTS_CSV)