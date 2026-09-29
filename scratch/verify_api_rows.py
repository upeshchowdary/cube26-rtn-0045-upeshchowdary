import os
import sys

# The API key comes from the environment; it is never committed (audit A12).
RM_API_KEY = os.environ.get("RM_API_KEY") or sys.exit("RM_API_KEY is not set. Mint a key with `returns-manager keys create` and export RM_API_KEY.")
import urllib.request
import json
import time

time.sleep(2)  # wait for server to bind

url = "http://127.0.0.1:8000/api/v1/batch/jobs/01M3MS62VX5T4C9ZMZPX55PGSF/rows"
req = urllib.request.Request(
    url,
    headers={"X-API-Key": RM_API_KEY}
)
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        print(f"Status 200 OK! Total rows returned: {len(data)}")
        print(f"{'RECORD ID':14} | {'CONDITION':17} | {'DISPOSITION':14} | {'ID CHECK'}")
        print("-" * 70)
        for r in data:
            rec = r.get("record_id", "")
            cond = r.get("amazon_condition", "")
            disp = r.get("operator_disposition", "")
            id_c = (r.get("sold_vs_returned_id_check") or "")[:25]
            print(f"{rec:14} | {cond:17} | {disp:14} | {id_c}")
except Exception as e:
    print("Error:", e)
