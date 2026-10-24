# Interaction Detector API

Module: `src/interaction_detector.py`

```python
from src.interaction_detector import check_interactions

result = check_interactions(["PRODUCT A", "PRODUCT B"])
```

The detector resolves English or Arabic product aliases, loads only graph-eligible ingredient links, enumerates cross-product ingredient pairs, and checks those pairs against a caller-supplied evidence CSV. It never infers a clinical interaction from names or drug classes.

## Statuses

| Status | Meaning |
|---|---|
| `DOCUMENTED_INTERACTION_FOUND` | At least one matching evidence row was found in the queried source file. |
| `NO_MATCH_FOUND_IN_QUERIED_SOURCES` | The evidence file existed and no matching row was found. This is not a safety claim. |
| `SOURCE_QUERY_FAILED` | Evidence file, required columns, or local input data could not be loaded. |
| `PRODUCT_NOT_FOUND` | An input could not be resolved to a unique product alias. |
| `AMBIGUOUS_INGREDIENT_IDENTITY` | A product-like input is not uniquely resolvable. |
| `INSUFFICIENT_EVIDENCE` | No medicine inputs were supplied. |

Every result includes `resolved_medicines`, `matches`, `unresolved_pairs`, and `coverage`. Clinical decisions require qualified professional review; the result does not recommend starting, stopping, or changing treatment.