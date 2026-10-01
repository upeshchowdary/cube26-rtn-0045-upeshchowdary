# RETURN MANAGER — COMPLETE CONTINUATION PROMPT (everything pending, in one place)

This single prompt replaces every earlier resume, speed-up, Stage 3, portability and handover
prompt. It covers everything that was started, paused, skipped for time or never done, plus a few
new items found along the way. Work through the phases **in order**.

It works on either laptop (the original one or a friend's, after a hand-over via git bundle).

---

## 0. READ FIRST

### 0.1 Where things are

All paths are relative to the **workspace folder**: the folder containing the repo checkout and
`audit-report.md` in a local development workspace.

| What | Where |
|---|---|
| Repo | `./cube26-rtn-0045-upeshchowdary` |
| Progress log (source of truth for what's done) | `./audit-report.md`. Read all of it before starting. Sections: audit items, `## Stage 1 fixes`, `## Stage 2 fixes`, `## Stage 3`, `## Redesign` (last entry: R5c-pause), `## Redesign findings (backend, for later)` |
| Redesign spec | `./Return_Manager_Sydon_Redesign_Prompt.md` (Parts A–K). If it's missing, stop and ask me |
| Product facts for the UI | `ui/FACTS.md` in the repo. If it contradicts the redesign spec, FACTS.md wins |
| Original build spec, rules, findings | the repo's build prompt, `CLAUDE.md`, `build-log.md`, `decisions/`, `findings/` |
| Screenshots and perf traces | `./redesign-screenshots/` |

### 0.2 Known state at the time of writing (verify, don't assume)

- **Branch `upeshchowdary`:** 15 local commits ahead of `origin/upeshchowdary` (Stage 1, Stage 2,
  pre-commit fixes, the request-cap fix, the chain-test fix). Latest is `e34f26f`. Nothing pushed.
- **Branch `ui-sydon`** (redesign, created from `e34f26f`):
  - Step 1 FACTS.md (`040d69f`), Step 2 foundation, Step 3 landing page (`d7367b1`), Step 4 app
    screens (`36936fb`), code-split (`14ea1cc`), 3D hero (`5243951`): committed.
  - 3D evidence scene: built and tuned to budget (off-thread texture decode, R3F resize fix,
    `compileAsync`, 1.5× textures for DPR ≤ 1.5, preload one screen ahead). Its lifecycle checks
    are NOT done. It may be a WIP commit or uncommitted.
- **Stage 3:** step 1.0 done. Steps 1.1–1.3 not done. **0 of 10 approved Gemini requests spent.**
- **Portability pass:** not started.
- **Machine setup:** WSL Ubuntu with Docker Engine and Supabase CLI. `%USERPROFILE%\.wslconfig`
  has memory=4GB, swap=2GB. `/etc/wsl.conf` has `generateResolvConf=false` with a hand-written
  resolv.conf. vmIdleTimeout keeps the VM but not the distro alive, so a keep-alive session is
  needed.
- **Stray file to report** (not in the repo): `D:\Git\tmp_head.json`. Tell me it's there; I'll
  delete it.

### 0.3 Operating rules (all phases)

**Sessions and processes**
- **Only ONE Claude Code session** may work on this repo. Before starting, list running
  `claude`, `node`, `python` and `dev check` processes. If another Claude Code session is using
  this repo, STOP and tell me. Don't touch it yourself.
- **One heavy process at a time:** dev check, Vite dev server, preview server, Chrome, Supabase
  start and big builds never overlap. Stop each one before starting the next.

**Memory and power**
- Report Windows and WSL available memory at every checkpoint.
- If either drops under **1 GB**, stop the heavy process, write a pause entry and tell me.
- Remind me to keep the charger plugged in before any long step.

**Network drops**
- Commit after every step (WIP commits are fine inside long steps).
- After every commit, append an entry to `audit-report.md` under the phase's heading: commit hash,
  what changed, checks run, memory, and what comes next.
- If you're resuming, find the last entry and continue from there.

**Git**
- No push. No force-push. No history rewrite.
- Merge locally only in Phase 2, and only after my approval.
- Never commit to the wrong branch: check `git branch --show-current` before every commit.

**Safety and truth**
- No secrets printed or written anywhere: keys, JWTs, passwords, service-role key, `.env`
  values. For `.env`, report names, presence and length only.
- Don't edit organiser-owned files; `scripts/check_boundary.py` decides which they are.
- Nothing under `eval/sealed/` or `eval/labels/` is ever opened.
- **Gemini:** only in Phase 3, at most **10 requests total**, enforced by `--max-requests`. No other
  phase calls Gemini. Unit tests use replay only.
- Never skip, delete, loosen or xfail a test to make it pass. If a test encoded wrong behaviour,
  replace it with a test of the right behaviour and say which test and why.

**Product truth** (applies to code, UI copy, docs and reports)
- **Dispositions:** Restock, Refurbish, Liquidate, Dispose only. `pending_review` is a status.
  `wrong_product` and `return_to_vendor` don't exist.
- **Grades:** exactly the five Amazon grades. `observed_state` values exactly as the code defines
  them.
- **Who does what:** the model reports observations, rules produce verdicts, and the rules engine
  computes the recommendation. Auto-approve applies only to rows needing no review or sign-off,
  and its threshold is not calibrated. Otherwise a person confirms or overrides, and dispose or
  high-value routes need a second person.
- **Identity:** product identity (visual features + barcode) and "sold vs returned records" are
  separate checks, always labelled separately.
- **Forbidden wording:** immutable (except the prescribed "not immutable"), tamper-proof,
  blockchain, fraud/fraudulent, counterfeit as a verdict, production-/enterprise-grade, real-time,
  guaranteed, 100% accurate, certified, Amazon-approved/-compliant, state-of-the-art, "the AI
  decides", "no damage" (use "no damage observed in the provided photos"), "works perfectly".
- **Numbers:** every number shown or written is real, with method and n, or labelled
  "Sample data". Measure performance; never claim it.

### 0.4 The only points where you wait for me

| Gate | When | I reply |
|---|---|---|
| **G1** | After the redesign is finished (end of Phase 1): start only the preview server, give me the URL, and tell me what to look at | `done looking` (plus any changes) |
| **G2** | Before merging ui-sydon into upeshchowdary (Phase 2) | `approve merge` |
| **G3** | Stage 3 UI check with a real job (Phase 3.4) | `done looking` |
| Stop-and-ask | Memory under 1 GB; another session found; git corruption; anything needing credentials, money or more than 10 Gemini requests; a genuine requirement conflict | — |

Everywhere else, keep going without waiting.

---

## PHASE 0 — State check and recovery

1. **Git health:**
   - `git status` on both branches;
   - leftover `.git/index.lock` or ref locks (remove only if no git process is running);
   - `git fsck --no-dangling`. If it reports real corruption, STOP.
2. **Progress:**
   - `git log --oneline origin/upeshchowdary..upeshchowdary`;
   - `git log --oneline upeshchowdary..ui-sydon`;
   - the last entries of every section in `audit-report.md`.
   Print a table of every item in this prompt marked done / partly done / not started.
3. **Uncommitted work:** for each changed file, say whether it's complete or cut off. Complete
   work that passes tsc and the build gets committed as the step it belongs to. Cut-off edits are
   restored and that part is redone.
4. **Dependencies:** `npm ls --depth=0` in `ui/` agrees with package.json and the lockfile (run
   `npm ci` if not). `uv sync` state in `agent/`.
5. **Machine:**
   - memory;
   - WSL, Docker and Supabase up with the DB intact: 11 migrations, reference data present
     (run `returns-manager reference load` if missing);
   - keep-alive running;
   - the local ports answer from Windows.
6. **New laptop?** If this is a hand-over machine (no WSL/Docker/Supabase yet, or no `.env`), do
   **Phase 5.3's setup steps first**, logging every step that failed or needed knowledge not in
   the docs. That log feeds the portability pass. The `.env` comes from `.env.example` plus this
   person's OWN Gemini key; never copy another person's `.env`.
7. Report the stray `D:\Git\tmp_head.json` if it still exists. Write a `## Continuation` entry in
   `audit-report.md`.

---

## PHASE 1 — Finish the redesign (branch `ui-sydon`), with nothing skipped

This restores everything earlier cut for time. The full redesign spec (Parts A–K) applies.

**1.1 Evidence scene: finish from R5c-pause.**
- Steady-state check (`perf3d.js`) for the evidence and hero scenes: fps while scrolling,
  off-screen pause, heap flat after scrolling down and up three times.
- Dispose check: geometries, materials and textures are freed on unmount.
- Visual re-check of both scenes after the shared-code refactor (hero included).
- Measure in a **visible, GPU-backed Chrome window**. Headless numbers don't count for 3D.
- Budget, unthrottled: steady ~60 fps (or matching the display), no main-thread task over 50 ms
  from scene code, flat heap. Report the 4× numbers for reference.
- Tune before removing anything. Commit and write the R5c entry.

**1.2 Decision stack as TRUE 3D (restored; no longer 2.5D-only).** Part H of the redesign spec,
F11 layout:
- Evidence → Identity → Condition → Recommendation → Operator review → Final disposition. The
  layers separate in depth on scroll, then align. Controls become active at "Operator review".
- Only the real four dispositions and real values or labelled sample data.
- Reuse the shared `three/common.ts` / `SceneCanvas.tsx` utilities and every lesson from the
  evidence scene: off-thread decode, R3F `resize={{ scroll: false, debounce: 0 }}`,
  `compileAsync`, DPR-matched textures, preload one screen ahead, frameloop demand, dispose,
  DPR ≤ 2.
- It gets its own lazy chunk. The 2.5D version is built too, as the fallback (reduced motion,
  mobile, no WebGL, low-power), and shows while loading.
- Same budget and measurement as 1.1. If it still fails after tuning, keep the 2.5D version and
  record why. Commit.

**1.3 First-load layout task.** Investigate and fix the ~300–400 ms Layout task during initial
landing load (Level 2 page, present with 3D off). Likely candidates: pinned ScrollTrigger setup,
forced reflows from measuring many elements, or font swap. Measure before and after. Commit.

**1.4 Full screenshot set (restored).**
- Every landing section and every app screen, at 1440px and 390px, one screen per batch, closing
  Chrome between batches.
- Save to `./redesign-screenshots/final/`.
- Compare against the Sydon screenshots and Part K, and fix what's off.

**1.5 Full Part K final check.**
- The comparison list, including every 3D scene.
- The truth check: forbidden-word grep of `ui/src` and new docs (zero hits), plus
  `wrong_product` / `return_to_vendor` (zero hits).
- The behaviour check: scroll forward/stop/back/fast, pinned sections release, resize, route
  changes, reduced motion, mobile widths, clean console.
- Bundle sizes (initial landing, and each lazy chunk).

**1.6 Full dev check WITH the database** (restored): Supabase up, nothing else heavy running.
Every gate except the boundary check's branch-name rule, which fails by design on ui-sydon.
Confirm with `git diff 36936fb -- agent/` whether the backend changed.

**1.7 Redesign report** appended under `## Redesign`: commits, measurements with method, bundle
sizes, screenshots, and what you tuned or chose not to build, with reasons.

→ **G1:** start only the preview server, give me the URL and what to look at (hero 3D, evidence 3D,
decision 3D, mobile width, reduced motion). Wait for `done looking`, apply my changes, commit.

---

## PHASE 2 — Merge the redesign (local only)

→ **G2:** show me `git log --oneline upeshchowdary..ui-sydon` and a `git diff --stat` summary.
Wait for `approve merge`.

1. Switch to `upeshchowdary`. Merge `ui-sydon` with a normal merge commit (no squash, no rebase),
   so history stays readable.
2. Resolve conflicts (unlikely: ui-sydon branched from its tip) by keeping both sides' intent.
   Report every conflict.
3. Run the **full dev check with the DB, including the boundary check, which must now pass
   completely on upeshchowdary.** Also tsc and `npm run build`.
4. Keep the `ui-sydon` branch (don't delete it). Commit and report.

---

## PHASE 3 — Stage 3 remainder (branch `upeshchowdary`)

**3.1 Wikimedia 403 fix** (already diagnosed: the User-Agent header).
- Set the batch image fetcher's User-Agent to a policy-compliant one that names the public repo
  URL as contact. No personal email or names.
- Add a test that the header is sent. Commit.
- Confirm with ONE plain HTTP fetch of each smoke-run photo URL (no Gemini) that each returns 200.

**3.2 Quota ledger analysis** (explain now, fix in Phase 4).
- The ledger showed 16/30 "used" from DB-test reservations. Can that block real requests?
- Does the batch path record into the ledger at all?

**3.3 Live smoke run: 10 Gemini requests total, the only Gemini use in this whole prompt.**
- Say how many have been spent before starting (expected 0). Check quota status.
- Rows (reuse the existing manifests; never invent rows or photos): PHONE-01 complete, PHONE-02
  missing parts, AIR-02 wrong item, PHONE-04 damaged.
  - PHONE-02 has no returned photo, so it can't test missing-part detection. Say so. If another
    real row with a returned photo shows a missing part, use it instead, within the same cap.
- Run as an API batch job, so the per-row detail exists for the UI. If you also run a CLI pass,
  the caps must sum to ≤ 10.
- Report per row: operator_disposition, agent_disposition, auto_approved, photo_identity_match,
  parts_missing, value_source, failure_reason, and requests used.
- Confirm:
  - the wrong item is `pending_review` + `wrong_item_returned` (never `wrong_product`);
  - no confidence or "source: model" appears without a real response;
  - no invented CSV defaults appear.
- If the cap or quota is hit, stop that step and report what you have.

**3.4 UI check** → **G3.**
- Start the API (and worker if needed) and the UI with the smoke-run job, one process at a time
  where possible.
- Give me the URLs and exactly which screens and rows to open, starting with AIR-02 on the
  Inspection screen (comparison panel, wrong-item handling, restyled design).
- Wait for `done looking`, then stop the servers.

---

## PHASE 4 — Backend to-dos (branch `upeshchowdary`)

One commit each, with tests.

1. **Batch overrides are data.**
   - Every batch-row accept, override, retake or review stores: the original value, the new value,
     reason code, reason text, actor and timestamp. Never only the new value.
   - The CSV export and row detail show the original next to the override.
2. **Batch decision trail.**
   - Make each job's decision log append-only and hash-chained, using the same RFC 8785 +
     SHA-256 scheme as `chain/`: each entry holds the previous entry's hash, plus a verify
     function, with a tamper test.
   - If job decisions can be linked to the DB event chain cleanly, do that instead and say which
     you chose.
   - The UI and docs must describe it accurately: tamper-evident, not immutable.
3. **Quota ledger** (from 3.2):
   - DB tests must not use up the real daily budget. Use isolated test model IDs or clean up test
     reservations.
   - The batch path reserves and records real requests in the ledger, so `quota status` tells the
     truth.
   - Add tests.
4. **"Auto-disapproved" is UI-only.** Either move it to a backend-computed flag (from
   `wrong_item_flag` and the review reasons, with a test), or rename it in the UI to what it is
   ("Possible wrong item: needs review"). Never a disposition.
5. **Reused-photo check for batch (F-020).**
   - Perceptual-hash every fetched photo within a job (imagehash is already a dependency).
   - Flag rows that share a near-identical returned photo with `possible_reused_photo` as a review
     reason. It's a flag, never a verdict. Add a test.
6. **Contract examples (C2):**
   - Write the 13 missing `contract/examples/` records required by §14.1: every official scenario
     plus X01, X06, X07, X11, including an uncertain case, a provisional requires_review case and a
     null-recommendation case.
   - Each one is labelled synthetic in its content, validates against
     `evidence-record.v1.schema.json`, and has a route that agrees with the engine.
   - Add a test that validates all of them.
7. **Auto-approve threshold:** it can't be calibrated without labelled eval data. Keep the "not yet
   calibrated" label everywhere. Make sure the threshold-sweep tooling (§21.5) works on a dev
   mini-set and is ready for the real eval. No invented operating point.

---

## PHASE 5 — Portability: runs on any laptop (branch `upeshchowdary`)

**5.1 Find every machine-specific thing.** Grep the repo (excluding .git, node_modules, .venv)
for:
- absolute paths: `C:\`, `c:/`, `D:\`, local macOS/Linux home directories, and local-root path examples from a contributor's checkout;
- usernames and personal names: `<user>`, `UPESH`, `ROHIT`, etc.;
- hardcoded hosts or ports that should come from config;
- Windows-only commands (PowerShell, `.bat`, `cmd /c`) with no cross-platform equivalent.
List every hit with file:line in the report BEFORE changing anything.

**5.2 Fix them.**
- Paths: relative to the repo root (`Path(__file__).resolve()` / `REPO_ROOT` in Python;
  `import.meta` / env vars in the UI).
- Person- or machine-specific values go into `.env` / `.env.example`, with a comment for each.
- Cross-platform (Python or npm) versions of anything PowerShell-only.
- Add a test that fails if an absolute user path or personal username appears in tracked files.
  Allow-list organiser files.

**5.3 One clear setup path.** Rewrite the setup sections of `agent/README.md`, `ARCHITECTURE.md`
and `CLAUDE.md` (never the organiser's root README).
- Prerequisites with versions:
  - Python 3.12, uv, Node LTS, Supabase CLI;
  - Docker: Desktop on Windows/macOS, or Engine in WSL/Linux;
  - rough RAM needs (the stack plus a browser; ~4 GB WSL cap on a 16 GB laptop).
- Exact commands in order:
  1. clone (or clone from a bundle, then set the origin URL);
  2. `.env` from `.env.example` plus your own Gemini key;
  3. `uv sync`, then `npm install`;
  4. `supabase start`;
  5. `db migrate`, `seed demo`, **`reference load`**;
  6. `keys create`;
  7. start the API, worker and UI;
  8. `dev check`.
- Known problems and fixes:
  - WSL DNS failure (`generateResolvConf=false` + resolv.conf);
  - WSL idle shutdown (vmIdleTimeout keeps the VM, not the distro; keep a session open);
  - low memory (`.wslconfig` cap, close heavy apps, restart);
  - Wikimedia 403 (User-Agent);
  - never run two Claude Code sessions or two dev servers on one repo;
  - headless Chrome is not valid for WebGL performance.
- Optional: one cross-platform setup script that runs the post-install steps and stops with a
  clear message when a prerequisite is missing.

**5.4 Prove it on a fresh clone.**
- Stop the main Supabase stack first; only one stack at a time.
- Clone into a new, differently named folder outside the repo. Follow ONLY the docs:
  - once on Windows;
  - once in WSL Ubuntu.
  Copy only the Gemini key.
- In each: the full dev check with the DB, then start the UI and open it.
- Log every failure or step needing knowledge not in the docs. Fix it in the ORIGINAL repo,
  re-clone, and repeat until both runs are clean.
- Then stop the clone's stack, delete the clones and restart the main stack.
- If a friend's laptop already did setup in Phase 0.6, include its log here.

---

## PHASE 6 — Documentation matches reality

Update `MASTER_PROJECT_PROMPT.md`, `ARCHITECTURE.md`, `agent/README.md` and `CLAUDE.md` (not
organiser files):
- final test counts with DB tests, with date and the exact command;
- smoke-run results, labelled "smoke run, n=4 (or actual n), not an eval";
- the redesign: what exists, including which scenes are true 3D and which 2.5D, and measured
  performance with method;
- Phase 4's new behaviour (override trail, decision chain, ledger, reused-photo flag, contract
  examples);
- what is honestly NOT done: the real eval (C1), threshold calibration, the Recovery-pod contract
  agreement, anything else open;
- a rule table regenerated from `disposition/engine.py`;
- a forbidden-word grep over all docs, showing zero hits.
Commit.

---

## PHASE 7 — Eval readiness kit (C1). Prepare only; humans do the labelling.

The real eval (≥ 50 unseen units, two independent labellers, human–human agreement first) is the
highest-scored section and needs people. Prepare everything they need, **without creating,
reading or sealing any eval data yourself:**

1. `eval/README.md`, a step-by-step protocol:
   - capturing 2–3 photos per unit;
   - the coverage quotas `eval seal` enforces (every scenario S01–S10 ≥ 3; poor lighting ≥ 10;
     oblique ≥ 10; slight blur ≥ 8; genuinely ambiguous ≥ 8; ≥ 15 products not seen in dev);
   - how to fill `conditions.csv` at capture time;
   - labelling rules (independent, before any agent run, official vocabulary);
   - then `eval seal`, `eval run`, `eval report`.
2. Blank templates in a non-sealed folder (e.g. `eval/templates/`):
   - `orders.csv`, `conditions.csv`, `labeller_a.csv`, `labeller_b.csv`, with the exact headers
     from §8.10 and zero data rows;
   - a printable one-page capture checklist and labelling sheet.
3. A quota plan: requests needed for 50 units (judgment + audit) versus the real daily limits, and
   how many days that takes on the free tier. It's an estimate, labelled as one.
4. Verify the tooling end to end on `--dev-mini` only. Commit.

---

## PHASE 8 — Final verification and hand-over package

1. With nothing else running, on `upeshchowdary`:
   - the full dev check with the DB (0 skipped);
   - `scripts/check_boundary.py`;
   - the portability test;
   - `tsc` and `npm run build`;
   - gitleaks over `origin/upeshchowdary..HEAD`.
   Show all outputs.
2. Create a hand-over bundle outside the repo: `git bundle create ../handoff.bundle --all` and
   `git bundle verify`.
3. **Final report** in `audit-report.md` under `## Final`, also shown to me:
   - every phase with its commits;
   - measurements with method;
   - test counts;
   - Gemini requests used (≤ 10);
   - `git log --oneline origin/upeshchowdary..upeshchowdary`.
4. **What only humans can do next**, as a checklist:
   - review, then push (coordinate with Upesh, the repo owner);
   - rotate any Gemini key that was ever pasted in chat;
   - delete the stray `D:\Git\tmp_head.json`;
   - run the eval with two labellers using the Phase 7 kit;
   - agree the contract with the Recovery pod.
Stop. Don't push.
