# Return Manager — Sydon-Style Redesign: Master Prompt (design + motion, merged)

This one prompt replaces two earlier documents: the Sydon-style master prompt and the advanced
3D/motion addendum. Where they disagreed, this version decides. Where their examples
contradicted the real Return Manager system, the examples have been corrected here.

**The target:**
**Sydon's design language + Return Manager's actual product + purposeful motion.**
Not Sydon's copy. Not a technology demo. Not a generic SaaS template.

Anyone familiar with sydon.ai should recognise the same design language at a glance. Once they
read it, the content must clearly be Return Manager and only Return Manager.

---

## PART A — HOW TO WORK

### A1. Ground rules

- Work on a new branch `ui-sydon`, created from the current HEAD of `upeshchowdary`. Never push.
  Commit after each build step with a clear message.
- **Frontend only.** Preserve the existing backend, APIs, database, routes, data and every working
  feature. You may add a backend field only when the UI genuinely needs it and it doesn't exist
  yet, and it must come with a test.
- Keep these green after every step:
  - `returns-manager dev check` (in `agent/`);
  - `tsc -p tsconfig.app.json`;
  - `npm run build` (in `ui/`).
  Never skip, delete or weaken a test.
- Keep the existing cinematic landing assets on disk. This branch replaces the landing page's
  design; it does not delete the old assets.
- **Reference material:**
  - Study https://sydon.ai/ live.
  - Study the Sydon screenshots in `<SCREENSHOTS_FOLDER>`.
  - If a reference video is provided, extract frames with ffmpeg (for example 2 fps; more for
    fast transitions) and study the frames.
  - Never claim to have watched a video you couldn't open.
  - Recreate the *observed* behaviour. Don't claim Sydon uses any particular library unless
    you have public evidence of it.
- **Dependencies:**
  - Inspect `ui/package.json` first. Don't reinstall what exists.
  - Install only what a step needs, from official packages: `gsap`, `lenis`, and only in step 5,
    `three`, `@react-three/fiber`, `@react-three/drei`, `postprocessing`.
  - Match versions to the project's React major version. Never force-install over peer
    conflicts.
  - Don't clone example repositories. Don't copy code from random GitHub projects.

### A2. Build order and approval gates

| Step | Work | Gate |
|---|---|---|
| 1 | Write `ui/FACTS.md` (A3) | **Stop and show me.** Nothing else until I approve |
| 2 | Design foundation: tokens, type, header, buttons, cards, FAQ, footer, back-to-top (Parts C, D) | Commit |
| 3 | Landing page sections with Level 1 + Level 2 motion (Parts E, F) | **Show me** (screenshots at 1440px and 390px) |
| 4 | Restyle the existing app screens into the same design system (Part G) | **Show me** |
| 5 | Level 3 true 3D, only where it clearly improves the story (Part H) | **Only after I approve**, and I may skip it |
| 6 | Performance, accessibility, mobile, and the final checklist (Parts I, K) | Report |

### A3. Step 1 — FACTS.md (the source of truth for all content)

Write `ui/FACTS.md` **from the code and data, not from this prompt.** It must list:

1. Every real route and screen (`ui/src/App.tsx` and the screens folder). These become the
   navigation.
2. The disposition values the engine can output (`agent/src/returns_manager/disposition/engine.py`).
3. The Amazon condition grades (rubrics, `judgment/grading.py`).
4. The `observed_state` values.
5. The `review_reasons` and `no_recommendation_reason` codes. These are the only "exceptions"
   the site may show.
6. The chain event types (`chain/event_types.py`). These are the only audit-timeline steps
   the site may show.
7. The metrics the dashboard actually computes (`ui/src/lib/derive.ts`, `/metrics/summary`).
8. Whether a prose "AI summary" exists anywhere in batch output or row detail. The explainer
   agent exists. Record whether the batch pipeline writes a summary; if it doesn't, the site must
   not show one as if it were routine output.
9. What the auto-approve rule actually requires (`batch/auto_approve.py`), and that its threshold
   is not yet calibrated.
10. Two or three real rows from an existing batch job, for use in mockups: product, SKU, parts,
    condition, disposition and photo references. Choose one clean row and one with a missing part
    or review reason.
