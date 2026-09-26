# F-012 · Literal R09 conflicts with the disposition monotonicity invariant

- **Date:** 2026-09-25
- **Source:** build prompt §12.2 R09 and §12.3 monotonicity invariant
- **Status:** handled and tested
- **GitHub issue:** not yet mirrored (issues are not enabled on the fork)

## Finding

Taken literally, R09 can route an item with a replaceable missing essential part to `refurbish` while the same
complete item would route to `liquidate` under R14. That makes a worse inspection outcome more valuable than a
better one, violating §12.3 monotonicity.

## Our handling

R09 applies only if the complete item's own route is `refurbish` or better. Otherwise R10 determines the salvage
route. The prompt's headphones example is unaffected because complete opened electronics already route through
R11 to `refurbish`. The resolution and property test live in `disposition/engine.py` and `test_disposition.py`.
