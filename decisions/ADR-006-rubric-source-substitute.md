# ADR-006 Rubric source substitute and data-driven marketplace adaptation
Status: accepted
Owner: upeshchowdary
Date: 2026-09-25
Revisit by: 2026-10-01, or immediately upon organizer guidance regarding target marketplace documentation
Reversibility: reversible — switching rubric snapshot source is a pure configuration/data change

## Decision (one paragraph: what)

We adopt Amazon UK's published 17-page condition guidelines PDF (`Condition_Guidelines_EN_161220.pdf`, 16 Dec 2020) as an explicit **`unverified_substitute`** condition rubric source for our target marketplace (`amazon.in`), because official seller documentation for `amazon.in` is locked behind an authenticated Seller Central portal and is not publicly retrievable. All extracted rubrics are stamped with `source_marketplace: amazon.co.uk`, `applies_to_marketplace: amazon.in`, and `verification_status: unverified_substitute`. The application binds category keys to rubric snapshots entirely through configuration (`reference/rubrics/active.yaml`), ensuring that substituting a verified `amazon.in` source in the future requires only registering the new snapshot and updating the mapping, with zero application code changes. Every inspection decision and evidence record records the exact `snapshot_id` and verification status under which the unit was evaluated.

## Why

- **Public reproducibility without credentials**: An external automated evaluation or peer audit must be able to verify condition rules against authentic, public source documents. The UK PDF is hosted at an open media-amazon URL with a verified SHA-256 (`342a3dc2e9cbdec5467ec03417630f1e2466ac3bbf6d7a6965caf871a35e2718`).
- **Intellectual honesty and transparency**: Grading against UK rules for an Indian marketplace without disclosure would be misleading (e.g. CE/UKCA marking and UK 3-pin plugs vs BIS and Indian plug standards). Explicitly tagging every snapshot and output with `unverified_substitute` maintains strict compliance with the competition's honesty rules.
- **Strict decoupling of rules and code**: The LLM prompt and deterministic rules engine must never invent or memorize condition definitions (Engineering Rule 5: "Look authoritative rules up"). By loading condition text dynamically from hashed rubric snapshots, the system preserves provenance.
- **Seamless data-only migration**: By isolating snapshot selection into `active.yaml`, if the organizers provide an official `amazon.in` condition document or export, the system can ingest it into `reference/rubrics/amazon.in/<category>.yaml` and switch the active pointer without breaking schema, database migrations, or code logic.

## Rejected alternatives (and why)

- **Scraping or fabricating amazon.in condition text**: Generating synthetic condition guidelines or guessing would violate Engineering Rule 5 and the competition's anti-hallucination rules.
- **Hardcoding condition definitions in python code**: Hardcoded strings prevent traceability to source documents, break content hashing, and make marketplace adaptation impossible without code redeployment.
- **Silently presenting amazon.co.uk rules as amazon.in rules**: Omitting the substitute status would misrepresent regulatory requirements (CE/UKCA vs BIS) and fail the honesty criteria (§24, forbidden language).

## Consequences

- All rubric snapshots must carry `verification_status: unverified_substitute` until an authentic `amazon.in` source is verified.
- The evaluation report must disclose that cosmetic grading was performed against the UK substitute guidelines and discuss any potential divergence.
- The `reference/policies/<marketplace>/<category>.yaml` files must clearly differentiate between guidelines derived from Amazon's text (`source_type: amazon_guideline`), seller business policies (`source_type: business_policy`), and operational assumptions (`source_type: assumption`).
