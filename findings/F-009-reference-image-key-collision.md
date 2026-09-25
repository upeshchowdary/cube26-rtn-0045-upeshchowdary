# F-009 · Reference-image key was not card-scoped

- **Date:** 2026-09-25
- **Source:** migration `0004`, reference-card loader
- **Status:** handled by migration `0006`
- **GitHub issue:** not yet mirrored (issues are not enabled on the fork)

## Finding

`rm.reference_images` used `(org_id, ref_image_id)` as its primary key even though cards commonly use local IDs
such as `ref_front`. Loading multiple cards in one organisation overwrote earlier rows.

## Impact

Only one reference image per organisation could survive, so a return could be compared with an image from the
wrong product card.

## Our handling

Migration `0006` scopes the key by organisation, SKU, card version and image ID. The loader also deactivates
older versions so one active card version remains per SKU.
