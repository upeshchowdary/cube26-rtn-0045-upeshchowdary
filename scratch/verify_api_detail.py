import os
import sys

# The API key comes from the environment; it is never committed (audit A12).
RM_API_KEY = os.environ.get("RM_API_KEY") or sys.exit(
    "RM_API_KEY is not set. Mint a key with `returns-manager keys create` and export RM_API_KEY."
)
import json
import urllib.request

base_url = "http://127.0.0.1:8000/api/v1/batch/jobs/01M3MS62VX5T4C9ZMZPX55PGSF/rows"
headers = {"X-API-Key": RM_API_KEY}

for test_id in ["RTN-EDGE-01", "RTN-PHONE-04", "RTN-AIR-02", "RTN-PHONE-02"]:
    url = f"{base_url}/{test_id}/detail"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        d = json.loads(resp.read().decode())
        dec = d.get("decision", {})
        cond = d.get("condition", {})
        sim = d.get("similarity", {})
        print(f"[{test_id}]")
        print(f"  Recommended Disposition: {dec.get('recommended_disposition')}")
        print(
            f"  Condition: {cond.get('amazon_condition')} (state: {cond.get('state')})"
        )
        print(
            f"  Confidence: {dec.get('confidence')}% (Auto-approved: {dec.get('auto_approved')})"
        )
        print(f"  Rule: {dec.get('rule_id')}")
        print(f"  Reason: {dec.get('reason')}")
        print()
