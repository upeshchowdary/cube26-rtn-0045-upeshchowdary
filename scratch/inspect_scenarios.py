import csv
from pathlib import Path

in_rows = list(csv.DictReader(Path('agent/manual_test_images/returns_input_30.csv').read_text(encoding='utf-8').splitlines()))
out_rows = list(csv.DictReader(Path('agent/manual_test_images/returns_output_30.csv').read_text(encoding='utf-8').splitlines()))

for i, (r_in, r_out) in enumerate(zip(in_rows, out_rows)):
    sc = r_in.get('scenario', '')
    pm = r_out.get('parts_missing', '')
    if pm:
        print(f"Row {i+1} ({r_in['returned_record_id']}): parts_list='{r_in['parts_list']}', parts_missing='{pm}'")
        print(f"   scenario: {sc[:120]}...")
