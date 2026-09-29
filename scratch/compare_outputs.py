import requests, csv
from pathlib import Path

r = requests.get('http://127.0.0.1:8000/api/v1/batch/jobs/01M3NV2QKHPBSKQK4GW41VGXN1/output.csv', headers={'X-API-Key': 'rmk_local_s8dPJ1uaqqsA89grddXAj3SEUEKIWPbthNkKURXH'})
downloaded = list(csv.DictReader(r.text.splitlines()))

golden_path = Path('agent/manual_test_images/returns_output_30.csv')
golden = list(csv.DictReader(golden_path.read_text(encoding='utf-8').splitlines()))

print(f'Downloaded rows count: {len(downloaded)}')
print(f'Golden rows count: {len(golden)}')

diffs = 0
for i, (d, g) in enumerate(zip(downloaded, golden)):
    for field in ['record_id', 'unit_id', 'operator_disposition', 'amazon_condition', 'observed_state', 'parts_missing']:
        val_d = d.get(field, '').strip()
        val_g = g.get(field, '').strip()
        if val_d != val_g:
            print(f"Diff in row {i+1} ({d.get('record_id')}) field {field}: downloaded={val_d!r} vs golden={val_g!r}")
            diffs += 1
if diffs == 0:
    print('ALL 30 ROWS MATCH returns_output_30.csv PERFECTLY!')
else:
    print(f'Total field diffs: {diffs}')
