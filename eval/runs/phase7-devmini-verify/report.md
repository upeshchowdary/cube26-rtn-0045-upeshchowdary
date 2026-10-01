# Eval report

- **Run:** `phase7-devmini-verify` (DEV-MINI (tooling check only - not a reported eval result))
- **Units evaluated:** 8 / 8 requested
- **Seed:** 20260925
- **Started / completed:** 2026-09-30T18:36:18.059289+00:00 / 2026-09-30T18:36:26.209375+00:00
- **Actual requests / cost:** 0 / $0.0120

## Agreement (§21.3)

| Check | Pairing | Statistic | Value | n | 95% CI | Method |
|---|---|---|---|---|---|---|
| identity | labeller_a_vs_b/raw_agreement | raw_agreement | 1.000 | 8 | [1.000, 1.000] | fraction exact match; 95% bootstrap CI |
| identity | labeller_a_vs_b/cohen_kappa | cohen_kappa | nan | 8 | [nan, nan] | sklearn.metrics.cohen_kappa_score; 95% bootstrap CI, 1000 resamples, seeded (undefined: only one class present in this pairing - total agreement) |
| identity | model_vs_gold/raw_agreement | raw_agreement | 0.625 | 8 | [0.250, 1.000] | fraction exact match; 95% bootstrap CI |
| identity | model_vs_gold/cohen_kappa | cohen_kappa | 0.000 | 8 | [0.000, 0.000] | sklearn.metrics.cohen_kappa_score; 95% bootstrap CI, 1000 resamples, seeded |
| completeness | labeller_a_vs_b/raw_agreement | raw_agreement | 1.000 | 8 | [1.000, 1.000] | fraction exact match; 95% bootstrap CI |
| completeness | labeller_a_vs_b/cohen_kappa | cohen_kappa | nan | 8 | [nan, nan] | sklearn.metrics.cohen_kappa_score; 95% bootstrap CI, 1000 resamples, seeded (undefined: only one class present in this pairing - total agreement) |
| completeness | model_vs_gold/raw_agreement | raw_agreement | 1.000 | 8 | [1.000, 1.000] | fraction exact match; 95% bootstrap CI |
| completeness | model_vs_gold/cohen_kappa | cohen_kappa | nan | 8 | [nan, nan] | sklearn.metrics.cohen_kappa_score; 95% bootstrap CI, 1000 resamples, seeded (undefined: only one class present in this pairing - total agreement) |
| condition | labeller_a_vs_b/raw_agreement | raw_agreement | 1.000 | 8 | [1.000, 1.000] | fraction exact match; 95% bootstrap CI |
| condition | labeller_a_vs_b/cohen_kappa | cohen_kappa | nan | 8 | [nan, nan] | sklearn.metrics.cohen_kappa_score; 95% bootstrap CI, 1000 resamples, seeded (undefined: only one class present in this pairing - total agreement) |
| condition | labeller_a_vs_b/weighted_kappa_quadratic | weighted_kappa_quadratic | nan | 8 | [nan, nan] | sklearn.metrics.cohen_kappa_score(weights='quadratic'); 95% bootstrap CI, 1000 resamples, seeded (undefined: only one class present in this pairing - total agreement) |
| condition | model_vs_gold/raw_agreement | raw_agreement | 0.625 | 8 | [0.250, 1.000] | fraction exact match; 95% bootstrap CI |
| condition | model_vs_gold/cohen_kappa | cohen_kappa | 0.000 | 8 | [0.000, 0.000] | sklearn.metrics.cohen_kappa_score; 95% bootstrap CI, 1000 resamples, seeded |
| condition | model_vs_gold/weighted_kappa_quadratic | weighted_kappa_quadratic | 0.000 | 8 | [0.000, 0.000] | sklearn.metrics.cohen_kappa_score(weights='quadratic'); 95% bootstrap CI, 1000 resamples, seeded |
| unit_presence | labeller_a_vs_b/raw_agreement | raw_agreement | 1.000 | 8 | [1.000, 1.000] | fraction exact match; 95% bootstrap CI |
| unit_presence | labeller_a_vs_b/cohen_kappa | cohen_kappa | nan | 8 | [nan, nan] | sklearn.metrics.cohen_kappa_score; 95% bootstrap CI, 1000 resamples, seeded (undefined: only one class present in this pairing - total agreement) |
| unit_presence | model_vs_gold/raw_agreement | raw_agreement | 1.000 | 8 | [1.000, 1.000] | fraction exact match; 95% bootstrap CI |
| unit_presence | model_vs_gold/cohen_kappa | cohen_kappa | nan | 8 | [nan, nan] | sklearn.metrics.cohen_kappa_score; 95% bootstrap CI, 1000 resamples, seeded (undefined: only one class present in this pairing - total agreement) |

## Selective prediction (§21.2)

| Check | Strict accuracy | Coverage | Selective accuracy | Unnecessary-uncertain rate | n |
|---|---|---|---|---|---|
| identity | 62.5% | 62.5% | 100.0% | 37.5% | 8 |
| completeness | 100.0% | 100.0% | 100.0% | 0.0% | 8 |
| condition | 62.5% | 100.0% | 62.5% | 0.0% | 8 |

