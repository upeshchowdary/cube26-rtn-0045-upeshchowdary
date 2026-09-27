# Eval report

- **Run:** `manual-30row-self-labeled-20260927` (sealed eval)
- **Units evaluated:** 30 / 30 requested
- **Seed:** 20260925
- **Started / completed:** 2026-09-27T17:16:59.109019+00:00 / 2026-09-27T17:17:23.245325+00:00
- **Actual requests / cost:** 0 / $0.0000

## Agreement (§21.3)

| Check | Pairing | Statistic | Value | n | 95% CI | Method |
|---|---|---|---|---|---|---|
| identity | labeller_a_vs_b/raw_agreement | raw_agreement | 1.000 | 30 | [1.000, 1.000] | fraction exact match; 95% bootstrap CI |
| identity | labeller_a_vs_b/cohen_kappa | cohen_kappa | 1.000 | 30 | [1.000, 1.000] | sklearn.metrics.cohen_kappa_score; 95% bootstrap CI, 1000 resamples, seeded |
| identity | model_vs_gold/raw_agreement | raw_agreement | 0.900 | 30 | [0.800, 1.000] | fraction exact match; 95% bootstrap CI |
| identity | model_vs_gold/cohen_kappa | cohen_kappa | 0.379 | 30 | [0.000, 0.872] | sklearn.metrics.cohen_kappa_score; 95% bootstrap CI, 1000 resamples, seeded |
| completeness | labeller_a_vs_b/raw_agreement | raw_agreement | 1.000 | 30 | [1.000, 1.000] | fraction exact match; 95% bootstrap CI |
| completeness | labeller_a_vs_b/cohen_kappa | cohen_kappa | 1.000 | 30 | [1.000, 1.000] | sklearn.metrics.cohen_kappa_score; 95% bootstrap CI, 1000 resamples, seeded |
| completeness | model_vs_gold/raw_agreement | raw_agreement | 0.700 | 30 | [0.533, 0.867] | fraction exact match; 95% bootstrap CI |
| completeness | model_vs_gold/cohen_kappa | cohen_kappa | 0.323 | 30 | [-0.074, 0.653] | sklearn.metrics.cohen_kappa_score; 95% bootstrap CI, 1000 resamples, seeded |
| condition | labeller_a_vs_b/raw_agreement | raw_agreement | 1.000 | 30 | [1.000, 1.000] | fraction exact match; 95% bootstrap CI |
| condition | labeller_a_vs_b/cohen_kappa | cohen_kappa | 1.000 | 30 | [1.000, 1.000] | sklearn.metrics.cohen_kappa_score; 95% bootstrap CI, 1000 resamples, seeded |
| condition | labeller_a_vs_b/weighted_kappa_quadratic | weighted_kappa_quadratic | 1.000 | 30 | [1.000, 1.000] | sklearn.metrics.cohen_kappa_score(weights='quadratic'); 95% bootstrap CI, 1000 resamples, seeded |
| condition | model_vs_gold/raw_agreement | raw_agreement | 0.333 | 30 | [0.167, 0.500] | fraction exact match; 95% bootstrap CI |
| condition | model_vs_gold/cohen_kappa | cohen_kappa | 0.144 | 30 | [0.014, 0.297] | sklearn.metrics.cohen_kappa_score; 95% bootstrap CI, 1000 resamples, seeded |
| condition | model_vs_gold/weighted_kappa_quadratic | weighted_kappa_quadratic | 0.727 | 30 | [0.000, 1.000] | sklearn.metrics.cohen_kappa_score(weights='quadratic'); 95% bootstrap CI, 1000 resamples, seeded |
| unit_presence | labeller_a_vs_b/raw_agreement | raw_agreement | 1.000 | 30 | [1.000, 1.000] | fraction exact match; 95% bootstrap CI |
| unit_presence | labeller_a_vs_b/cohen_kappa | cohen_kappa | nan | 30 | [nan, nan] | sklearn.metrics.cohen_kappa_score; 95% bootstrap CI, 1000 resamples, seeded (undefined: only one class present in this pairing - total agreement) |
| unit_presence | model_vs_gold/raw_agreement | raw_agreement | 1.000 | 30 | [1.000, 1.000] | fraction exact match; 95% bootstrap CI |
| unit_presence | model_vs_gold/cohen_kappa | cohen_kappa | nan | 30 | [nan, nan] | sklearn.metrics.cohen_kappa_score; 95% bootstrap CI, 1000 resamples, seeded (undefined: only one class present in this pairing - total agreement) |

