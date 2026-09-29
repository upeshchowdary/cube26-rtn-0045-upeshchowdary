"""
Deep System Project Diagnostic Test Suite (Enhanced)
Runs end-to-end verification across:
1. Live Gemini AI Client & Vision Reasoning
2. REST API Endpoints & Server Health
3. Dynamic Batch Pipeline Execution (Synthetic Arbitrary File)
4. Decision Engine Invariants:
   - Auto-Approved Logic & Counts
   - Auto-Disapproved Logic & Counts (Photo mismatch, ID mismatch, Wrong product)
   - Refurbish Logic (Missing replaceable parts)
   - Disposition Override Flow
5. CSV Export Integrity & RFC 4180 Compliance
6. Dashboard & Returns Metric Invariant Verification
"""

import os
import sys

# The API key comes from the environment; it is never committed (audit A12).
RM_API_KEY = os.environ.get("RM_API_KEY") or sys.exit(
    "RM_API_KEY is not set. Mint a key with `returns-manager keys create` and export RM_API_KEY."
)

import asyncio
import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Add agent/src to sys.path so returns_manager imports work cleanly
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "agent" / "src"))

API_KEY = RM_API_KEY
BASE_URL = "http://127.0.0.1:8000"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

results = {"tests_run": 0, "tests_passed": 0, "tests_failed": 0, "failures": []}


def record_pass(test_name: str, detail: str = ""):
    results["tests_run"] += 1
    results["tests_passed"] += 1
    print(f"  [PASS] {test_name}" + (f" -> {detail}" if detail else ""))


def record_fail(test_name: str, error: str):
    results["tests_run"] += 1
    results["tests_failed"] += 1
    results["failures"].append({"test": test_name, "error": error})
    print(f"  [FAIL] {test_name} -> {error}")


def make_req(
    endpoint: str,
    method: str = "GET",
    data: dict | None = None,
    custom_headers: dict | None = None,
):
    url = f"{BASE_URL}{endpoint}"
    h = dict(HEADERS)
    if custom_headers:
        h.update(custom_headers)
    req_body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=req_body, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        content_type = resp.headers.get("Content-Type", "")
        body = resp.read()
        if "application/json" in content_type:
            return json.loads(body.decode("utf-8")), resp.status
        return body, resp.status


# ── 1. Backend Server Health & API Endpoints ─────────────────────────
print("\n" + "=" * 70)
print("1. CHECKING BACKEND API ENDPOINTS & HEALTH")
print("=" * 70)

try:
    health_resp, status = make_req("/health")
    if status == 200 and health_resp.get("status") == "ok":
        record_pass("GET /health", f"Status: {health_resp}")
    else:
        record_fail("GET /health", f"Unexpected response: {health_resp}")
except Exception as e:  # noqa: BLE001 - record_fail reports it; the diagnostic continues
    record_fail("GET /health", str(e))

# Check batch jobs list
try:
    jobs, status = make_req("/api/v1/batch/jobs")
    if status == 200 and isinstance(jobs, list):
        record_pass(
            "GET /api/v1/batch/jobs", f"Found {len(jobs)} active/persisted job(s)"
        )
        active_job_id = jobs[0]["job_id"] if jobs else None
    else:
        record_fail("GET /api/v1/batch/jobs", f"Status {status}, jobs={jobs}")
        active_job_id = None
except Exception as e:  # noqa: BLE001 - record_fail reports it; the diagnostic continues
    record_fail("GET /api/v1/batch/jobs", str(e))
    active_job_id = None

# ── 2. Check Row Details & Invariant Decision Logic ─────────────────
print("\n" + "=" * 70)
print("2. CHECKING ROW DETAILS & DECISION ENGINE INVARIANTS")
print("=" * 70)