11. Real product photos available in the repo that can legally be shown, with their paths.

**If this prompt ever conflicts with FACTS.md, FACTS.md wins.**

---

## PART B — TRUTH RULES (read before writing any copy or mockup)

These correct errors in the earlier prompts. They are not optional.

1. **Four dispositions only:** Restock, Refurbish, Liquidate, Dispose.
   - "Pending review" is a *status*, not a disposition.
   - Never show "Return to vendor", "Needs review", "Wrong product" or any other value as a
     disposition.
2. **Mockups must agree with the rules engine.**
   - Any condition-and-route pair shown must be one `disposition/engine.py` would produce under
     current parameters.
   - Example: Used - Good does **not** restock under the current `restock_used_grades`.
   - Use a real row from FACTS.md, or label the mockup "Sample data".
3. **Condition vocabulary.**
   - Amazon grades exactly as written: New, Used - Like New, Used - Very Good, Used - Good,
     Used - Acceptable.
   - Observed state is the official value (e.g. "Signs of use"), never free text like
     "Used - minor wear".
4. **Identity has two different checks. Never merge them.**
   - *Product identity* is the model's visual feature checks on the product body, plus barcode
     evidence, fused by deterministic rules. It can be Yes / No / Uncertain.
   - *Sold vs returned records* is the paperwork comparison of SKU / ASIN / IDs.
   - Show both, clearly labelled. Never animate a record-to-record SKU/ASIN match as
     "IDENTITY VERIFIED" on its own: packaging and paperwork don't prove what's inside the box,
     and the same ASIN can appear on unrelated products.
5. **Who does what.** This is the story, and it must be accurate:
   - The model *reports observations* from the photos.
   - Deterministic rules turn them into verdicts: identity, completeness, condition.
   - The rules engine *computes the recommended disposition*.
   - Auto-approve can finalize a row only when the engine needs neither review nor sign-off and
     every check clears the (not yet calibrated) confidence threshold.
   - Otherwise an operator confirms or overrides, and dispose or high-value routes need a second
     person's sign-off.
   - **Never say or imply "the AI decides".**
6. **Uncertain is a real outcome.** Show it as a first-class state with its reason, never as a
   failure or a low-confidence pass.
7. **Honest wording.** Use these phrasings:
   - "No damage observed in the provided photos", never "no damage".
   - "Not visible in the provided photos", never "missing" when it simply wasn't seen.
   - "Tamper-evident (hash-chained), not immutable", never "immutable", "tamper-proof" or
     "blockchain".
   - "Functional test not performed", never "works perfectly".
   - "Graded against Amazon's published condition guidelines (unverified substitute snapshot)",
     never "certified" or "Amazon-approved".
8. **No invented numbers.** Every metric, count, percentage or timing is either read from real
   data or labelled "Sample data". No performance claims (FPS, latency) unless you measured them.
9. **No fake presence.** No logos, testimonials, integrations, customer counts, company details
   or contact information that don't exist in the project.
10. **Navigation, exceptions, audit steps and FAQ answers use FACTS.md values only.**

---

## PART C — DESIGN LANGUAGE

### C1. Character

Extremely clean, premium, minimal, technical and spacious. White-dominant, near-black type,
Sydon-like blue accent, subtle cyan, very restrained shadows, thin borders, occasional soft glass
surfaces, elegant micro-interactions, and subtle movement throughout.

Avoid:
- generic dashboard templates;
- neon or cyberpunk styling;
- giant gradients;
- excessive rounding;
- random 3D objects.

It should feel like a funded commercial product, not a student project.

### C2. Colour tokens

| Token | Value | Use |
|---|---|---|
| `--bg` | `#FFFFFF` | Dominant background |
| `--text` | `#0B0F19` | Primary text |
| `--text-2` | `#6B7280` | Secondary text |
| `--text-3` | `#9CA3AF` | Muted text |
| `--blue` | `#2563EB` | Primary accent, CTAs, active and verified states |
| `--blue-2` | `#3B82F6` | Secondary blue, gradients in headline accents |
| `--blue-50` | `#EFF6FF` | Light blue surface |
| `--blue-25` | `#F5F9FF` | Very light blue section |
| `--cyan` | `#22D3EE` | Subtle accent, particles |
| `--glow` | `#EEF2FF` | Atmospheric glow |
| `--border` | `#E5E7EB` | Thin borders |
| `--success` | a restrained green | Success states only |
| `--warning` | a restrained amber | Warnings and review flags only |
| `--danger` | a restrained red | Real exceptions only |

