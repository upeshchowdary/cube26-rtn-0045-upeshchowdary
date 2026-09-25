# F-008 · Placeholder reference images are not usable product evidence

- **Date:** 2026-09-25
- **Source:** `agent/src/returns_manager/reference/seed_cards.py`, `reference/products/*/images`
- **Status:** handled
- **GitHub issue:** not yet mirrored (issues are not enabled on the fork)

## Finding

The supposed reference images were generated truncated 1×1 JPEG placeholders. They did not decode fully and
unrelated SKUs shared identical bytes. Their provenance and brand labels were synthetic rather than product
evidence.

## Impact

Using them for visual identity comparison would make an unsupported model comparison appear evidence-backed.

## Our handling

The images were removed; cards are version 1.1.0 or later with `reference_images: []` and explicit synthetic
placeholder provenance. Validation now requires listed files to exist, decode fully, and not be byte-identical
across SKUs. Until real reference photos and hand-authored cards are supplied, the §11.2a gate skips the model
with `no_product_reference` and routes the return to review.
