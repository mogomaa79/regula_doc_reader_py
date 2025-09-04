# src/adapters/regula_client.py
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any
import time
import random

# 👉 Use the new package name
from regula.documentreader.webclient import (
    DocumentReaderApi,
    ProcessParams,
    Scenario,
    Result,
    RecognitionRequest,
)

DOCREADER_URL = "http://localhost:8080"
DATE_FORMAT = "dd/MM/yyyy"   # Regula expects capital MM for month


def recognize_images(
    image_paths: List[str],
    scenario: Scenario = Scenario.FULL_PROCESS,
    max_retries: int = 5,
    adaptive_delay: bool = True,
) -> Dict[str, Any]:
    images = [Path(p).expanduser().read_bytes() for p in image_paths]

    for attempt in range(max_retries + 1):
        try:
            with DocumentReaderApi(host=DOCREADER_URL) as api:
                params = ProcessParams(
                    scenario=scenario,
                    result_type_output=[Result.STATUS, Result.TEXT, Result.AUTHENTICITY],
                    date_format=DATE_FORMAT,
                    check_auth=True,
                    auth_params={"checkExtMRZ": True},
                    # Optional leniency for text field masks / requirements:
                    # match_text_field_mask=False,
                    # check_required_text_fields=False,
                )
                req = RecognitionRequest(process_params=params, images=images)
                resp = api.process(req)

                # Turn the SDK model into a plain dict you can JSON-dump
                return api.api_client.sanitize_for_serialization(resp)

        except Exception as e:
            emsg = str(e).lower()
            is_rate_limit = any(s in emsg for s in ("rate limit", "too many requests", "429", "quota", "throttle"))
            is_conn = any(s in emsg for s in ("timeout", "connection", "network", "unreachable", "refused"))
            if attempt < max_retries and (is_rate_limit or is_conn):
                if is_rate_limit:
                    delay = 60 if attempt == 0 else (2 ** attempt) * 30 + random.uniform(5, 15)
                    print(f"Rate limit (attempt {attempt + 1}/{max_retries + 1}): {e}")
                else:
                    delay = (1.5 ** attempt) + random.uniform(0, 0.5)
                    print(f"Connection error (attempt {attempt + 1}/{max_retries + 1}): {e}")
                print(f"Retrying in {delay:.1f}s...")
                time.sleep(delay)
                continue
            raise

    raise RuntimeError("Maximum retries exceeded")