The overall impression is **white + black + blue + a little cyan.** Blue is an accent, never the
whole background. Radial glows stay faint, e.g.
`radial-gradient(circle at center, rgba(37,99,235,0.05), transparent 60%)`.

### C3. Typography

- One modern sans-serif throughout: Inter or Geist, or another equally clean geometric sans. No
  decorative, futuristic, overly rounded or serif fonts in the interface.
- Sizes (desktop):
  - hero 64–80px;
  - section headings 48–64px;
  - subheadings 18–22px;
  - body 16–18px;
  - labels 11–13px (uppercase with controlled letter-spacing for eyebrows).
- Headlines are bold, tight and high-contrast, with a **blue accent phrase** as in Sydon's hero
  ("Run your whole store with **agents that act, not just alert.**").
- Vary the scale between sections. Not everything is huge.

### C4. Layout and whitespace

- Max content width 1200–1400px. Hero text is narrow enough for strong typography. Body copy
  never runs excessively wide.
- 120–180px vertical spacing between major sections on desktop. Sections read like chapters.
  Never fill every pixel.
- Every section follows: small eyebrow → large headline → short supporting copy → a visual.
- **Vary the layouts** across the page: centred, left/right split, large product visual, sticky
  text beside a scrolling visual, timeline, comparison, cards, FAQ.
- Mostly white. Occasionally use a very light blue section, a faint radial glow, or light grey.
  Use a dark section only if it genuinely helps.

### C5. Surfaces, depth, glass, shadow

- Cards: white, 1px `--border`, 8–16px radius, very soft shadow, generous internal spacing.
- Depth comes mainly from 2.5D layering (Part F3), not from heavy shadows or blur.
- Glass/transparency: sparingly, only on floating layers over the hero or dashboard preview.
  Never on dense text.
- A consistent shadow scale (e.g. `sm` / `md` / `lg`), all soft and low-opacity. No glow
  explosions.

---

## PART D — COMPONENTS

### D1. Header

- White, compact, thin bottom border, subtle backdrop blur when sticky. Height may shrink slightly
  on scroll.
- **Left:** Return Manager wordmark.
- **Centre:** the landing page's section anchors, plus links to the real app screens from
  FACTS.md. Never Pricing, Plans, Billing or Subscriptions.
- **Right:** primary CTA "Open Return Manager →", leading into the existing app.
- Nav hover: a small colour shift toward blue, an optional thin underline, 150–250ms, nothing
  dramatic.

### D2. Buttons

- Primary: blue background, white text, rounded rectangle (not a giant pill), subtle shadow.
  - Hover: slightly darker, lifts 1–2px, shadow grows, arrow slides 2–4px right.
  - Active: slightly compressed.
- Secondary: white with thin border, same motion.
- **Magnetic pull** (a button drifting a few px toward the cursor) is Level 3. Only add it in
  step 5, and keep it very subtle.

### D3. Cards

Hover: border slightly darker, shadow slightly larger, lift 2–4px, optional blue accent, inner icon
nudges. 200–300ms with the standard easing. No large scaling.

### D4. FAQ ("Common questions")

- Small eyebrow and heading.
- Items are horizontal rounded rectangles showing: number, question, chevron.
- Click: smooth height expansion (300–450ms), chevron rotates 180°, subtle background change.
  Fully keyboard accessible (`button`, `aria-expanded`, `aria-controls`).
- Questions, with answers written strictly from FACTS.md:
  1. What is Return Manager?
  2. What does it check on a returned item?
  3. How does it tell whether the right product came back?
  4. What happens when a part isn't visible in the photos?
  5. How is condition graded?
  6. Does the AI decide what happens to the item? *(No: the rules engine computes a
     recommendation from the observations, and a person confirms or overrides it.)*
  7. When does a return need a person to review or sign off?
  8. Is every decision recorded?
  Only include a question if the real system supports an accurate answer.

### D5. Footer

