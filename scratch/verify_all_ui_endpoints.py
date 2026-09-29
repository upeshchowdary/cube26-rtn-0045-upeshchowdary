import os
import sys

# The API key comes from the environment; it is never committed (audit A12).
RM_API_KEY = os.environ.get("RM_API_KEY") or sys.exit(
    "RM_API_KEY is not set. Mint a key with `returns-manager keys create` and export RM_API_KEY."
)
import csv
from pathlib import Path

import requests

API_BASE = "http://127.0.0.1:8000"
UI_BASE = "http://localhost:5175"
API_KEY = RM_API_KEY
HEADERS = {"X-API-Key": API_KEY}


def verify():
    print("=" * 60)
    print("END-TO-END PIPELINE & UI DATA PROPAGATION VERIFICATION")
    print("=" * 60)

    # 1. UI Dev Server Reachability
    print("\n[1] Checking Vite UI Server (http://localhost:5175)...")
    r_ui = requests.get(UI_BASE)
    print(f"  UI Status: {r_ui.status_code}")
    assert r_ui.status_code == 200, "Vite UI dev server not responding"
    assert "<title>" in r_ui.text, "Vite UI HTML missing title"
    print("  [OK] Frontend UI dev server is running and accessible.")

    # 2. Backend API Jobs
    print("\n[2] Checking Jobs via GET /api/v1/batch/jobs ...")
    r_jobs = requests.get(f"{API_BASE}/api/v1/batch/jobs", headers=HEADERS)
    assert r_jobs.status_code == 200, f"Failed to list jobs: {r_jobs.text}"
    jobs = r_jobs.json()
    print(f"  Found {len(jobs)} batch job(s).")
    latest_job = jobs[0]
    job_id = latest_job["job_id"]
    status = latest_job["status"]
    total = latest_job["total_rows"]
    processed = latest_job["processed"]
    print(
        f"  Latest Job: ID={job_id} | Status={status} | Total={total} | Processed={processed}"
    )
    assert status == "done", f"Latest job status is {status}, expected 'done'"
    assert total == 30, f"Expected 30 rows, got {total}"

    # 3. Processed Rows & Details
    print(f"\n[3] Fetching processed rows for Job {job_id} ...")
    r_rows = requests.get(
        f"{API_BASE}/api/v1/batch/jobs/{job_id}/rows", headers=HEADERS
    )
    assert r_rows.status_code == 200, f"Failed to fetch rows: {r_rows.text}"
    rows = r_rows.json()
    print(f"  Retrieved {len(rows)} processed rows.")
    assert len(rows) == 30, f"Expected 30 rows, got {len(rows)}"

    # 4. CSV Download verification
    print(
        f"\n[4] Downloading output CSV from /api/v1/batch/jobs/{job_id}/output.csv ..."
    )
    r_csv = requests.get(
        f"{API_BASE}/api/v1/batch/jobs/{job_id}/output.csv", headers=HEADERS
    )
    assert r_csv.status_code == 200, "Failed to download output CSV"
    csv_text = r_csv.text
    downloaded_rows = list(csv.DictReader(csv_text.splitlines()))
    print(f"  Downloaded CSV row count: {len(downloaded_rows)}")
    assert len(downloaded_rows) == 30, (
        f"Expected 30 CSV rows, got {len(downloaded_rows)}"
    )

    # Golden check
    golden_path = Path("agent/manual_test_images/returns_output_30.csv")
    golden_rows = list(
        csv.DictReader(golden_path.read_text(encoding="utf-8").splitlines())
    )
    mismatches = []
    for i, (d, g) in enumerate(zip(downloaded_rows, golden_rows)):
        for f in [
            "record_id",
            "unit_id",
            "operator_disposition",
            "amazon_condition",
            "observed_state",
            "parts_missing",
        ]:
            vd = d.get(f, "").strip()
            vg = g.get(f, "").strip()
            if vd != vg:
                mismatches.append(
                    f"Row {i + 1} ({d.get('record_id')}) [{f}]: downloaded={vd!r} vs golden={vg!r}"
                )
    if mismatches:
        print(f"  Discrepancies found: {len(mismatches)}")
        for m in mismatches[:5]:
            print(f"    - {m}")
        assert False, (
            f"{len(mismatches)} discrepancies between downloaded CSV and golden output"
        )
    else:
        print(
            "  [OK] 100% PERFECT MATCH with returns_output_30.csv on all 30 rows and fields!"
        )

    # 5. UI Data Propagation Metrics (Dashboard / Returns / Analytics / Reviews)
    print("\n[5] Verifying UI Derived State & Data Propagation across pages...")

    # Calculate dispositions
    disp_counts = {}
    cond_counts = {}
    auto_approved = 0
    awaiting_review = 0
    needs_attention = 0
    wrong_products = 0

    for r in rows:
        disp = r.get("operator_disposition", "unknown")
        cond = r.get("amazon_condition", "unknown")
        disp_counts[disp] = disp_counts.get(disp, 0) + 1
        cond_counts[cond] = cond_counts.get(cond, 0) + 1

        # Check detail endpoint for confidence score
        rec_id = r["record_id"]
        r_det = requests.get(
            f"{API_BASE}/api/v1/batch/jobs/{job_id}/rows/{rec_id}/detail",
            headers=HEADERS,
        )
        if r_det.status_code == 200:
            det = r_det.json()
            sim = det.get("similarity", {})
            conf = sim.get("confidence", 0)
            is_auto = sim.get("is_auto_approved", False)
            if is_auto or conf >= 85 and disp == "restock":
                auto_approved += 1
            elif disp == "wrong_product" or r.get(
                "sold_vs_returned_id_check", ""
            ).startswith("NOT MATCHED"):
                needs_attention += 1
            else:
                awaiting_review += 1
        if disp == "wrong_product":
            wrong_products += 1

    print("\n  A. DASHBOARD METRICS:")
    print(f"     Total Returns: {len(rows)}")
    print(f"     Disposition breakdown: {disp_counts}")
    print(f"     Wrong Product Mismatches: {wrong_products}")
    print(
        f"     Restock count: {disp_counts.get('restock', 0)} ({round(disp_counts.get('restock', 0) / 30 * 100)}%)"
    )

    print("\n  B. RETURNS LEDGER METRICS:")
    print(f"     'All returns' tab: {len(rows)}")
    print(f"     'Auto-approved' tab: {auto_approved}")
    print(f"     'Awaiting review' tab: {awaiting_review}")
    print(f"     'Needs attention' tab: {needs_attention}")

    print("\n  C. ANALYTICS METRICS:")
    print(f"     Condition Grades Distribution: {cond_counts}")
    print("     Missing Components breakdown:")
    missing_items = [
        r["parts_missing"] for r in downloaded_rows if r.get("parts_missing")
    ]
    print(f"       Items with missing parts: {len(missing_items)} / 30")
    for r in downloaded_rows:
        if r.get("parts_missing"):
            print(
                f"         - {r['record_id']}: missing='{r['parts_missing']}' -> disp={r['operator_disposition']}"
            )

    print("\n  D. REVIEWS QUEUE METRICS:")
    print(
        f"     Items requiring human attention/review: {awaiting_review + needs_attention}"
    )

    print("\n" + "=" * 60)
    print("ALL VERIFICATION CHECKS PASSED WITH ZERO ERRORS!")
    print("=" * 60)


if __name__ == "__main__":
    verify()
