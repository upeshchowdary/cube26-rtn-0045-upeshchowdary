# Eval readiness kit (Phase 7)

This folder is a preparation kit only. It does not contain the sealed eval set, the human labels, or any model-tuned data. The repo is explicitly designed so that humans do the labelling and the CLI only reads the finished sealed data during `eval run`.

Important guardrails:
- Never open or edit anything under `eval/sealed/` or `eval/labels/` during setup.
- Never use real eval data for prompt tuning or debugging.
- The real evaluation is the highest-scoring section of the project and requires 50 unseen units and two independent labellers.
- This kit prepares the human workflow; it does not create the final eval itself.

## 1) Capture workflow for each unit

For each eval unit:
1. Assign a unique unit ID in the format `UNIT-EVAL-###`.
2. Capture 2 to 3 photos of the same item from different angles, with the same item and SKU visible in each. For ambiguous cases, include the relevant detail that drives the ambiguity.
3. Capture the order metadata in `eval/templates/orders.csv`.
4. Capture the condition metadata in `eval/templates/conditions.csv` at the time the unit is photographed.
5. Store files locally in the human-managed sealed work area, not in this repo until the team is ready to seal them.

Recommended capture checklist:
- item is present, empty box, or wrong item inside
- front/side/back photos or 2-3 useful views
- visible accessory and box condition
- any lighting or blur issue
- whether the product was seen in dev fixtures or category seen in dev

## 2) Coverage quotas the seal step enforces

The real eval set must meet the minimum quotas before `eval seal` passes. The rules enforced by the tool are:
- every scenario `S01` through `S10` has at least 3 units
- `lighting == poor` has at least 10 units
- `angle == oblique` has at least 10 units
- `blur == slight` has at least 8 units
- `ambiguity == genuinely_ambiguous` has at least 8 units
- at least 15 units have `product_seen_in_dev = yes`

These are capture tags from the sealed metadata, not labels of the final answer. They should be written before labelling and never changed after the set is sealed without an explicit documented explanation.

## 3) Filling `conditions.csv` at capture time

Use the blank file in `eval/templates/conditions.csv` and fill one row per unit with:
- `unit_id`
- `scenario_codes` as a `;`-separated list from the official scenario set
- `lighting`: `good|poor`
- `angle`: `standard|oblique`
- `blur`: `none|slight`
- `ambiguity`: `clear|genuinely_ambiguous`
- `product_seen_in_dev`: `yes|no`
- `category_seen_in_dev`: `yes|no`
- `notes`: free-form capture notes

Do not label the correct answer here. The data is only the capture condition and item-context metadata.

## 4) Independent labelling rules

Each unit must be labelled twice, independently, before the agent is run:
- Labeller A and Labeller B label the same unit without consulting each other.
- They do this before any agent inference on that unit.
- They use the official vocabulary from the product contract:
  - `identity_match`: `yes|no|uncertain`
  - `unit_presence`: `product_present|empty_packaging|non_product_contents|uncertain`
  - `completeness`: `complete|incomplete|uncertain`
  - `parts_missing`: `;`-separated list or blank
  - `parts_uncertain`: `;`-separated list or blank
  - `observed_state`: official state wording
  - `amazon_condition`: Amazon condition label or `uncertain`
  - `disposition`: `restock|refurbish|liquidate|dispose` or blank with reason if no recommendation is possible
- Per-check verdict columns must use `PASS|FAIL|UNCERTAIN` with the fixed keys:
  - `v_unit_presence`
  - `v_identity`
  - `v_completeness`
  - `v_condition_grade`
  - `v_relistable_as_is`

The blank templates live in `eval/templates/labeller_a.csv` and `eval/templates/labeller_b.csv`.

## 5) Seal, run, and report the eval

Once the humans have created the sealed set and label files, the project workflow is:

1. Seal the set:
   - `uv run returns-manager eval seal --units-dir <path-to-sealed-unit-metadata>`
2. Run the eval with the sealed data:
   - `uv run returns-manager eval run --run-id <run_name>`
3. Review the generated report:
   - `uv run returns-manager eval report --run-id <run_name>`

For a dev-only end-to-end smoke check that is not a real eval, use the repository's built-in dev-mini path:
- `uv run returns-manager eval run --run-id phase7-devmini --dev-mini --confirm-spend`

## 6) Current repo state

The repository is currently prepared for the workflow but does not contain a real sealed eval set or real human labels. That is intentional. The codebase already validates the tooling on `--dev-mini`, while the human and operational work remains for the actual evaluation.