## Selective prediction (§21.2)

| Check | Strict accuracy | Coverage | Selective accuracy | Unnecessary-uncertain rate | n |
|---|---|---|---|---|---|
| identity | 86.7% | 96.7% | 89.7% | 0.0% | 30 |
| completeness | 60.0% | 90.0% | 66.7% | 0.0% | 30 |
| condition | 10.0% | 20.0% | 50.0% | 73.9% | 30 |

## Per-check false positives / false negatives (§21.1)

| Check | Positive means | FP | FP means | FN (dangerous) | FN means | n |
|---|---|---|---|---|---|---|
| unit_presence | item not returned (empty/non-product) | 0 | flagged empty, but the item was there | 0 | empty box passed as a real return | 30 |
| identity | wrong item (identity_match = no) | 0 | flagged wrong, but it was right | 3 | wrong item passed as right | 30 |
| completeness | incomplete (>=1 component missing) | 4 | said missing, but complete | 5 | said complete, but something was missing | 30 |
| condition | N/A (ordinal; ranked by CONDITION_GRADE_ORDER) | 1 | under-grade: system says worse than gold | 2 | over-grade: system says better than gold (customer gets less than listed) | 6 |

## Disposition confusion matrix (§21.1)

| gold \ agent | dispose | liquidate | null | refurbish | restock |
|---|---|---|---|---|---|
| dispose | 0 | 0 | 3 | 0 | 1 |
| liquidate | 0 | 0 | 3 | 0 | 0 |
| null | 0 | 0 | 16 | 0 | 0 |
| refurbish | 0 | 0 | 0 | 0 | 0 |
| restock | 0 | 1 | 2 | 3 | 1 |

- `restock` when gold != restock (dangerous): **1**
- `dispose` when gold was recoverable (value loss): **0**
- n = 30

## Failure modes (§21.4)

| Mode | Count | Example unit_ids |
|---|---|---|
| condition_ambiguity | 12 | UNIT-WATCH-03, UNIT-AIR-03, UNIT-PHONE-04 |
| accessory_not_visible | 5 | UNIT-WATCH-02, UNIT-PHONE-02, UNIT-PHONE-03 |
| false_missing_component | 4 | UNIT-PUZZLE-02, UNIT-CEREAL-01, UNIT-CEREAL-02 |
| wrong_disposition | 3 | UNIT-WATCH-01, UNIT-AIR-01, UNIT-PHONE-01 |
| barcode_failure | 3 | UNIT-AIR-02, UNIT-LEASH-02, UNIT-SHAMPOO-02 |
| overgrade | 2 | UNIT-KETTLE-01, UNIT-SHAMPOO-01 |
| undergrade | 1 | UNIT-PUZZLE-04 |

## Per-unit summary (§21.9)

- **identity:** agree 26, disagree 3, uncertain 1 (n=30)
- **completeness:** agree 18, disagree 9, uncertain 3 (n=30)
- **condition:** agree 3, disagree 3, uncertain 24 (n=30)
- **disposition:** agree 1, disagree 5, uncertain 24 (n=30)

## Per-unit table (§21.9)

Disagreements first, then uncertain, then agreements.

