# F-013 · Several placeholder cards cannot support a positive identity verdict

- **Date:** 2026-09-25
- **Source:** synthetic product cards for puzzle, protein and bottle SKUs; §11.9 C06
- **Status:** handled conservatively
- **GitHub issue:** not yet mirrored (issues are not enabled on the fork)

## Finding

The puzzle, protein and bottle cards expose only packaging or accessory critical features and have no barcode
values. Under the C06 box-swap defence, those features cannot prove that the returned product body matches the
sold unit.

## Impact

Identity cannot honestly be `yes` for these placeholders; treating the packaging as proof would defeat the
box-swap control.

## Our handling

The deterministic pipeline keeps those cases unverified. Replacement cards require real evidence, including at
least two critical product-body features or a barcode value, plus real reference photos before a model session is
allowed.
