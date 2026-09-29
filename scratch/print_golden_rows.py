import csv
from pathlib import Path

out_rows = list(csv.DictReader(Path('agent/manual_test_images/returns_output_30.csv').read_text(encoding='utf-8').splitlines()))
for r in out_rows:
    if r['record_id'] in ['RTN-AIR-02', 'RTN-AIR-03', 'RTN-LEASH-02', 'RTN-LEASH-03', 'RTN-SHAMPOO-02', 'RTN-SHAMPOO-03']:
        print(f"--- {r['record_id']} ---")
        print(f"parts_list: {r.get('parts_list')}")
        print(f"parts_missing: {r.get('parts_missing')}")
        print(f"disposition: {r.get('operator_disposition')}")
        print(f"notes: {r.get('notes')}")