- Clean editorial composition with a large statement, e.g. "Every return. Every inspection. One
  clear decision."
- Then a short "Get in touch" line, *only* if real contact information exists in the project, then
  the wordmark, copyright and small navigation.
- No pricing links, no invented company details.
- Motion: the statement reveals on scroll with subtle kinetic typography. Nothing else animates.

### D6. Back-to-top button

Small circular blue button, fixed bottom-right, subtle shadow, upward chevron. Appears after
scrolling (opacity 0→1, scale 0.8→1, 200–300ms). Click scrolls smoothly to the top through Lenis.

### D7. Loading state

Minimal: a white background, the small Return Manager mark, and a faint blue motion. No big loading
screen. If 3D is added, it loads lazily behind a static fallback (H4).

---

## PART E — PAGE STRUCTURE AND CONTENT

The story: **problem → system → workflow → product → evidence → decision → trail → FAQ → CTA.**
Include a section only if it communicates real functionality. Copy is short, confident, direct,
technical and slightly editorial, like Sydon's. No "revolutionary platform" language.

Headlines you can use, as long as every claim stays true:
- "Returns are decisions, not just transactions."
- "Know what came back. Know what belongs. Know what happens next."
- "Evidence first. Decision second."
- "Every inspection leaves a trail."
- "Turn returned units into clear outcomes."

### E1. Hero

- **Eyebrow pill:** THE RETURN INSPECTION WORKFLOW (or similar; no platform claims beyond the
  product).
- **Headline:** "Turn every return into a **clear decision.**", with the accent phrase in blue.
- **Supporting copy** (keep it this accurate): "Return Manager checks a returned item's identity,
  parts and condition from photos, records the evidence, and computes one of four dispositions for
  your team to confirm."
- **CTAs:** "Open Return Manager →" (primary), "See how it works" (secondary, scrolls to the
  workflow).
- **Background:** the particle field (F6).
- **Hero visual:** a layered 2.5D composition of real Return Manager UI cards built from one
  FACTS.md row:
  - Return record: return ID, unit, order, SKU, ASIN.
  - Product identity: verdict, e.g. "2 of 2 critical features matched".
  - Sold vs returned records.
  - Parts: e.g. "2 of 2 present".
  - Condition: the real Amazon grade.
  - Evidence: photo count and thumbnails.
  - Disposition: the engine's route plus its rule ID.
  Label everything "Sample data" unless it's a real row.
- Never "Start free", "Free trial" or prices.

### E2. The problem

"Returns aren't just refunds. They're decisions." Then short lines:
- A returned unit has to be identified.
- Its order has to be matched.
- Its parts have to be accounted for.
- Its condition has to be graded.
- The evidence has to be kept.
- Then someone decides what happens next.

End with: "Today that varies by operator and shift, and the reasoning often isn't recorded." This
comes straight from the problem statement, so it's allowed.

### E3. The workflow ("The Return Journey")

The signature concept connecting the whole page:

**Return received → Product identity → Parts → Condition → Evidence → Recommendation (rules
engine) → Human review → Disposition → Audit trail.**

- It builds as the user scrolls: only "Return received" is visible at first, then each step
  appears and connects with a thin blue progress line.
- Vertical on mobile, vertical or horizontal on desktop.
- The line is the visual thread reused in later sections (F7).

### E4. Identity

- Headline: "Know it's the right product, not just the right box."
- Visual, two labelled parts:
  1. **Product identity:** a returned photo beside the reference photo. Distinguishing-feature
     checks light up one by one (match / mismatch / not visible), then the fused verdict appears
     (Yes / No / Uncertain).
  2. **Sold vs returned records:** ordered vs returned SKU / ASIN / IDs converge. A thin scanning
     line passes. The result is "Records match" or "Records don't match".
- If a barcode was decoded, add a subtle scanner beam (F8) over the barcode crop.
- The final state states *both* results, never one standing in for the other.

### E5. Parts / accessories

- Headline: "Everything that should be in the box."
- Expected parts from the real parts list vs what was observed: present / missing / not visible
  (uncertain).
- Use the real missing-part scenario from FACTS.md if there is one; that's the problem
  statement's own example ("USB cable missing → Completeness: FAIL").
- Components separate slightly on scroll, each gets checked, then they settle back.
- Only components in the real data model.

