import csv
from pathlib import Path

rows = list(csv.DictReader(Path('agent/manual_test_images/returns_output_30.csv').read_text(encoding='utf-8').splitlines()))
print("Fieldnames:", list(rows[0].keys()))
for r in rows:
    print(f"{r['record_id']}: parts_missing='{r.get('parts_missing')}'")