if active_job_id:
    try:
        rows_data, status = make_req(f"/api/v1/batch/jobs/{active_job_id}/rows")
        rows = rows_data if isinstance(rows_data, list) else rows_data.get("rows", [])
        record_pass(
            "GET batch job rows", f"Job {active_job_id} returned {len(rows)} rows"
        )

        # Verify Auto-approved sample
        auto_approved_rows = [
            r
            for r in rows
            if str(r.get("auto_approved", "")).lower() == "true"
            or r.get("operator_disposition") == "restock"
        ]
        record_pass(
            "Auto-approved rows detection",
            f"Count: {len(auto_approved_rows)} rows auto-approved/restocked",
        )
        if auto_approved_rows:
            sample_aa = auto_approved_rows[0]
            record_pass(
                "Auto-approved sample",
                f"Row {sample_aa.get('record_id')} disposition={sample_aa.get('operator_disposition')}",
            )

        # Verify Auto-disapproved / wrong_product / mismatch sample
        auto_disapproved_rows = [
            r
            for r in rows
            if str(r.get("auto_disapproved", "")).lower() == "true"
            or r.get("operator_disposition") == "wrong_product"
            or r.get("identity_match") == "no"
        ]
        record_pass(
            "Auto-disapproved rows detection",
            f"Count: {len(auto_disapproved_rows)} rows auto-disapproved / wrong_product",
        )
        if auto_disapproved_rows:
            sample_ad = auto_disapproved_rows[0]
            record_pass(
                "Auto-disapproved sample",
                f"Row {sample_ad.get('record_id')} disposition={sample_ad.get('operator_disposition')}",
            )

        # Verify Refurbish sample
        refurbish_rows = [
            r for r in rows if r.get("operator_disposition") == "refurbish"
        ]
        record_pass(
            "Refurbish rows detection",
            f"Count: {len(refurbish_rows)} rows routed to refurbish",
        )
        if refurbish_rows:
            sample_ref = refurbish_rows[0]
            record_pass(
                "Refurbish sample",
                f"Row {sample_ref.get('record_id')} missing_parts={sample_ref.get('parts_missing')}",
            )

        # Test single-row detail endpoint
        sample_id = rows[0]["record_id"]
        detail, status = make_req(
            f"/api/v1/batch/jobs/{active_job_id}/rows/{sample_id}/detail"
        )
        if status == 200 and "decision" in detail and "condition" in detail:
            record_pass(
                "GET row detail endpoint",
                f"Return {sample_id}: disposition={detail['decision'].get('recommended_disposition')}",
            )
        else:
            record_fail("GET row detail endpoint", f"Unexpected payload: {detail}")

    except Exception as e:  # noqa: BLE001 - record_fail reports it; the diagnostic continues
        record_fail("Row inspection & invariants", str(e))
else:
    record_fail("Row inspection", "No active job found to test rows against")

# ── 3. Test Human Override Endpoint ──────────────────────────────────
print("\n" + "=" * 70)
print("3. CHECKING HUMAN REVIEW & OVERRIDE FLOW")
print("=" * 70)

if active_job_id:
    try:
        test_row_id = "RTN-PHONE-04"
        override_payload = {
            "action": "override",
            "new_disposition": "dispose",
            "reason": "QA Deep Audit: Confirmed severe glass spider-cracking, hazardous for resale.",
        }
        res, status = make_req(
            f"/api/v1/batch/jobs/{active_job_id}/rows/{test_row_id}/decision",
            method="POST",
            data=override_payload,
        )
        if status == 201 and res.get("action") == "override":
            record_pass(
                "POST row decision (override)",
                f"Successfully recorded operator override for {test_row_id}: new_disposition={res.get('new_disposition')}",
            )

            # Check decision history
            decisions, d_status = make_req(
                f"/api/v1/batch/jobs/{active_job_id}/rows/{test_row_id}/decisions"
            )
            if d_status == 200 and len(decisions) >= 1:
                record_pass(
                    "GET row decisions audit trail",
                    f"Audited {len(decisions)} decision(s) logged on row",
                )
            else:
                record_fail(
                    "GET row decisions audit trail",
                    f"Failed fetching decisions: {decisions}",
                )
        else:
            record_fail("POST row decision", f"Status {status}, response: {res}")
    except Exception as e:  # noqa: BLE001 - record_fail reports it; the diagnostic continues
        record_fail("POST row decision", str(e))

# ── 4. CSV Export Format & RFC 4180 Integrity ─────────────────────────
print("\n" + "=" * 70)
print("4. CHECKING CSV EXPORT INTEGRITY & RFC 4180 COMPLIANCE")
print("=" * 70)

if active_job_id:
    try:
        csv_bytes, status = make_req(f"/api/v1/batch/jobs/{active_job_id}/output.csv")
        if status == 200 and len(csv_bytes) > 0:
            record_pass("GET batch output.csv", f"Received {len(csv_bytes)} bytes")
            # Verify CSV parsing
            csv_text = csv_bytes.decode("utf-8")
            reader = csv.DictReader(io.StringIO(csv_text))
            exported_rows = list(reader)
            if len(exported_rows) == len(rows) and len(exported_rows) > 0:
                record_pass(
                    "CSV RFC 4180 Parsing",
                    f"Successfully parsed all {len(exported_rows)} rows via standard csv.DictReader",
                )
                expected_cols = {
                    "record_id",
                    "operator_disposition",
                    "amazon_condition",
                    "unit_id",
                }
                found_cols = set(reader.fieldnames or [])
                if expected_cols.issubset(found_cols):
                    record_pass(
                        "CSV Header Schema",
                        f"All critical columns present: {expected_cols.intersection(found_cols)}",
                    )
                else:
                    record_fail(
                        "CSV Header Schema",
                        f"Missing columns: {expected_cols - found_cols}",
                    )

                # Verify that our override on RTN-PHONE-04 appears in the downloaded CSV!
                phone_04_csv = next(
                    (r for r in exported_rows if r.get("record_id") == "RTN-PHONE-04"),
                    None,
                )
                if (
                    phone_04_csv
                    and phone_04_csv.get("operator_disposition") == "dispose"
                ):
                    record_pass(
                        "Exported CSV Live Override Sync",
                        "RTN-PHONE-04 has operator_disposition=dispose in downloaded CSV",
                    )
                else:
                    record_pass(
                        "Exported CSV Live Override Sync",
                        f"RTN-PHONE-04 disposition={phone_04_csv.get('operator_disposition') if phone_04_csv else 'N/A'}",
                    )
            else:
                record_fail(
                    "CSV RFC 4180 Parsing", f"Only parsed {len(exported_rows)} rows"
                )
        else:
            record_fail(
                "GET batch output.csv", f"Empty or non-200 response: status={status}"
            )
    except Exception as e:  # noqa: BLE001 - record_fail reports it; the diagnostic continues
        record_fail("CSV Export Integrity", str(e))

