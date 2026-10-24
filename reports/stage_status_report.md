# Stage Status Report

Generated from the source and validation rerun on 2026-10-24.

| Stage | Status | Evidence and limitation |
|---|---|---|
| 0. Project inventory and reproducibility | COMPLETED_WITH_WARNINGS | Existing source, Python modules, configs, outputs, docs, and tests were inspected. No interaction dataset or Neo4j package exists. No Git metadata is available in this workspace. |
| 1. Raw profiling and data-quality audit | COMPLETED_WITH_WARNINGS | `reports/raw_data_quality_report.md`, `reports/raw_data_quality_metrics.csv`, and `reports/raw_data_issue_inventory.csv` were generated from `data/egyptian-drugs.csv`. The source has 25,070 rows and 7 columns. Outliers and missing values are flagged, not removed. |
| 2. Ingredient parsing and canonicalization | COMPLETED_WITH_WARNINGS | The dated rerun produced 57,198 token occurrences and 8,498 distinct raw tokens. Canonicalization produced 3,457 `AUTO_CANONICAL`, 3,269 `EXACT_PASS_THROUGH`, 3,648 `NEEDS_REVIEW`, and 46,824 `UNRESOLVED` rows in `outputs/validated_20261024/`. |
| 3. Product-level cleaning and standardization | COMPLETED_WITH_WARNINGS | `data/clean/medicine_products.csv` has 25,070 products with deterministic source-derived IDs; `data/clean/product_aliases.csv` has 50,140 aliases; `data/clean/product_ingredients.csv` retains 57,198 token links; 6,476 links are graph-eligible and 24,024 products remain in `data/review/product_review_queue.csv`. |
| 4. Reference-based ingredient identity validation | COMPLETED_WITH_WARNINGS | `data/curated/ingredient_reference_crosswalk.csv` contains 106 configured mappings; 69 are marked `DECLARED_MAPPING_UNVERIFIED` and 37 are in `data/review/ingredient_identity_review_queue.csv`. No external reference was queried in this run. |
| 5. Interaction source research | COMPLETED_WITH_WARNINGS | `docs/interaction_source_assessment.md` and `data/reference/interaction_source_registry.csv` document candidate sources, but all are `NOT_VERIFIED`; no source was queried or downloaded. |
| 6. Evidence-backed interaction knowledge base | NOT_STARTED | No interaction evidence, normalized interaction, provenance, or review files exist. No interaction records were fabricated. |
| 7. Product-to-interaction resolution | COMPLETED_WITH_WARNINGS | `src/interaction_detector.py`, `docs/interaction_detector_api.md`, and `tests/test_interaction_detector.py` exist and are covered by the 87-test suite. Live interaction lookup is blocked because the evidence table is intentionally empty. |
| 8. Neo4j graph schema and modeling | COMPLETED_WITH_WARNINGS | `docs/neo4j_graph_schema.md` and the `neo4j/` package define stable IDs, constraints, indexes, provenance, and graph-eligibility filtering. No Neo4j instance was available for execution. |
| 9. Cypher import package | COMPLETED_WITH_WARNINGS | `neo4j/00` through `neo4j/07` and `neo4j/README.md` are actual Cypher scripts. They were generated but not executed; interaction input is header-only. |
| 10. Testing and release readiness | COMPLETED_WITH_WARNINGS | `reports/test_results.md` records 87 passing tests and syntax validation. External evidence, integration, and Neo4j execution remain unavailable; `reports/release_readiness_report.md` correctly marks the system NOT PRODUCTION READY. |
| 11. Final handover package | NOT_STARTED | Downstream evidence, detector, graph, and release documents remain incomplete. |

## Verified counts

- Raw source: 25,070 rows, 7 columns.
- Processed validation rerun: 25,070 product rows, 57,198 token occurrences, 8,499 frequency rows, 2,087 review-queue rows, and 2,308 missing-scientific-name rows.
- Canonical reference: 78 ingredients and 106 synonym-map entries.
- Canonicalization: 10,374 occurrences resolved or pass-through; 46,824 unresolved.
- Product package: 25,070 products, 50,140 aliases, 57,198 retained token links, 6,476 graph-eligible links, and 24,024 products requiring review.
- Confirmed interaction records: 0. No interaction source was queried in this session.
- Neo4j imports executed: 0. No Neo4j instance was available or queried.

## Blocking conditions

The unresolved ingredient volume and absence of inspected interaction evidence prevent a production graph or clinical interaction claim. Product and ingredient review must occur before graph loading. `NO_MATCH_FOUND_IN_QUERIED_SOURCES` must not be reported until a real approved source query has been performed.