## Per-check false positives / false negatives (§21.1)

| Check | Positive means | FP | FP means | FN (dangerous) | FN means | n |
|---|---|---|---|---|---|---|
| unit_presence | item not returned (empty/non-product) | 0 | flagged empty, but the item was there | 0 | empty box passed as a real return | 8 |
| identity | wrong item (identity_match = no) | 0 | flagged wrong, but it was right | 0 | wrong item passed as right | 8 |
| completeness | incomplete (>=1 component missing) | 0 | said missing, but complete | 0 | said complete, but something was missing | 8 |
| condition | N/A (ordinal; ranked by CONDITION_GRADE_ORDER) | 0 | under-grade: system says worse than gold | 3 | over-grade: system says better than gold (customer gets less than listed) | 8 |

## Disposition confusion matrix (§21.1)

| gold \ agent | dispose | liquidate | null | refurbish | restock |
|---|---|---|---|---|---|
| dispose | 0 | 0 | 0 | 0 | 0 |
| liquidate | 0 | 0 | 0 | 0 | 0 |
| null | 0 | 0 | 0 | 0 | 0 |
| refurbish | 0 | 0 | 0 | 0 | 0 |
| restock | 0 | 0 | 0 | 0 | 8 |

- `restock` when gold != restock (dangerous): **0**
- `dispose` when gold was recoverable (value loss): **0**
- n = 8

## Failure modes (§21.4)

| Mode | Count | Example unit_ids |
|---|---|---|
| barcode_failure | 2 | DEV-MINI-03, DEV-MINI-06 |
| poor_lighting | 1 | DEV-MINI-00 |

## Per-unit summary (§21.9)

- **identity:** agree 5, disagree 0, uncertain 3 (n=8)
- **completeness:** agree 8, disagree 0, uncertain 0 (n=8)
- **condition:** agree 5, disagree 3, uncertain 0 (n=8)
- **disposition:** agree 8, disagree 0, uncertain 0 (n=8)

## Per-unit table (§21.9)

Disagreements first, then uncertain, then agreements.

| unit_id | scenario_codes | lighting | angle | blur | ambiguity | product_seen_in_dev | human_a_identity | human_b_identity | gold_identity | agent_identity | identity_agree | human_a_completeness | human_b_completeness | gold_completeness | agent_completeness | completeness_agree | gold_parts_missing | agent_parts_missing | human_a_condition | human_b_condition | gold_condition | agent_condition | condition_agree | condition_error | gold_disposition | agent_disposition | agent_requires_review | disposition_agree | agent_uncertain_checks | uncertainty_reasons | latency_ms | cost_usd | failure_mode | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DEV-MINI-00 | S01 | poor | oblique | none | genuinely_ambiguous | yes | yes | yes | yes | uncertain | agent_uncertain | complete | complete | complete | complete | yes |  |  | Used - Good | Used - Good | Used - Good | Used - Very Good | no | over_grade_by_1 | restock | restock | yes | yes | identity | photo_quality | 1500 | 0.001500 | poor_lighting |  |
| DEV-MINI-03 | S04 | normal | square | none | clear | no | yes | yes | yes | uncertain | agent_uncertain | complete | complete | complete | complete | yes |  |  | Used - Good | Used - Good | Used - Good | Used - Very Good | no | over_grade_by_1 | restock | restock | yes | yes | identity | photo_quality | 1650 | 0.001500 | barcode_failure |  |
| DEV-MINI-06 | S07 | normal | square | none | genuinely_ambiguous | yes | yes | yes | yes | uncertain | agent_uncertain | complete | complete | complete | complete | yes |  |  | Used - Good | Used - Good | Used - Good | Used - Very Good | no | over_grade_by_1 | restock | restock | yes | yes | identity | photo_quality | 1800 | 0.001500 | barcode_failure |  |
| DEV-MINI-01 | S02 | normal | square | slight | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Good | Used - Good | Used - Good | Used - Good | yes | exact | restock | restock | no | yes |  |  | 1550 | 0.001500 |  |  |
| DEV-MINI-02 | S03 | normal | square | none | clear | yes | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Good | Used - Good | Used - Good | Used - Good | yes | exact | restock | restock | no | yes |  |  | 1600 | 0.001500 |  |  |
| DEV-MINI-04 | S05 | poor | square | slight | clear | yes | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Good | Used - Good | Used - Good | Used - Good | yes | exact | restock | restock | no | yes |  |  | 1700 | 0.001500 |  |  |
| DEV-MINI-05 | S06 | normal | oblique | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Good | Used - Good | Used - Good | Used - Good | yes | exact | restock | restock | no | yes |  |  | 1750 | 0.001500 |  |  |
| DEV-MINI-07 | S08 | normal | square | slight | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Good | Used - Good | Used - Good | Used - Good | yes | exact | restock | restock | no | yes |  |  | 1850 | 0.001500 |  |  |
