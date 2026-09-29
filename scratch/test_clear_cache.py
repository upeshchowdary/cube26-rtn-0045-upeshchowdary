import os
import sys

# The API key comes from the environment; it is never committed (audit A12).
RM_API_KEY = os.environ.get("RM_API_KEY") or sys.exit(
    "RM_API_KEY is not set. Mint a key with `returns-manager keys create` and export RM_API_KEY."
)
from pathlib import Path

import httpx

API_URL = "http://127.0.0.1:8000/api/v1/batch"
API_KEY = RM_API_KEY
HEADERS = {"X-API-Key": API_KEY}
CSV_PATH = Path(
    r"c:\Users\UPESH CHOWDARY\OneDrive\Desktop\cube26-rtn-0045-upeshchowdary-main\cube26-rtn-0045-upeshchowdary\agent\manual_test_images\returns_input_30.csv"
)


def test_full_clear_cache_cycle():
    with httpx.Client(headers=HEADERS, timeout=30.0) as client:
        print("[1] Uploading a batch job...")
        with open(CSV_PATH, "rb") as f:
            files = {"file": ("returns_input_30.csv", f, "text/csv")}
            data = {"confirm_spend": "true", "max_requests": "5"}
            res = client.post(f"{API_URL}/jobs", files=files, data=data)
            assert res.status_code == 202, res.text
            job = res.json()
            job_id = job["job_id"]
            print(f"Created job {job_id}")

        print("[2] Listing jobs...")
        res = client.get(f"{API_URL}/jobs")
        assert res.status_code == 200
        jobs = res.json()
        print(f"Found {len(jobs)} jobs before clear.")
        assert len(jobs) >= 1

        print("[3] Calling POST /api/v1/batch/cache/clear...")
        res = client.post(f"{API_URL}/cache/clear")
        assert res.status_code == 200, res.text
        data = res.json()
        print(f"Cache clear result: {data}")
        assert data.get("cleared", 0) >= 1

        print("[4] Checking jobs list after clear...")
        res = client.get(f"{API_URL}/jobs")
        assert res.status_code == 200
        jobs_after = res.json()
        print(f"Jobs remaining: {len(jobs_after)}")
        assert len(jobs_after) == 0, f"Expected 0 jobs, found {len(jobs_after)}"

        print(">>> SUCCESS: Full cache clear cycle verified successfully!")


if __name__ == "__main__":
    test_full_clear_cache_cycle()
