import os
import sys

# The API key comes from the environment; it is never committed (audit A12).
RM_API_KEY = os.environ.get("RM_API_KEY") or sys.exit(
    "RM_API_KEY is not set. Mint a key with `returns-manager keys create` and export RM_API_KEY."
)
import sys
import time
from pathlib import Path

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

API_BASE = "http://127.0.0.1:8000"
API_KEY = RM_API_KEY
HEADERS = {"X-API-Key": API_KEY}

REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = REPO_ROOT / "agent" / "manual_test_images" / "returns_input_30.csv"
GOLDEN_OUTPUT_FILE = (
    REPO_ROOT / "agent" / "manual_test_images" / "returns_output_30.csv"
)


def run():
    print("1. Checking backend health...")
    r = requests.get(f"{API_BASE}/health")
    print(f"Health response: {r.status_code} {r.text}")
    assert r.status_code == 200

    print(f"2. Uploading {INPUT_FILE.name} to /api/v1/batch/jobs ...")
    with open(INPUT_FILE, "rb") as f:
        files = {"file": (INPUT_FILE.name, f, "text/csv")}
        data = {"confirm_spend": "true"}
        r = requests.post(
            f"{API_BASE}/api/v1/batch/jobs", headers=HEADERS, files=files, data=data
        )
    print(f"Upload response: {r.status_code}")
    print(r.text)
    assert r.status_code in (200, 202), f"Upload failed: {r.text}"
    job = r.json()
    job_id = job["job_id"]
    print(f"Created Job ID: {job_id}")

    print(f"3. Polling job {job_id} until completion...")
    for _ in range(60):
        r = requests.get(f"{API_BASE}/api/v1/batch/jobs/{job_id}", headers=HEADERS)
        status_data = r.json()
        status = status_data.get("status")
        processed = status_data.get("processed", 0)
        total = status_data.get("total_rows", 0)
        print(f"  Job status: {status} ({processed}/{total})")
        if status in ("done", "failed"):
            break
        time.sleep(1)

    assert status == "done", f"Job ended in status: {status}"

    print(f"4. Fetching processed rows from /api/v1/batch/jobs/{job_id}/rows ...")
    r = requests.get(f"{API_BASE}/api/v1/batch/jobs/{job_id}/rows", headers=HEADERS)
    assert r.status_code == 200
    rows = r.json()
    print(f"  Retrieved {len(rows)} rows.")

    print(f"5. Downloading output CSV from /api/v1/batch/jobs/{job_id}/output.csv ...")
    r = requests.get(
        f"{API_BASE}/api/v1/batch/jobs/{job_id}/output.csv", headers=HEADERS
    )
    assert r.status_code == 200
    downloaded_csv = r.text
    out_path = Path("scratch") / f"downloaded_output_{job_id}.csv"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(downloaded_csv, encoding="utf-8")
    print(f"  Saved downloaded output CSV to {out_path} ({len(downloaded_csv)} bytes)")

    print("6. Checking details for row RTN-PHONE-01, RTN-PHONE-02, RTN-AIR-02 ...")
    for test_rec in ["RTN-PHONE-01", "RTN-PHONE-02", "RTN-AIR-02"]:
        r_det = requests.get(
            f"{API_BASE}/api/v1/batch/jobs/{job_id}/rows/{test_rec}/detail",
            headers=HEADERS,
        )
        print(f"  Detail for {test_rec} ({r_det.status_code}):")
        if r_det.status_code == 200:
            det = r_det.json()
            sim = det.get("similarity", {})
            print(
                f"    Confidence: {sim.get('confidence')}% | Disp: {sim.get('recommended_disposition')} | Cond: {sim.get('resolved_condition')}"
            )
            print(f"    Rule ID: {sim.get('rule_id')} | Summary: {sim.get('summary')}")

    print("\nSUCCESS: All API pipeline steps completed cleanly!")


if __name__ == "__main__":
    run()
