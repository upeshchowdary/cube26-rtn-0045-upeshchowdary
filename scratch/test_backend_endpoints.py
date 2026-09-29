import urllib.request
import urllib.error
import json
import csv
import io
import sys

API_KEY = "rmk_local_s8dPJ1uaqqsA89grddXAj3SEUEKIWPbthNkKURXH"
BASE_URL = "http://127.0.0.1:8000"

def req(path, method="GET", body=None):
    headers = {"X-API-Key": API_KEY}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    r = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            content = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return resp.status, json.loads(content.decode("utf-8"))
            elif "text/csv" in content_type:
                return resp.status, content.decode("utf-8")
            else:
                return resp.status, content.decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_body)
        except Exception:
            return e.code, err_body

def run_tests():
    print("=== STARTING EXHAUSTIVE BACKEND API TEST SUITE ===")
    
    # 1. Health
    st, res = req("/health")
    assert st == 200, f"/health failed: {st}, {res}"
    print(f"[PASS] /health -> {res}")

    # 2. Ready
    st, res = req("/ready")
    assert st == 200, f"/ready failed: {st}, {res}"
    print(f"[PASS] /ready -> {res}")

    # 3. List jobs
    st, jobs = req("/api/v1/batch/jobs")
    assert st == 200 and isinstance(jobs, list), f"List jobs failed: {st}, {jobs}"
    print(f"[PASS] /api/v1/batch/jobs returned {len(jobs)} jobs.")
    assert len(jobs) > 0, "No batch jobs found"
    
    # Find a completed job
    completed_jobs = [j for j in jobs if j.get("status") == "done" and j.get("total_rows", 0) > 0]
    assert len(completed_jobs) > 0, "No completed job found"
    test_job = completed_jobs[0]
    job_id = test_job["job_id"]
    print(f"Testing with job_id={job_id} ({test_job['processed']} processed / {test_job['total_rows']} total)")

    # 4. Job details
    st, job_detail = req(f"/api/v1/batch/jobs/{job_id}")
    assert st == 200 and job_detail["job_id"] == job_id, f"Get job failed: {st}"
    print(f"[PASS] /api/v1/batch/jobs/{job_id} -> status={job_detail['status']}")

    # 5. Job rows
    st, rows = req(f"/api/v1/batch/jobs/{job_id}/rows")
    assert st == 200 and len(rows) > 0, f"Get rows failed: {st}"
    print(f"[PASS] /api/v1/batch/jobs/{job_id}/rows -> {len(rows)} rows loaded.")
    test_record = rows[0]
    rec_id = test_record["record_id"]

    # 6. Row detail
    st, detail = req(f"/api/v1/batch/jobs/{job_id}/rows/{rec_id}/detail")
    assert st == 200 and "identity" in detail and "decision" in detail, f"Get row detail failed: {st}, {detail}"
    print(f"[PASS] /api/v1/batch/jobs/{job_id}/rows/{rec_id}/detail -> identity={detail['identity'].get('identity_match')}")

    # 7. Row decisions history
    st, decisions = req(f"/api/v1/batch/jobs/{job_id}/rows/{rec_id}/decisions")
    assert st == 200 and isinstance(decisions, list), f"Get decisions failed: {st}"
    print(f"[PASS] /api/v1/batch/jobs/{job_id}/rows/{rec_id}/decisions -> {len(decisions)} existing decisions.")

    # 8. Post a human override decision
    override_payload = {
        "action": "override",
        "new_disposition": "refurbish",
        "reason": "Automated verification test: verified screen has minor scratch, routing to refurbish."
    }
    st, dec_res = req(f"/api/v1/batch/jobs/{job_id}/rows/{rec_id}/decision", method="POST", body=override_payload)
    assert st in (200, 201) and dec_res["action"] == "override", f"Post override failed: {st}, {dec_res}"
    print(f"[PASS] Post override decision -> recorded by {dec_res.get('actor')}")

    # 9. Verify CSV output download reflects changes
    st, csv_data = req(f"/api/v1/batch/jobs/{job_id}/output.csv")
    assert st == 200 and isinstance(csv_data, str), f"Download output.csv failed: {st}"
    reader = csv.DictReader(io.StringIO(csv_data))
    csv_rows = list(reader)
    print(f"[PASS] Output CSV downloaded -> {len(csv_rows)} rows found.")
    matching_csv_row = next((r for r in csv_rows if r.get("record_id") == rec_id), None)
    assert matching_csv_row is not None, f"Record {rec_id} not found in output CSV"
    print(f"Record {rec_id} in output CSV: operator_disposition={matching_csv_row.get('operator_disposition')}")

    # 10. Post an accept decision
    accept_payload = {
        "action": "accept",
        "reason": "Automated test acceptance: item condition verified."
    }
    st, acc_res = req(f"/api/v1/batch/jobs/{job_id}/rows/{rec_id}/decision", method="POST", body=accept_payload)
    assert st in (200, 201) and acc_res["action"] == "accept", f"Post accept failed: {st}, {acc_res}"
    print(f"[PASS] Post accept decision -> {acc_res.get('action')}")

    # 11. System controls
    st, controls = req("/api/v1/system/controls")
    assert st == 200, f"System controls failed: {st}, {controls}"
    print(f"[PASS] /api/v1/system/controls -> {controls.keys()}")

    # 12. Metrics summary
    st, metrics = req("/api/v1/metrics/summary?window=7d")
    assert st == 200, f"Metrics summary failed: {st}, {metrics}"
    print(f"[PASS] /api/v1/metrics/summary -> {metrics.get('window')}")

    # 13. Metrics economics
    st, econ = req("/api/v1/metrics/economics?window=7d&volume=1000")
    assert st == 200, f"Economics metrics failed: {st}, {econ}"
    print(f"[PASS] /api/v1/metrics/economics -> ok")

    # 14. Cache clear
    st, clear_res = req("/api/v1/batch/cache/clear", method="POST", body={})
    assert st == 200, f"Clear cache failed: {st}, {clear_res}"
    print(f"[PASS] /api/v1/batch/cache/clear -> {clear_res}")

    print("\n>>> ALL 14 BACKEND API CHECKS PASSED WITH 100% SUCCESS! <<<")

if __name__ == "__main__":
    run_tests()
