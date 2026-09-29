import os
import sys

# The API key comes from the environment; it is never committed (audit A12).
RM_API_KEY = os.environ.get("RM_API_KEY") or sys.exit(
    "RM_API_KEY is not set. Mint a key with `returns-manager keys create` and export RM_API_KEY."
)
import csv
from pathlib import Path

import requests

r = requests.get(
    "http://127.0.0.1:8000/api/v1/batch/jobs/01M3NVEAEY4EZV8YFDBSWW6FB9/output.csv",
    headers={"X-API-Key": RM_API_KEY},
)
dl = list(csv.DictReader(r.text.splitlines()))
gd = list(
    csv.DictReader(
        Path("agent/manual_test_images/returns_output_30.csv")
        .read_text(encoding="utf-8")
        .splitlines()
    )
)

for i, (d, g) in enumerate(zip(dl, gd)):
    for f in [
        "record_id",
        "unit_id",
        "operator_disposition",
        "amazon_condition",
        "observed_state",
        "parts_missing",
    ]:
        if d.get(f, "").strip() != g.get(f, "").strip():
            print(
                f"Row {i + 1} ({d.get('record_id')}) field {f}: dl={d.get(f)!r} vs gd={g.get(f)!r}"
            )
