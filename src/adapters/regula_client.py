# src/adapters/regula_client.py
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any
from regula.documentreader.webclient import (
    DocumentReaderApi, ProcessParams, Scenario, Result, RecognitionRequest
)

DOCREADER_URL = "http://localhost:8080"  # your Docker container

def recognize_images(image_paths: List[str], scenario: Scenario = Scenario.FULL_PROCESS) -> Dict[str, Any]:
    """Send 1..N images to Regula and return a plain JSON-able dict."""
    images = [Path(p).expanduser().read_bytes() for p in image_paths]

    with DocumentReaderApi(host=DOCREADER_URL) as api:
        params = ProcessParams(
            scenario=scenario,
            result_type_output=[Result.STATUS, Result.TEXT, Result.AUTHENTICITY]
        )
        req = RecognitionRequest(process_params=params, images=images)
        resp = api.process(req)

        # Turn the SDK model into a plain dict you can JSON-dump
        return api.api_client.sanitize_for_serialization(resp)
