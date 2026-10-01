# Eval quota plan (estimate only)

This document is an estimate for planning only. It does not claim a verified run on a real free-tier key.

## Assumptions
- Minimum real eval target: 50 unseen units.
- The project target is a mean of at most about 1.2 requests per inspected unit.
- The decision path on the free tier is constrained by the daily request limit per model.
- The project prompt notes that the judgment model sees about 18 usable requests/day on a real free-tier key.

## Estimated judgment load
- 50 units × ~1.2 requests/unit = about 60 judgment requests.
- 60 judgment requests / 18 requests/day ≈ 3.3 days.

That is the planning estimate for the judgment pass alone.

## Audit/review load
- The audit pass runs on a different model and is intentionally conservative.
- The project prompt also expects an additional audit requirement beyond the main judgment model.
- For planning, assume the audit adds at least 1 more day of model time depending on the actual free-tier cap and the selected audit model.

## Planning estimate
A realistic planning estimate is therefore:
- about 3 to 4 days of judgment quota
- plus audit/cross-check time on the second model
- total free-tier planning estimate: roughly 4 to 6 days, assuming no major quota surprises and no many additional round trips

This is not a promise. The actual number depends on the real AI Studio daily caps, the final request-per-inspection mean, and whether the audit is run on every unit or only on a subset.
