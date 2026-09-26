# F-007 · Where the build lives: build prompt vs. repository RULES

- **Date:** 2026-09-25
- **Source:** build prompt Part 1 §0.3, §1.1, §4.2, §23 P0 vs. repository `RULES.md` R2/R3, `GITHUB-GUIDE.md` §1, §6
- **Status:** handled (human decision recorded in `build-log.md`, 2026-09-25)
- **GitHub issue:** not yet mirrored (pending; see build log)

## Contradiction
- The build prompt says: build only inside `submissions/<github-username>/`, name the branch after the
  username, and pass the organiser CI guard (`.github/scripts/submission-guard.sh`), which fails any PR that
  changes a file outside that folder.
- The repository's own `RULES.md` (R2, R3) and `GITHUB-GUIDE.md` say Round 2 is built in the participant's
  **own fork**: participants "do not need to create `submissions/<your-github-username>/`" or open a PR into
  the organiser repository, and "your final structure should be clear and easy to run". The README's
  submission list also asks for `README.md` and `ARCHITECTURE.md`, which the `submissions/` layout does
  not place at the fork root.
- The CI guard still exists in the repository and still describes the old, PR-based workflow.

## Impact
Where files go and which boundary check applies. Following the prompt literally would hide the build
inside a subfolder of a fork whose root README describes the organisers' problem statement, not this build.

## Our handling
- The repository rules are the more recent and authoritative source for Round 2; the human chose the
  **fork-root layout**.
- The CI guard's *intent* is kept locally: `scripts/check_boundary.py` checks that the branch is named after
  the username (never `main`) and that no change touches an organiser-owned path (`.github/`, `data/`,
  `submissions/`, root `.gitignore`, `README.md`, `RULES.md`, `GITHUB-GUIDE.md`), plus forbidden files and
  the 5 MB cap.
- The root `README.md` / `ARCHITECTURE.md` needed for submission will be handled as an explicit, logged
  decision near the end of the build.