| unit_id | scenario_codes | lighting | angle | blur | ambiguity | product_seen_in_dev | human_a_identity | human_b_identity | gold_identity | agent_identity | identity_agree | human_a_completeness | human_b_completeness | gold_completeness | agent_completeness | completeness_agree | gold_parts_missing | agent_parts_missing | human_a_condition | human_b_condition | gold_condition | agent_condition | condition_agree | condition_error | gold_disposition | agent_disposition | agent_requires_review | disposition_agree | agent_uncertain_checks | uncertainty_reasons | latency_ms | cost_usd | failure_mode | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| UNIT-AIR-01 | baseline | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Acceptable | Used - Acceptable | Used - Acceptable | Used - Acceptable | yes | exact | restock | refurbish | no | no |  |  |  |  | wrong_disposition | sold_vs_returned_id_check='matched' |
| UNIT-AIR-02 | identity_mismatch | normal | square | none | clear | no | no | no | no | yes | no | uncertain | uncertain | uncertain | uncertain | agent_uncertain |  | AirPods case | uncertain | uncertain | uncertain | uncertain | agent_uncertain | agent_uncertain |  |  | yes | agent_uncertain | condition;observed_state |  |  |  | barcode_failure | sold_vs_returned_id_check='matched' |
| UNIT-CEREAL-01 | baseline;new_only_category | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | incomplete | no |  | cereal box | Used - Like New | Used - Like New | Used - Like New | uncertain | agent_uncertain | agent_uncertain | dispose |  | yes | agent_uncertain | condition |  |  |  | false_missing_component | sold_vs_returned_id_check='matched' |
| UNIT-CEREAL-02 | id_mismatch_org_order;new_only_category | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | incomplete | no |  | cereal box | Used - Like New | Used - Like New | Used - Like New | uncertain | agent_uncertain | agent_uncertain |  |  | yes | agent_uncertain | condition |  |  |  | false_missing_component | sold_vs_returned_id_check="NOT MATCHED: org_id: sold='org_demo_alpha' vs returned='org_demo_beta'; order_id: sold='ORD-CEREAL-02' vs returned='ORD-CEREAL-02-X'" |
| UNIT-CEREAL-03 | malformed_parts_list;new_only_category | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | incomplete | no |  | Cereal Box;Vitamin Sachet ☕;Spoon xABC | Used - Like New | Used - Like New | Used - Like New | uncertain | agent_uncertain | agent_uncertain | dispose |  | yes | agent_uncertain | condition |  |  |  | false_missing_component | sold_vs_returned_id_check='matched' |
| UNIT-EDGE-02 | multi_photo;damaged | normal | square | none | clear | no | yes | yes | yes | yes | yes | incomplete | incomplete | incomplete | complete | no | battery;battery cover |  | Used - Acceptable | Used - Acceptable | Used - Acceptable | uncertain | agent_uncertain | agent_uncertain | liquidate |  | yes | agent_uncertain | condition;observed_state |  |  |  | accessory_not_visible | sold_vs_returned_id_check='matched' |
| UNIT-KETTLE-01 | baseline | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Good | Used - Good | Used - Good | Used - Like New | no | over_grade_by_2 | restock | restock | no | yes |  |  |  |  | overgrade | sold_vs_returned_id_check='matched' |
| UNIT-LEASH-02 | identity_mismatch | normal | square | none | clear | no | no | no | no | yes | no | uncertain | uncertain | uncertain | uncertain | agent_uncertain |  | leash | uncertain | uncertain | uncertain | uncertain | agent_uncertain | agent_uncertain |  |  | yes | agent_uncertain | condition;observed_state |  |  |  | barcode_failure | sold_vs_returned_id_check='matched' |
| UNIT-PHONE-01 | baseline | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Very Good | Used - Very Good | Used - Very Good | Used - Very Good | yes | exact | restock | refurbish | no | no |  |  |  |  | wrong_disposition | sold_vs_returned_id_check='matched' |
| UNIT-PHONE-02 | side_part_missing;no_photo | normal | square | none | clear | no | yes | yes | yes | yes | yes | incomplete | incomplete | incomplete | complete | no | battery;battery cover |  | uncertain | uncertain | uncertain | uncertain | agent_uncertain | agent_uncertain |  |  | yes | agent_uncertain | condition;observed_state |  |  |  | accessory_not_visible | sold_vs_returned_id_check='matched' |
| UNIT-PHONE-03 | main_part_missing;no_photo | normal | square | none | clear | no | yes | yes | yes | yes | yes | incomplete | incomplete | incomplete | complete | no | handset |  | uncertain | uncertain | uncertain | uncertain | agent_uncertain | agent_uncertain |  |  | yes | agent_uncertain | condition;observed_state |  |  |  | accessory_not_visible | sold_vs_returned_id_check='matched' |
| UNIT-PUZZLE-01 | baseline | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Good | Used - Good | Used - Good | uncertain | agent_uncertain | agent_uncertain | restock | liquidate | no | no | condition |  |  |  | condition_ambiguity | sold_vs_returned_id_check='matched' |
| UNIT-PUZZLE-02 | damaged | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | incomplete | no |  | puzzle pieces | Used - Acceptable | Used - Acceptable | Used - Acceptable | uncertain | agent_uncertain | agent_uncertain | liquidate |  | yes | agent_uncertain | condition |  |  |  | false_missing_component | sold_vs_returned_id_check='matched' |
| UNIT-PUZZLE-03 | side_part_missing;no_photo | normal | square | none | clear | no | yes | yes | yes | yes | yes | incomplete | incomplete | incomplete | complete | no | puzzle pieces |  | uncertain | uncertain | uncertain | uncertain | agent_uncertain | agent_uncertain |  |  | yes | agent_uncertain | condition;observed_state |  |  |  | accessory_not_visible | sold_vs_returned_id_check='matched' |
| UNIT-PUZZLE-04 | id_mismatch_order_sku | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Good | Used - Good | Used - Good | Used - Acceptable | no | under_grade_by_1 |  |  | yes | agent_uncertain |  |  |  |  | undergrade | sold_vs_returned_id_check="NOT MATCHED: order_id: sold='ORD-PUZZLE-04' vs returned='ORD-PUZZLE-04-X'; ordered_sku: sold='SKU-PUZZLE-A' vs returned='SKU-PUZZLE-B'" |
| UNIT-SHAMPOO-01 | baseline;new_only_category | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Like New | Used - Like New | Used - Like New | New | no | over_grade_by_1 | dispose | restock | no | no |  |  |  |  | overgrade | sold_vs_returned_id_check='matched' |
| UNIT-SHAMPOO-02 | identity_mismatch;new_only_category | normal | square | none | clear | no | no | no | no | yes | no | uncertain | uncertain | uncertain | uncertain | agent_uncertain |  | bottle;pump cap | uncertain | uncertain | uncertain | uncertain | agent_uncertain | agent_uncertain | dispose |  | yes | agent_uncertain | condition;observed_state |  |  |  | barcode_failure | sold_vs_returned_id_check='matched' |
| UNIT-WATCH-01 | baseline | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Like New | Used - Like New | Used - Like New | Used - Like New | yes | exact | restock | refurbish | no | no |  |  |  |  | wrong_disposition | sold_vs_returned_id_check='matched' |
| UNIT-WATCH-02 | main_part_missing;no_photo | normal | square | none | clear | no | yes | yes | yes | yes | yes | incomplete | incomplete | incomplete | complete | no | watch |  | uncertain | uncertain | uncertain | uncertain | agent_uncertain | agent_uncertain |  |  | yes | agent_uncertain | condition;observed_state |  |  |  | accessory_not_visible | sold_vs_returned_id_check='matched' |
| UNIT-AIR-03 | id_mismatch_sku_asin | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Like New | Used - Like New | Used - Like New | uncertain | agent_uncertain | agent_uncertain |  |  | yes | agent_uncertain | condition;observed_state |  |  |  | condition_ambiguity | sold_vs_returned_id_check="NOT MATCHED: ordered_sku: sold='SKU-AIR-A' vs returned='SKU-AIR-B'; ordered_asin: sold='B0AIR001' vs returned='B0AIR002'" |
| UNIT-EDGE-01 | whitespace_edge_case;identity_carried_forward | normal | square | none | clear | no | uncertain | uncertain | uncertain | uncertain | agent_uncertain | complete | complete | complete | complete | yes |  |  | Used - Very Good | Used - Very Good | Used - Very Good | uncertain | agent_uncertain | agent_uncertain | restock |  | yes | agent_uncertain | identity;condition;observed_state |  |  |  | condition_ambiguity | sold_vs_returned_id_check='matched' |
| UNIT-KETTLE-02 | id_mismatch_order | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Like New | Used - Like New | Used - Like New | uncertain | agent_uncertain | agent_uncertain |  |  | yes | agent_uncertain | condition |  |  |  | condition_ambiguity | sold_vs_returned_id_check="NOT MATCHED: order_id: sold='ORD-KETTLE-02' vs returned='ORD-KETTLE-02-WRONG'" |
| UNIT-LEASH-01 | baseline | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Good | Used - Good | Used - Good | uncertain | agent_uncertain | agent_uncertain | restock |  | yes | agent_uncertain | condition |  |  |  | condition_ambiguity | sold_vs_returned_id_check='matched' |
| UNIT-LEASH-03 | id_mismatch_asin | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Good | Used - Good | Used - Good | uncertain | agent_uncertain | agent_uncertain |  |  | yes | agent_uncertain | condition |  |  |  | condition_ambiguity | sold_vs_returned_id_check="NOT MATCHED: ordered_asin: sold='B0LEASH01' vs returned='B0LEASH02'" |
| UNIT-PHONE-04 | damaged | normal | square | none | clear | no | yes | yes | yes | yes | yes | incomplete | incomplete | incomplete | incomplete | yes | battery;battery cover | battery;battery cover | Used - Acceptable | Used - Acceptable | Used - Acceptable | uncertain | agent_uncertain | agent_uncertain | liquidate |  | yes | agent_uncertain | condition |  |  |  | condition_ambiguity | sold_vs_returned_id_check='matched' |
| UNIT-PHONE-05 | id_mismatch_org | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Very Good | Used - Very Good | Used - Very Good | uncertain | agent_uncertain | agent_uncertain |  |  | yes | agent_uncertain | condition;observed_state |  |  |  | condition_ambiguity | sold_vs_returned_id_check="NOT MATCHED: org_id: sold='org_demo_alpha' vs returned='org_demo_beta'" |
| UNIT-PHONE-06 | unknown_category | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Very Good | Used - Very Good | Used - Very Good | uncertain | agent_uncertain | agent_uncertain |  |  | yes | agent_uncertain | condition;observed_state |  |  |  | condition_ambiguity | sold_vs_returned_id_check='matched' |
| UNIT-PHONE-07 | no_category | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Very Good | Used - Very Good | Used - Very Good | uncertain | agent_uncertain | agent_uncertain |  |  | yes | agent_uncertain | condition;observed_state |  |  |  | condition_ambiguity | sold_vs_returned_id_check='matched' |
| UNIT-SHAMPOO-03 | id_mismatch_sku;new_only_category | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Like New | Used - Like New | Used - Like New | uncertain | agent_uncertain | agent_uncertain |  |  | yes | agent_uncertain | condition |  |  |  | condition_ambiguity | sold_vs_returned_id_check="NOT MATCHED: ordered_sku: sold='SKU-SHAMPOO-A' vs returned='SKU-SHAMPOO-B'" |
| UNIT-WATCH-03 | id_mismatch_order | normal | square | none | clear | no | yes | yes | yes | yes | yes | complete | complete | complete | complete | yes |  |  | Used - Like New | Used - Like New | Used - Like New | uncertain | agent_uncertain | agent_uncertain |  |  | yes | agent_uncertain | condition;observed_state |  |  |  | condition_ambiguity | sold_vs_returned_id_check="NOT MATCHED: order_id: sold='ORD-WATCH-03' vs returned='ORD-WATCH-03-WRONG'" |
