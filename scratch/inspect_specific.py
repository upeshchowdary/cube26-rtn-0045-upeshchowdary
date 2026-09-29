import csv
from pathlib import Path

in_rows = list(csv.DictReader(Path('agent/manual_test_images/returns_input_30.csv').read_text(encoding='utf-8').splitlines()))

target_ids = ['RTN-WATCH-03', 'RTN-PHONE-02', 'RTN-PHONE-05', 'RTN-PUZZLE-04', 'RTN-LEASH-02', 'RTN-LEASH-03', 'RTN-KETTLE-02', 'RTN-CEREAL-02']
for r in in_rows:
    if r['returned_record_id'] in target_ids:
        print(f"--- {r['returned_record_id']} ---")
        print(f"parts_list: {r['parts_list']}")
        print(f"scenario: {r['scenario']}")