### E6. Condition and evidence

- Headline: "Evidence first. Decision second."
- The real return photos in a floating stack (F9). As the user scrolls, the stack spreads, the
  active photo comes forward, and the condition panel appears beside it:
  - observed state;
  - defects observed (type, severity, location);
  - Amazon grade and the matched rubric phrase;
  - "Functional test not performed".
- Never fabricate photos. If no suitable real photo exists, use the app's existing placeholder
  and say so.

### E7. From observations to a recommendation

(This replaces the earlier prompts' "AI section".)

- Headline, e.g.: "The model observes. The rules decide. You confirm."
- Visual (F10): input nodes (Identity, Parts, Condition, Evidence) connect with thin lines into a
  **Rules engine** node, which outputs the recommendation card:
  - route;
  - rule ID;
  - any review reasons;
  - whether sign-off is required.
- No glowing AI orb. No fake "AI typing".
- If FACTS.md shows no prose summary exists, don't invent one. Show the structured check results
  building in stages.

### E8. Human review and disposition

- Headline: "The final call stays with your team."
- A decision stack (F11): Evidence → Recommendation → Operator review → Final disposition. At
  "Operator review" the decision controls become active: Accept / Override (with reason).
- Explain, briefly and accurately:
  - when auto-approve applies (clean rows only; threshold not yet calibrated);
  - when a second person must sign off (dispose; high-value non-restock);
  - that overrides are recorded with the original value, the new value and the reason.
- Show the four dispositions as the only possible outcomes.

### E9. Exceptions

- Headline, e.g.: "When something doesn't add up, it's flagged, not guessed."
- Show only real codes from FACTS.md (e.g. identity mismatch, essential part uncertain,
  condition uncertain, possible reused photo), with human-readable labels.
- Use restrained amber. Red only for real exceptions. The page must never look red.

### E10. Audit trail

- Headline: "Every inspection leaves a trail."
- A clean vertical timeline of real event types from FACTS.md. Each node shows timestamp, actor,
  action and result.
- A blue progress line travels down it on scroll: the current node activates and earlier nodes
  stay visible.
- One line of honest wording: "Tamper-evident within the database (hash-chained); not immutable."

### E11. Dashboard preview

- A high-quality preview of the *real* app (the restyled screens from Part G), rendered as normal
  HTML/React inside a 2.5D composition (F12).
- Floating metric cards show only real metrics from FACTS.md, with real values or "Sample data".
  Nothing the app doesn't have: no Billing, Pricing, Inventory, PPC or other intelligence modules.

### E12. FAQ, final CTA, footer

- FAQ per D4.
- Final CTA: a large kinetic headline, then "Open Return Manager →", leading into the app.
- Footer per D5.

---

## PART F — MOTION SYSTEM (Level 1 and Level 2; build in step 3)

### F1. Architecture

- One central `ui/src/motion/tokens.ts` holds every duration, easing, distance, stagger, parallax
  strength and interaction strength. No hard-coded animation values scattered through components.
- **Exactly one Lenis instance**, driven by the GSAP ticker (`gsap.ticker.add`, `lagSmoothing(0)`,
  ScrollTrigger updated from Lenis). No second smooth-scroll system, no competing
  `requestAnimationFrame` loops, no raw wheel handlers.
- Reusable hooks and components: `useReveal`, `useParallax`, `useScrollProgress`, `usePointer`
  (one global, normalised −1…1 pointer state with damping), `<Reveal>`, `<KineticHeadline>`,
  `<ParticleField>`, `<Depth>` (2.5D layer).
- Kill every ScrollTrigger, ticker callback and listener when a component unmounts. No leaks, and
  no duplicate triggers after route changes.
- Never call React `setState` per animation frame. Use refs, GSAP and canvas for high-frequency
  values.

### F2. Motion tokens

| Token | Value |
|---|---|
| Fast interaction | 150–220ms |
| Hover | 200–300ms |
| UI transition / FAQ | 300–450ms |
| Page transition | 400–700ms |
| Section reveal | 700–1000ms |
| Large product movement / cinematic | 900–1600ms |
| Background drift | 5–20s continuous |
| Stagger | 0.05–0.12s |
| Easing | `cubic-bezier(0.22, 1, 0.36, 1)` / GSAP `power3.out` (`power2.out` for small elements) |
| Floating elements | gentle ease-in-out |
| Linear | only for continuous particles and backgrounds |

No random one-off durations. Everything should feel like one designed system.

### F3. Three levels of motion

- **Level 1, micro (everywhere):** buttons, arrows, nav hover, card lift, FAQ, icons, text
  highlight. Plain CSS/GSAP. Lightweight.
- **Level 2, 2.5D (most of the "premium depth"):** layered cards, perspective,
  `translateZ` / `rotateX` / `rotateY`, shadow depth, parallax, floating UI, overlapping
  interface layers. Faster and cleaner than WebGL, so use it by default.
- **Level 3, true 3D (Part H):** only in step 5, only with approval, only for at most 2–4 major
  moments. Never for navigation, FAQ, tables, the working dashboard or the footer.

### F4. Section reveals

- Order: eyebrow (opacity 0→1, y 20→0) → heading (y 35→0) → paragraph → visual (opacity 0→1,
  scale 0.97→1, optional blur 8→0px).
- Staggered, 700–1000ms, triggered once as the section enters.
- Never pop a whole section in at once.

### F5. Kinetic typography

Word-by-word reveals (clip-path + translateY + opacity, small stagger) for the hero headline,
major section headlines and the final CTA only, e.g. "RETURNS / ARE / DECISIONS." Never animate
body text, and never animate every sentence.

### F6. Hero particle field

- **Canvas**, not DOM elements. One rAF loop driven by the GSAP ticker. Paused when the hero is
  off-screen (IntersectionObserver) or the tab is hidden.
- Tiny, sparse, soft, low-opacity particles: mostly blue/cyan with a few muted neutrals. They
  sit mostly around the edges, keeping the centre clean for the headline.
- Motion: slow drift, slight rotation, occasional fade in/out. No fireworks, no confetti bursts.
- Pointer response: particles near the cursor move a few px away, then ease back with damping.
- Scroll velocity: fast scrolling may speed up drift slightly, then everything settles. Never
  distort text. No motion blur.
- Density drops on mobile. Movement is disabled under reduced motion (a static field is fine).
- Tune density and speed against the Sydon frames and screenshots.

### F7. Scroll storytelling

- **Scroll-linked hero:** as scrolling begins, the hero visual moves up, scales slightly, tilts a
  few degrees and becomes less dominant, while the next section enters (ScrollTrigger scrub).
- **Pinning:** use for 1–2 story sections at most (e.g. E3 and E7): sticky text on one side, the
  visual progressing on the other, with scroll progress mapped 0→1 onto the section's timeline.
  Pinned regions must release cleanly and must never trap the user.
- **The blue progress line** (from E3) carries through workflow, audit trail and decision
  sections, tying the page together.
- **Section-to-section continuity:** where natural, an element from one section (e.g. the
  recommendation card) carries into the next instead of every section being isolated. Keep it
  subtle.
- **Parallax layers:** background ~0.1×, decorative ~0.2×, product ~0.05×, text normal. No motion
  sickness.

### F8. Barcode scanner effect

A thin blue beam sweeps the barcode crop once. When it crosses the barcode, a few data particles
activate, then the decoded result appears ("Barcode matches ordered SKU", "Barcode unreadable", or
whatever the data says). Subtle, never a laser show.

### F9. Evidence stack

Real photos in a controlled 3D-feeling stack (CSS 3D is enough): front, slightly behind, slightly
rotated, further behind. Scroll spreads them out and brings the active one forward. The pointer adds
slight perspective. No literal orbiting planets.

### F10. Observation-to-recommendation synthesis

- Thin animated connections from the input nodes to the rules engine node. Small data particles
  travel along them as the user scrolls.
- The recommendation card builds in stages from real values:
  identity → parts → condition → recommendation → review / sign-off flags.
- Real UI transitions, no typewriter effect.

### F11. Decision stack

Layers (Evidence, Identity, Condition, Recommendation, Operator review, Final disposition) start
overlapping, separate vertically in depth as the user scrolls, then align into the final card
showing the real disposition. The Operator review layer is where controls become active, which
makes the human decision visibly distinct from machine assistance.

### F12. Dashboard in 2.5D

- Enters with scale 0.94→1, opacity 0→1, y 60→0 and a slight rotateX settling to about 0–4°.
- Then a gentle pointer tilt (≤ 2–3°, damped).
- Metric cards float slightly in front at their own depth and phase.
- Must remain readable at all times.

### F13. Pointer and floating

- Hero visual: 3–8px pointer movement, with foreground, middle and background layers moving
  different amounts.
- Floating: 2–8px vertical and 0.1–0.5° rotation over 4–8s, with independent phases per layer.
  Never synchronised.
- Always interpolate (`current += (target - current) * damping`). Never map raw coordinates.
  No jitter.

### F14. Page transition into the app

"Open Return Manager →" fades or slides (400–700ms) into the existing app, so the landing page
leads straight into the working product. The marketing site sells the workflow; the dashboard runs
it.

---

## PART G — THE APP SCREENS (step 4)

Restyle the existing screens (dashboard, returns list, inspection, new batch upload, and the rest in
FACTS.md) into the same design system: same tokens, type, borders, buttons, cards and status
colours. **Change how they look, not what they show or do.**

- Keep every feature working: batch CSV upload with spend confirmation, live row status,
  accept / override / retake / review decisions, the four-eyes sign-off rules, CSV download, the
  Auto-approved and Auto-disapproved views, and the Inspection comparison panel.
- Raw field names become professional labels, e.g.:
  - ordered_sku → Ordered SKU;
  - identity_match → Identity (sold record);
  - photo_identity_match → Product identity (photo);
  - parts_missing → Missing parts;
  - observed_state → Observed state;
  - operator_disposition → Final disposition;
  - sold_vs_returned_id_check → Sold vs returned records.
- Data is shown as cards, chips, badges, comparison panels, evidence panels and timelines, never
  as a database dump. Tables only where they're genuinely the clearest form.
- Charts: minimal axes, thin lines, subtle blue, plenty of whitespace. Only real metrics.
  `"no data"` stays "no data", never 0.
- Status colours: blue for active/primary, green for success only, amber for warnings and review,
  red for real exceptions only.
- Motion in the app stays at Level 1: hover, row transitions, number transitions. No parallax or
  particles inside working screens.

---

## PART H — LEVEL 3 TRUE 3D (step 5 only, after approval)

Only if it clearly improves the story and doesn't hurt performance. Candidates, in priority order:

1. the hero composition;
2. the evidence / condition stack;
3. the observation-to-recommendation synthesis;
4. the decision stack.

If Level 2 already looks right, stop there.

- **Stack:** Three.js + React Three Fiber + Drei (camera, environment and helpers only as needed)
  + postprocessing.
- **Hero scene:**
  - The layered UI cards from E1, as planes with slight Z separation (~0.15 units apart, tiny, not
    huge).
  - A perspective camera with very slight floating, pointer influence (camera 0.02–0.05 rad,
    cards 0.01–0.03 rad, damped) and scroll influence.
  - It starts almost still. Nothing spins constantly.
- **Lighting:** soft, low-contrast studio lighting (ambient plus one or two soft directional
  lights, or a subtle environment), matching the white/blue palette. No dramatic coloured lights.
- **Post-processing:** barely perceptible. Very subtle bloom, near-invisible vignette and noise,
  no chromatic aberration except, at most, momentarily. If it isn't noticeably better, leave it
  out.
- **Custom cursor and magnetic buttons:** optional, very subtle, desktop only. Disabled on touch
  devices and under reduced motion. The native cursor stays usable.
- **Lazy loading:** load 3D chunks only when their section nears the viewport (dynamic import +
  IntersectionObserver). Show the Level 2 version as the fallback while loading, on low-power
  devices, and under reduced motion.
- **Lifecycle:** pause render loops off-screen (`frameloop="demand"` or equivalent). Dispose
  geometries, materials and textures on unmount. No memory leaks.
- **Assets:** prefer building from UI planes and textures of real screenshots. Use GLB/GLTF only
  if a real model is genuinely needed, optimised and compressed.
- **Never:** rotating cubes, spheres, neon grids, holograms, glowing AI orbs, or game effects.
  The user should think "this feels polished", not "they used Three.js".

---

## PART I — PERFORMANCE, MOBILE, ACCESSIBILITY

### I1. Performance

- Target a steady 60 FPS, with natural support for higher-refresh displays.
- **Measure it** (Chrome Performance trace on the landing page with scroll and pointer input, plus
  a Lighthouse run). Report the numbers and the method. Never just claim them.
- Animate only `transform` and `opacity` (and `filter` sparingly). Never animate width, height,
  top or left.
- Avoid expensive blur on large areas. No DOM particles.
- Cap canvas and WebGL device pixel ratio at `Math.min(devicePixelRatio, 2)`. Size canvases from
  their CSS box. Handle resize.
- Code-split the landing page's heavy parts so the app screens don't load the motion stack.
- Decorative animation must never cause stutter. If it does, reduce it.

### I2. Mobile (recompose, don't shrink)

Compact navigation, stacked cards, scaled hero typography, lighter animation, fewer particles,
vertical workflows, scaled-down product mockups, no horizontal overflow, working touch interactions,
no pointer-only effects. Test at 390px and 768px as well as 1440px.

### I3. Accessibility and reduced motion

- Keyboard navigation everywhere, visible focus states, proper contrast (WCAG AA), ARIA labels,
  and an accessible FAQ and navigation.
- Under `prefers-reduced-motion: reduce`, disable: smooth-scroll inertia, parallax, particle
  movement, pinned or scrubbed sequences, 3D, custom cursor and magnetic effects. Keep simple
  fades. All content must remain reachable and readable.

---

## PART J — NEVER ADD

Unless FACTS.md shows it genuinely exists:

- **Commercial pages:** pricing, subscriptions, plans, billing, checkout, free trial, credit card,
  upgrade buttons.
- **Fake presence:** integrations, testimonials, customer logos, statistics, revenue numbers,
  contact details.
- **Features Return Manager doesn't have:** Amazon seller tools, PPC or ad management, inventory,
  listing, pricing or competitor intelligence, product scouting, keyword tracking, Shopify,
  TikTok Shop. Any AI capability or automation beyond what the code does.
- **Wrong values:** a fifth disposition, or a condition grade outside the five Amazon grades.
- **Forbidden words:** immutable, tamper-proof, blockchain, fraud / fraudulent, counterfeit (as a
  verdict), production-ready / production-grade, enterprise-grade, real-time, guaranteed, 100%
  accurate, certified, Amazon-approved / Amazon-compliant, state-of-the-art, "the AI decides",
  "no damage" (when merely not observed), "works perfectly".

Don't add features, pages or sections just to make the site look bigger. If a capability is
uncertain, inspect the code first.

---

## PART K — FINAL CHECK AND REPORT

1. **Compare against the Sydon reference** (live site, screenshots, video frames) and report on
   each of:
   - header spacing, logo position, navigation spacing;
   - CTA shape;
   - hero typography, hero whitespace, blue accent;
   - particle density and speed;
   - scroll smoothness, section spacing, product mockup scale;
   - card shadows, border thickness, border radius;
   - FAQ design, back-to-top button, footer layout;
   - typography weight, animation timing, pointer interaction;
   - scroll reveals, parallax, mobile behaviour, overall visual density.
   Refine anything that's off, then report again.
2. **Truth check:**
   - Every product claim traces to FACTS.md.
   - Grep `ui/src` and any new docs for every Part J forbidden word and for `wrong_product` /
     `return_to_vendor`, and show zero hits.
   - The one allowed exception is the phrase "not immutable" in the prescribed ADR-007 wording.
   - Every number on screen is either real or labelled "Sample data".
3. **Behaviour check:**
   - Scroll forward, stop, backward and fast; pinned sections release; no stalls.
   - Resize, route changes back and forth, reduced motion on, mobile widths.
   - The browser console is clean.
4. **Engineering check:**
   - `dev check`, `tsc` and `npm run build` are green.
   - Bundle size before and after, with the landing page code-split.
   - The measured performance numbers from I1, with the method.
5. **Report:**
   - the commits;
   - screenshots at 1440px and 390px for each section;
   - what you chose not to build, and why.
   Stop. Don't push.

**The most important rule:** the website must communicate the project that actually exists.
Sydon's polish, Return Manager's truth.
