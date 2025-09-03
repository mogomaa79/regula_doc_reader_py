# main.py
from regula.documentreader.webclient import (
    DocumentReaderApi, ProcessParams, Scenario, Result, RecognitionRequest
)
import pathlib, sys, json

HOST = "http://localhost:8080"  # change if needed

def main(paths):
    if not paths:
        print("Usage: python main.py <img1> [img2]")
        sys.exit(1)

    images = [pathlib.Path(p).expanduser().read_bytes() for p in paths]

    with DocumentReaderApi(host=HOST) as api:
        params = ProcessParams(
            scenario=Scenario.FULL_PROCESS,
            result_type_output=[Result.STATUS, Result.TEXT, Result.AUTHENTICITY]
        )
        req = RecognitionRequest(process_params=params, images=images)
        resp = api.process(req)

        # Convert SDK response to pure Python dict using the client's serializer
        payload = api.api_client.sanitize_for_serialization(resp)

        # Save to a file named exactly "output"
        with open("output.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        print("✅ Saved JSON to ./output")

if __name__ == "__main__":
    main(sys.argv[1:])
