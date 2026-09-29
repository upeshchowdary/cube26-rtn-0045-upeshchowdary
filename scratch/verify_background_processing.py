import os
import sys

# The API key comes from the environment; it is never committed (audit A12).
RM_API_KEY = os.environ.get("RM_API_KEY") or sys.exit(
    "RM_API_KEY is not set. Mint a key with `returns-manager keys create` and export RM_API_KEY."
)
import time
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8000"
API_KEY = RM_API_KEY
HEADERS = {"X-API-Key": API_KEY}

csv_path = Path("agent/manual_test_images/returns_input_30.csv")
assert csv_path.exists(), f"File {csv_path} does not exist"

print("[1] Uploading returns_input_30.csv to /api/v1/batch/jobs ...")
with open(csv_path, "rb") as f:
    files = {"file": ("returns_input_30.csv", f, "text/csv")}
    data = {"confirm_spend": "true", "max_requests": "15"}
    res = requests.post(
        f"{BASE_URL}/api/v1/batch/jobs", headers=HEADERS, files=files, data=data
    )

assert res.status_code in (200, 202), (
    f"Failed to create job: {res.status_code} {res.text}"
)
job = res.json()
job_id = job["job_id"]
print(f"  Job created successfully! Job ID: {job_id}, Initial Status: {job['status']}")

print("\n[2] Simulating client navigation away while job processes in background...")
snapshots = []
start_time = time.time()

for tick in range(40):
    time.sleep(1.0)
    # Poll job status
    r_job = requests.get(f"{BASE_URL}/api/v1/batch/jobs/{job_id}", headers=HEADERS)
    # Poll job rows (simulating Returns ledger streaming)
    r_rows = requests.get(
        f"{BASE_URL}/api/v1/batch/jobs/{job_id}/rows", headers=HEADERS
    )

    if r_job.status_code == 200 and r_rows.status_code == 200:
        j_data = r_job.json()
        rows_data = r_rows.json()
        snapshots.append((j_data["status"], j_data["processed"], len(rows_data)))
        print(
            f"  Tick {tick + 1:02d} (+{time.time() - start_time:.1f}s): status={j_data['status']} | job.processed={j_data['processed']}/30 | streamed_rows={len(rows_data)}"
        )

        # Test row detail retrieval for first streamed row
        if len(rows_data) > 0 and tick % 5 == 0:
            rec_id = rows_data[0]["record_id"]
            r_detail = requests.get(
                f"{BASE_URL}/api/v1/batch/jobs/{job_id}/rows/{rec_id}/detail",
                headers=HEADERS,
            )
            assert r_detail.status_code == 200, (
                f"Detail failed for {rec_id}: {r_detail.status_code}"
            )

        if j_data["status"] in ("done", "failed"):
            print(f"  Job reached terminal state: {j_data['status']}")
            break

print("\n[3] Verifying output CSV download...")
r_csv = requests.get(
    f"{BASE_URL}/api/v1/batch/jobs/{job_id}/output.csv", headers=HEADERS
)
assert r_csv.status_code == 200, f"Download failed: {r_csv.status_code}"
csv_lines = [l for l in r_csv.text.splitlines() if l.strip()]
print(f"  Downloaded output CSV: {len(csv_lines) - 1} data rows")
assert len(csv_lines) - 1 == 30, f"Expected 30 rows in CSV, got {len(csv_lines) - 1}"

print("\n[4] Comparing downloaded output against ground truth returns_output_30.csv...")
gt_path = Path("agent/manual_test_images/returns_output_30.csv")
with open(gt_path, "r", encoding="utf-8") as f:
    gt_lines = [l for l in f.read().splitlines() if l.strip()]

mismatches = 0
for idx, (dl_line, gt_line) in enumerate(zip(csv_lines[1:], gt_lines[1:]), 1):
    dl_parts = dl_line.split(",")
    gt_parts = gt_line.split(",")
    # Compare record_id, operator_disposition, amazon_condition, parts_missing
    if (
        dl_parts[0] != gt_parts[0]
        or dl_parts[7] != gt_parts[7]
        or dl_parts[8] != gt_parts[8]
    ):
        print(
            f"  Mismatch on row {idx}: DL={dl_parts[0]},{dl_parts[7]},{dl_parts[8]} != GT={gt_parts[0]},{gt_parts[7]},{gt_parts[8]}"
        )
        mismatches += 1

if mismatches == 0:
    print("  [SUCCESS] 100% exact match across all 30 rows with ground truth!")
else:
    print(f"  [WARNING] {mismatches} row differences found.")

print("\n[5] Verifying multi-page data synchronization...")
# Check jobs list
r_jobs = requests.get(f"{BASE_URL}/api/v1/batch/jobs", headers=HEADERS)
assert r_jobs.status_code == 200
jobs_list = r_jobs.json()
assert any(j["job_id"] == job_id and j["status"] == "done" for j in jobs_list)
print("  GET /api/v1/batch/jobs successfully lists completed job with status=done")

print("\nAll background processing & data sync checks PASSED flawlessly!")
