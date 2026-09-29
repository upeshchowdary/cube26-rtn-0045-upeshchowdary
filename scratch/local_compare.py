import csv
from pathlib import Path

dl = list(csv.DictReader(Path('scratch/downloaded_output_01M3NW6XTER0G32HPG9PZRH5TZ.csv').read_text(encoding='utf-8').splitlines()))
gd = list(csv.DictReader(Path('agent/manual_test_images/returns_output_30.csv').read_text(encoding='utf-8').splitlines()))

print(f"Total downloaded: {len(dl)}, Total golden: {len(gd)}")
diffs = 0
for i, (d, g) in enumerate(zip(dl, gd)):
    for f in ['record_id', 'unit_id', 'operator_disposition', 'amazon_condition', 'observed_state', 'parts_missing']:
        vd = d.get(f, '').strip()
        vg = g.get(f, '').strip()
        if vd != vg:
            print(f"Row {i+1} ({d.get('record_id')}) field '{f}': downloaded={vd!r} vs golden={vg!r}")
            diffs += 1

if diffs == 0:
    print("PERFECT 100% MATCH ON ALL 30 ROWS AND ALL FIELDS!")
else:
    print(f"Total diffs: {diffs}")