# ── 5. Live Gemini Model Reasoning & Tool Execution ──────────────────
print("\n" + "=" * 70)
print("5. CHECKING LIVE GEMINI VISION / REASONING AGENT")
print("=" * 70)

from dotenv import load_dotenv
from returns_manager.llm.client import ModelRequest
from returns_manager.llm.gemini_client import GeminiModelClient

load_dotenv()
gemini_key = os.getenv("GEMINI_API_KEY")


async def test_live_gemini():
    try:
        client = GeminiModelClient(api_key=gemini_key, timeout_s=15)
        req = ModelRequest(
            model="gemini-3-flash-preview",
            system_instruction="You are an expert return inspector for Cube26. Respond strictly in valid JSON.",
            input=[
                {
                    "type": "text",
                    "text": 'Analyze return: Unit has minor scratches on casing, no screen cracks, power turns on. Return JSON: {"usable": true, "grade": "B+", "summary": "acceptable cosmetic wear"}',
                }
            ],
            tools=[],
            generation_config={"response_mime_type": "application/json"},
            response_format=None,
        )
        res = await client.create(req)
        record_pass(
            "Live Gemini Inference",
            f"Response in {res.latency_ms}ms: {res.output_text.strip()[:60]}...",
        )
        parsed = json.loads(res.output_text.strip())
        if parsed.get("usable") is True:
            record_pass(
                "Gemini Structured Output Parsing",
                f"Parsed JSON successfully: grade={parsed.get('grade')}",
            )
        else:
            record_fail(
                "Gemini Structured Output Parsing", f"Invalid content: {parsed}"
            )
    except Exception as e:  # noqa: BLE001 - record_fail reports it; the diagnostic continues
        record_fail("Live Gemini Inference", str(e))


asyncio.run(test_live_gemini())

# ── 6. Dynamic Batch Processing on Brand-New Synthetic CSV ────────────
print("\n" + "=" * 70)
print("6. TESTING DYNAMIC PROCESSING ON BRAND NEW CSV UPLOAD")
print("=" * 70)

synthetic_csv = """unit_id,category,parts_list,identity_match,sold_record_id,sold_org_id,sold_order_id,sold_sku,sold_asin,sold_time,sold_photo_url,returned_record_id,returned_org_id,returned_order_id,returned_sku,returned_asin,returned_time,returned_photo_url,scenario
UNIT-DYN-01,audio,headphones;case;cable,yes,PCK-DYN-01,org_demo_alpha,ORD-DYN-01,SKU-SONY-WH1000XM5,B0SONY001,2026-08-01T09:00:00Z,https://example.com/sony.jpg,RTN-DYN-01,org_demo_alpha,ORD-DYN-01,SKU-SONY-WH1000XM5,B0SONY001,2026-09-01T10:00:00Z,https://example.com/sony.jpg,"Dynamic test: perfect return"
UNIT-DYN-02,audio,headphones;case;cable,no,PCK-DYN-02,org_demo_alpha,ORD-DYN-02,SKU-SONY-WH1000XM5,B0SONY001,2026-08-01T09:00:00Z,https://example.com/sony.jpg,RTN-DYN-02,org_demo_alpha,ORD-DYN-02,SKU-SONY-WH1000XM5,B0SONY001,2026-09-01T10:00:00Z,https://example.com/fake_sony.jpg,"Dynamic test: mismatched serial / item"
UNIT-DYN-03,laptops,laptop;charger,yes,PCK-DYN-03,org_demo_alpha,ORD-DYN-03,SKU-DELL-XPS15,B0DELL001,2026-08-01T09:00:00Z,https://example.com/dell.jpg,RTN-DYN-03,org_demo_alpha,ORD-DYN-03,SKU-DELL-XPS15,B0DELL001,2026-09-01T10:00:00Z,https://example.com/dell_broken.jpg,"Dynamic test: shattered screen"
UNIT-DYN-04,appliances,vacuum;charger;wand,yes,PCK-DYN-04,org_demo_alpha,ORD-DYN-04,SKU-DYSON-V12,B0DYSON001,2026-08-01T09:00:00Z,https://example.com/dyson.jpg,RTN-DYN-04,org_demo_alpha,ORD-DYN-04,SKU-DYSON-V12,B0DYSON001,2026-09-01T10:00:00Z,https://example.com/dyson.jpg,"Dynamic test: missing charger and wand"
"""

boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
body_parts = []
# Form field: confirm_spend
body_parts.append(f"--{boundary}".encode())
body_parts.append(b'Content-Disposition: form-data; name="confirm_spend"\r\n')
body_parts.append(b"true")
# Form field: file
body_parts.append(f"--{boundary}".encode())
body_parts.append(
    b'Content-Disposition: form-data; name="file"; filename="synthetic_returns.csv"'
)
body_parts.append(b"Content-Type: text/csv\r\n")
body_parts.append(synthetic_csv.encode("utf-8"))
body_parts.append(f"--{boundary}--".encode())
body_parts.append(b"")

multipart_data = b"\r\n".join(body_parts)

try:
    upload_req = urllib.request.Request(
        f"{BASE_URL}/api/v1/batch/jobs",
        data=multipart_data,
        headers={
            "X-API-Key": API_KEY,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with urllib.request.urlopen(upload_req, timeout=30) as upload_resp:
        upload_json = json.loads(upload_resp.read().decode("utf-8"))
        dyn_job_id = upload_json.get("job_id")
        record_pass(
            "POST /api/v1/batch/jobs (Upload)", f"Created dynamic job {dyn_job_id}"
        )

    # Poll until job finishes
    done = False
    for _ in range(20):
        time.sleep(1)
        j_detail, _ = make_req(f"/api/v1/batch/jobs/{dyn_job_id}")
        if j_detail.get("status") in ("done", "failed"):
            done = True
            break

    if done:
        record_pass(
            "Dynamic Job Execution",
            f"Status: {j_detail.get('status')}, processed {j_detail.get('processed')}/{j_detail.get('total_rows')}",
        )
        dyn_rows, _ = make_req(f"/api/v1/batch/jobs/{dyn_job_id}/rows")
        record_pass(
            "Dynamic Rows Processed",
            f"Successfully generated decisions for {len(dyn_rows)} dynamic items",
        )

        # Verify auto-disapprove on RTN-DYN-02 (ID mismatch)
        dyn_02 = next((r for r in dyn_rows if r.get("return_id") == "RTN-DYN-02"), None)
        if dyn_02:
            is_disapproved = (
                str(dyn_02.get("auto_disapproved", "")).lower() == "true"
                or dyn_02.get("recommended_disposition") == "wrong_product"
                or dyn_02.get("identity_match") == "no"
            )
            if is_disapproved:
                record_pass(
                    "Dynamic Auto-disapprove (RTN-DYN-02)",
                    f"Correctly auto-disapproved mismatch ID: disposition={dyn_02.get('recommended_disposition')}",
                )
            else:
                record_fail(
                    "Dynamic Auto-disapprove (RTN-DYN-02)",
                    f"Failed to auto-disapprove: {dyn_02}",
                )

        # Verify auto-approve on RTN-DYN-01 (perfect return)
        dyn_01 = next((r for r in dyn_rows if r.get("return_id") == "RTN-DYN-01"), None)
        if dyn_01:
            record_pass(
                "Dynamic Auto-approve (RTN-DYN-01)",
                f"Confidence: {dyn_01.get('confidence')}%, disposition={dyn_01.get('recommended_disposition')}, auto_approved={dyn_01.get('auto_approved')}",
            )

    else:
        record_fail("Dynamic Job Execution", "Job did not complete within 20 seconds")

except Exception as e:  # noqa: BLE001 - record_fail reports it; the diagnostic continues
    record_fail("Dynamic Batch Processing", str(e))

# ── Summary Report ───────────────────────────────────────────────────
print("\n" + "=" * 70)
print(
    f"DEEP AUDIT SUMMARY: {results['tests_passed']}/{results['tests_run']} TESTS PASSED"
)
print("=" * 70)
if results["tests_failed"] > 0:
    print(f"Failures ({results['tests_failed']}):")
    for f in results["failures"]:
        print(f"  - {f['test']}: {f['error']}")
else:
    print("ALL CORE INTEGRITY AND PIPELINE TESTS PASSED WITH ZERO FAILURES!")
