import csv
from pathlib import Path

in_rows = list(csv.DictReader(Path('agent/manual_test_images/returns_input_30.csv').read_text(encoding='utf-8').splitlines()))
for r in in_rows:
    if r['returned_record_id'] in ['RTN-AIR-02', 'RTN-AIR-03', 'RTN-SHAMPOO-02', 'RTN-SHAMPOO-03', 'RTN-LEASH-02']:
        print(f"--- {r['returned_record_id']} ---")
        print("keys:", r.keys())
        print("parts_missing in input:", r.get('parts_missing'))
        print("scenario:", r.get('scenario'))
