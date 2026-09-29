import csv
import sys
from pathlib import Path

# Add agent/src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "agent" / "src"))

from returns_manager.batch.io_csv import BeforeRow, ReturnedRow
from returns_manager.batch.similarity import compute_before_after_similarity

root = Path(__file__).parent.parent
input_path = root / "agent" / "manual_test_images" / "returns_input_30.csv"
with open(input_path, encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

print(f"{'RECORD ID':14} | {'CONF':4} | {'AUTO':5} | {'DISPOSITION':14} | {'CONDITION':16} | {'RULE ID'}")
print("-" * 80)
for r in rows:
    rec_id = r["returned_record_id"].strip()
    unit_id = r["unit_id"].strip()
    before = BeforeRow(
        record_id=r.get("sold_record_id", "").strip(),
        unit_id=unit_id,
        org_id=r.get("sold_org_id", "").strip(),
        order_id=r.get("sold_order_id", "").strip(),
        ordered_sku=r.get("sold_sku", "").strip(),
        ordered_asin=r.get("sold_asin", "").strip(),
        identity_match=r.get("identity_match", "").strip(),
        parts_list=r.get("parts_list", "").strip(),
        time=r.get("sold_time", "").strip(),
        photo_ref=r.get("sold_photo_url", "").strip(),
        category=r.get("category", "").strip(),
    )
    ret_row = ReturnedRow(
        record_id=rec_id,
        unit_id=unit_id,
        org_id=r.get("returned_org_id", "").strip(),
        order_id=r.get("returned_order_id", "").strip(),
        ordered_sku=r.get("returned_sku", "").strip(),
        ordered_asin=r.get("returned_asin", "").strip(),
        returned_photo_refs=tuple(p.strip() for p in r.get("returned_photo_url", "").split(";") if p.strip()),
        time=r.get("returned_time", "").strip(),
    )
    sim = compute_before_after_similarity(before, ret_row, {})
    print(f"{rec_id:14} | {sim['confidence']:3}% | {str(sim['is_auto_approved']):5} | {sim['recommended_disposition']:14} | {sim['resolved_condition']:16} | {sim['rule_id']}")
