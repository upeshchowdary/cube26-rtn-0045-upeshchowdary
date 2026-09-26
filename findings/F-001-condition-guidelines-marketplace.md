# F-001 · Authoritative condition guidelines: target marketplace login barrier and substitute source

- **Date:** 2026-09-25
- **Source:** build prompt Part 1 §1.7, §8.3, §26
- **Status:** handled via ADR-006 (unverified substitute data architecture)
- **GitHub issue:** not yet mirrored (pending issues enabled on fork)

## Finding
- The target marketplace for the Returns track is presumed to be `amazon.in` (matching Indian Rupee `INR` currency conventions across the prompt and data).
- Amazon's official Seller Central condition guideline documentation for `amazon.in` (and `amazon.com`) requires an authenticated Seller Central login and cannot be retrieved publicly or reproducibly without credentials.
- The only publicly retrievable authoritative PDF published by Amazon is the UK condition guidelines document: `https://m.media-amazon.com/images/G/02/rainier/help/legal/Condition_Guidelines_EN_161220.pdf` (17 pages, dated 16 Dec 2020; SHA-256 `342a3dc2e9cbdec5467ec03417630f1e2466ac3bbf6d7a6965caf871a35e2718`).

## Impact
- Rubrics extracted from the UK document carry UK-specific provisions (e.g. CE / UKCA markings, UK standard three-pin plugs, Great Britain vs. Northern Ireland protocol rules).
- Applying UK rules to `amazon.in` products without qualification would misrepresent regulatory compliance checks (e.g. BIS certification in India vs CE/UKCA in the UK).
- If the organizers or sellers provide `amazon.in` guidelines later, switching sources without breaking data integrity is essential.

## Our handling
1. **Explicit substitute status:** Every condition rubric extracted from the UK document is explicitly marked `source_marketplace: amazon.co.uk`, `applies_to_marketplace: amazon.in`, and `verification_status: unverified_substitute`.
2. **Data-driven switching:** Snapshot selection is controlled entirely by data in `reference/rubrics/active.yaml` (`category_key -> snapshot_id`). Code never hardcodes snapshot IDs. Switching to verified `amazon.in` guidelines requires only adding new snapshot files and updating `active.yaml`.
3. **Traceability:** Every inspection and evidence record records the exact `snapshot_id` and `verification_status` used at evaluation time.
4. **Separation of concerns:** Regional electrical conformity marks (UKCA/CE) are extracted in rubrics but category policies delineate between `amazon_guideline`, `business_policy`, and `assumption`.
5. **Decisions:** Documented in `decisions/ADR-006-rubric-source-substitute.md`. Question to organizers logged in `build-log.md` under Open Questions (OQ-2).
