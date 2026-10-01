# Labelling sheet

Use this sheet for each unit before the agent runs.

## Unit
- Unit ID:
- Labeller ID:
- Labelled at (UTC timestamp):

## Official labels
- identity_match: `yes | no | uncertain`
- unit_presence: `product_present | empty_packaging | non_product_contents | uncertain`
- completeness: `complete | incomplete | uncertain`
- parts_missing:
- parts_uncertain:
- observed_state:
- amazon_condition: `New | Used - Like New | Used - Very Good | Used - Good | Used - Acceptable | uncertain`
- disposition: `restock | refurbish | liquidate | dispose` or blank with reason

## Per-check verdicts
- v_unit_presence: `PASS | FAIL | UNCERTAIN`
- v_identity: `PASS | FAIL | UNCERTAIN`
- v_completeness: `PASS | FAIL | UNCERTAIN`
- v_condition_grade: `PASS | FAIL | UNCERTAIN`
- v_relistable_as_is: `PASS | FAIL | UNCERTAIN`

## Notes
- [ ] Independent labelling complete
- [ ] No agent output consulted
- [ ] Labelling finished before any eval run starts
- [ ] Any disagreement noted for adjudication
