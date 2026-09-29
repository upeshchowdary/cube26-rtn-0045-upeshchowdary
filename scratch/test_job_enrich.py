import sys, json, traceback
from pathlib import Path

sys.path.insert(0, 'agent/src')
from returns_manager.batch.jobs_service import BatchJobsService
from returns_manager.config import AGENT_ROOT, get_settings

s = get_settings()
svc = BatchJobsService(AGENT_ROOT / ".data" / "batch_jobs", s, None)

org_id = 'org_demo_alpha'
job_id = '01M3MS62VX5T4C9ZMZPX55PGSF'
record_id = 'RTN-EDGE-01'

job = svc.get_job(org_id, job_id)
print("1. Job:", job.status if job else None)

path = svc._detail_path(org_id, job_id)
print("2. Detail path:", path, "exists:", path.exists())

try:
    all_detail = json.loads(path.read_text(encoding="utf-8"))
    print("3. all_detail keys count:", len(all_detail))
    print("4. record_id in all_detail:", record_id in all_detail)
    detail = all_detail.get(record_id)
except Exception as e:
    print("3/4 error:", e)

rows = svc.output_rows(org_id, job_id) or []
print("5. rows count:", len(rows))
matched_row = next((r for r in rows if r.get("record_id") == record_id), None)
print("6. matched_row found:", matched_row is not None)

job_dir = svc._job_dir(org_id, job_id)
before_path = job_dir / "before.csv"
print("7. before_path exists:", before_path.exists())

from returns_manager.batch.io_csv import read_before_csv, ReturnedRow
from returns_manager.batch.similarity import compute_before_after_similarity

before_by_unit = read_before_csv(before_path) if before_path.exists() else {}
print("8. before_by_unit count:", len(before_by_unit))

unit_id = (matched_row.get("unit_id") if matched_row else None) or detail.get("unit_id", "")
print("9. unit_id:", unit_id)
before = before_by_unit.get(unit_id)
print("10. before found:", before is not None)

try:
    ret_photos = (
        [p for p in (matched_row.get("photo_refs") or "").split(";") if p]
        if matched_row
        else detail.get("returned_photo_refs")
        or [p.get("url", "") for p in detail.get("photos", []) if p.get("url")]
    )
    print("11. ret_photos:", ret_photos)

    ret_row = ReturnedRow(
        record_id=record_id,
        unit_id=unit_id,
        org_id=org_id,
        order_id=(matched_row.get("order_id") if matched_row else None) or detail.get("order_id", ""),
        ordered_sku=(matched_row.get("ordered_sku") if matched_row else None) or detail.get("sku", ""),
        ordered_asin=(matched_row.get("ordered_asin") if matched_row else None) or detail.get("asin", ""),
        returned_photo_refs=tuple(ret_photos),
        time=(matched_row.get("captured_at") if matched_row else None) or detail.get("captured_at", ""),
    )
    print("12. ret_row created")
    
    parts_comp = detail.get("completeness", {})
    comp_items = parts_comp.get("components", [])
    expected_parts = [c.get("name", "") for c in comp_items]
    missing_parts = [c.get("name", "") for c in comp_items if c.get("status") == "missing"]

    cond_info = detail.get("condition", {})
    out_repr = {
        "parts_list": ";".join(expected_parts),
        "parts_missing": ";".join(missing_parts),
        "amazon_condition": cond_info.get("amazon_condition", "")
        or (matched_row.get("amazon_condition") if matched_row else ""),
        "observed_state": cond_info.get("state", "")
        or (matched_row.get("observed_state") if matched_row else ""),
        "operator_disposition": detail.get("decision", {}).get("recommended_disposition", "")
        or (matched_row.get("operator_disposition") if matched_row else ""),
        "sold_vs_returned_id_check": matched_row.get("sold_vs_returned_id_check", "") if matched_row else "",
    }
    sim = compute_before_after_similarity(before, ret_row, out_repr)
    print("13. sim computed:", sim["confidence"])
except Exception as e:
    print("Exception in step:")
    traceback.print_exc()
