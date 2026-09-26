# ADR-007 Hash-chain scope and honest claim wording
Status: accepted
Owner: upeshchowdary
Date: 2026-09-25
Revisit by: 2026-11-01, or if an external blockchain or timestamping witness is integrated
Reversibility: reversible

## Decision (one paragraph: what)

We implement a two-level cryptographic hash-chain for evidence integrity: a per-unit event chain (`rm.unit_events`, linked sequentially by `prev_event_hash`) and a per-org audit ledger (`rm.org_ledger`, tracking evidence finalization, supersession, and critical control events). Payloads are canonicalized using RFC 8785 JSON Canonicalization Scheme (JCS) before hashing with SHA-256. Ledger heads are periodically exported to an append-only JSONL anchor file (`anchors/ledger-anchors.jsonl`) committed to public git. We strictly mandate the following honest claim wording across all documentation, API responses, UI text, and contracts:

> *"Tamper-evident within this database: modification, reordering, insertion or deletion of events or records is detected unless an attacker rewrites the entire chain consistently. Not immutable. Weakly anchored: ledger heads are published in public git commits; history before an anchor cannot be silently rewritten without breaking the anchor."*

We strictly forbid claiming that our system is "tamper-proof", "immutable", or a "blockchain".

## Why

- **Tamper Evidence vs Immutability**: No software running on a standard relational database can claim physical immutability against a database superuser who can edit disk sectors or table rows directly. However, by chaining each event's hash to its predecessor and canonicalizing payloads with RFC 8785, any alteration, reordering, insertion, or deletion of a past event breaks the hash linkage and is detected by `returns-manager chain verify`.
- **Two-tier Design (Per-Unit Chains + Per-Org Ledger)**: Units arrive asynchronously and concurrently. Maintaining a single monolithic event chain across an entire organization creates write contention and lock serialisation bottlenecks. A per-unit hash chain serialises only concurrent events for that single unit (`FOR UPDATE` on `unit_chain_heads`), while the per-org ledger records only milestone events (record finalization and supersession).
- **Public Git Anchoring**: Publishing periodic ledger heads into a public Git repository provides an external witness. Once a commit is published and observed, history before that commit cannot be rewritten in the database without producing a mismatch against the recorded anchor in Git.
- **Accurate and Honest Engineering Claims**: Track 04 judging rewards technical accuracy and honesty. Misrepresenting a database hash-chain as "blockchain-secured" or "tamper-proof" is misleading and violates the forbidden-language rules (§24).

## Rejected alternatives (and why)

- **Decentralized public blockchain (Ethereum, Solana)**: Excessive latency (seconds to minutes for finality), gas transaction fees, and operational complexity that conflict with free-tier and low-latency commerce requirements.
- **Single global hash chain**: High database lock contention on high-throughput intake; concurrent returns for different units would contend for the same lock.
- **Uncanonicalized JSON hashing (`json.dumps`)**: Key ordering variations, whitespace differences, and floating-point representations break hash stability across different platforms, languages, or Python versions. RFC 8785 JCS guarantees deterministic canonical UTF-8 bytes.
- **No external anchoring**: Leaving hashes purely inside the database means a privileged DBA could re-calculate the entire hash chain from an altered state; external git anchoring closes this loophole for historical entries.

## Consequences

- All unit events must pass through `returns_manager.chain.append.append_event` and evidence documents through `finalize_record` / `supersede_record`.
- Payloads must never contain native floating-point numbers (`canonical_bytes` rejects floats to enforce integer/minor currency units).
- The verifier `run_verify_unit` and `run_verify_org` are exposed via CLI (`returns-manager chain verify`), API (`/api/v1/units/{unit_id}/chain/verification`), and the cross-pod contract.
- The honest claim sentence is embedded in all evidence records and API verification responses.
