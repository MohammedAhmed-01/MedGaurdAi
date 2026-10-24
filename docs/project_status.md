# Egyptian Drug Knowledge Graph — Project Status

> Generated: 2026-10-24T12:10+03:00

## Executive Summary

The project has a working data-loading/cleaning pipeline and an ingredient parsing + token inventory system. A dated rerun on 2026-10-24 produced a verified 25,070-row source snapshot, 57,198 ingredient-token occurrences, and 8,498 distinct raw tokens. Canonicalization resolved 10,374 occurrences (18.14%); 46,824 remain unresolved and block a production graph. Interaction research, the interaction detector, and Neo4j import have not started.


---

## Stage Status Overview

| Stage | Description | Status | Evidence |
| ------- | ------------ | -------- | ---------- |
| **0** | Project Inventory & Reproducibility | `COMPLETED_WITH_WARNINGS` | Existing source, code, outputs, configs, and tests were inventoried. The dated validation output is under `outputs/validated_20261024/`; no Git metadata is available in the workspace. |
| **1** | Raw Data Profiling & Quality Audit | `COMPLETED_WITH_WARNINGS` | `reports/raw_data_quality_report.md`, `reports/raw_data_quality_metrics.csv`, and `reports/raw_data_issue_inventory.csv` were generated from the source; 25,070 rows and 7 source columns verified. |
| **2** | Ingredient Parsing & Canonicalization | `COMPLETED_WITH_WARNINGS` | Parsing rerun: 57,198 token occurrences, 8,498 distinct raw tokens. Canonicalization: 3,457 automatic, 3,269 exact pass-through, 3,648 review, 46,824 unresolved; unresolved mappings block production graph loading. |
| **3** | Product-Level Cleaning & Standardization | `COMPLETED_WITH_WARNINGS` | `data/clean/medicine_products.csv` has 25,070 source-traceable products; aliases, all parsed ingredient links, review queue, audit, and report were generated. Only 6,476 links are graph-eligible; 24,024 products remain under review. |
| **4** | Reference-Based Ingredient Validation | `COMPLETED_WITH_WARNINGS` | Crosswalk and review queue generated, but configured evidence remains explicitly unverified because no external reference was queried in this run. |
| **5** | Drug–Drug Interaction Source Research | `COMPLETED_WITH_WARNINGS` | Candidate source assessment and registry exist; all sources remain `NOT_VERIFIED` and no interaction source was queried or downloaded. |
| **6** | Interaction Knowledge Base | `NOT_STARTED` | No interaction data files |
| **7** | Product-to-Interaction Resolution | `COMPLETED_WITH_WARNINGS` | Offline evidence-gated detector, API documentation, and tests exist. Live lookup is blocked until an approved interaction source is actually ingested. |
| **8** | Neo4j Graph Schema & Modeling | `COMPLETED_WITH_WARNINGS` | Schema docs and import package generated with stable IDs and graph-eligibility filtering; no Neo4j instance was queried. |
| **9** | Cypher Import Package | `COMPLETED_WITH_WARNINGS` | Actual `neo4j/00` through `neo4j/07` scripts and README generated; not executed, and interaction input is header-only. |
| **10** | Testing, Validation & Release | `COMPLETED_WITH_WARNINGS` | 87 tests pass and syntax validation passes. Integration, external-evidence, and Neo4j execution remain unavailable; the release report marks the system NOT PRODUCTION READY. |
| **11** | Final Deliverable Package | `NOT_STARTED` | Missing most required docs, reports, and deliverables |

---

## Existing Artifacts Inventory

### Source Data

| File | Rows (excl header) | Description |
|------|-----|-------------|
| `data/egyptian-drugs.csv` | 25,070 | Raw source. 7 columns: `commercial_name_en`, `commercial_name_ar`, `scientific_name`, `manufacturer`, `drug_class`, `route`, `price_egp`. No `product_id`. |

### Pipeline Source Code (`src/drug_pipeline/`)

| Module | Description | Status |
| -------- | ------------- | -------- |
| `__init__.py` | Package init, exposes `run()` | Working |
| `loader.py` | Stage 0: Load CSV, add `source_row_index`, validate schema, profile | Working |
| `cleaner.py` | Stages 1–4: Duplicate detection, status markers, manufacturer parsing, drug class/route canonicalization | Working |
| `ingredient_parser.py` | Stage 5: Parse `scientific_name` → `ParseResult`/`IngredientToken` objects | Working |
| `inventory.py` | Stage 6: Build token table, frequency report, review queue | Working |
| `reporter.py` | Stage 7: Build DQ stats dict, write all output files | Working |
| `pipeline.py` | Orchestrator: runs Stages 0–7 in sequence | Working |
| `canonicalizer.py` | Stage 5b: Two-tier canonicalization with synonym map + canonical table | Working but low coverage |

### Configuration Files (`config/`)

| File | Entries | Description |
| ------ | --------- | ------------- |
| `drug_class_map.csv` | 32 | Raw → canonical drug class mappings |
| `route_map.csv` | 16 | Raw → canonical route mappings |
| `status_markers.csv` | 5 | Regex patterns for registration status |
| `ingredient_synonym_map.csv` | 106 | Raw ingredient → canonical name mappings with evidence |
| `canonical_ingredients.csv` | 78 | Canonical ingredient reference table with IDs (ING-0001..ING-0078) |
| `ingredient_token_canonicalized.csv` | 57,208 | Canonicalized token table (output of canonicalizer) |
| `normalization_audit.csv` | 106 | Audit trail of synonym map entries |
| `normalization_review_queue.csv` | 2,021 | Tokens needing review (from canonicalizer) |

### Pipeline Outputs (`outputs/`)

| File | Rows | Description |
| ------ | ------ | ------------- |
| `dq_report.json` | — | Data quality metrics (JSON) |
| `dq_report.html` | — | HTML summary of DQ report |
| `drug_products_processed.csv` | 25,100 | Cleaned product table with added columns |
| `ingredient_token_table.csv` | 57,208 | Flat token table (source_row_index × token) |
| `ingredient_token_frequency.csv` | 8,504 | Unique tokens ranked by frequency |
| `ingredient_review_queue.csv` | 2,021 | Tokens flagged for human review |
| `missing_scientific_names.csv` | 2,311 | Products with no `scientific_name` |

### Tests

| File | Description | Status |
|------|-------------|--------|
| `tests/test_ingredient_parser.py` | 60+ test cases for ingredient parsing | Present, not verified this session |
| `src/drug_pipeline/test_canonicalizer.py` | Unit tests for canonicalization module | Present, not verified this session |

---

## Key Metrics from Current State

### Data Quality (from `dq_report.json`)

- **Raw rows**: 25,070
- **Exact duplicates flagged**: 4
- **Name duplicates flagged**: 10
- **Missing scientific_name**: 2,308 (9.21%)
- **Missing manufacturer**: 71 (0.28%)
- **Missing drug_class**: 97 (0.39%)
- **Price range**: EGP 0.30 – 375,504.00 (mean 674.54, median 75.00)
- **Registration status markers**: 1,208 N/A + 255 Cancelled + 99 Illegal Import + 1 Withdrawn

### Ingredient Parsing

- **Total token occurrences**: 57,198
- **Unique raw tokens**: 8,499
- **Tokens with embedded dose**: 1,367
- **Tokens with parenthetical content**: 1,745
- **Review queue tokens**: 2,018 unique (3,498 total occurrences)

### Canonicalization Coverage (CRITICAL GAP)

- **AUTO_CANONICAL**: 3,457 occurrences (6.04%)
- **EXACT_PASS_THROUGH**: 3,269 occurrences (5.72%)
- **NEEDS_REVIEW**: 3,648 occurrences (6.38%)
- **UNRESOLVED**: 46,824 occurrences (81.86%)
- **Synonym map entries**: 106 (covering 78 canonical ingredients)

### What's Missing for Downstream Stages

1. ~82% of ingredient tokens have no canonical mapping
2. No product ID scheme or product-level deduplication
3. No ingredient identity validation against external references
4. No interaction source research or data
5. No Neo4j schema, scripts, or graph model
6. No interaction detector module
7. No integration tests
8. No comprehensive documentation suite

---

## Known Limitations

1. The raw dataset has no inherent product identifier — `source_row_index` is the only stable key
2. 2,308 products have no `scientific_name` at all — these cannot have ingredient relationships
3. The `price_egp` field has extreme outliers (max 375,504) that may represent bulk pricing or data errors
4. The `drug_class` field has 2,498 distinct values but only 32 are mapped in `drug_class_map.csv`
5. The canonicalizer's synonym map is small (106 entries) relative to the token space (8,499 unique tokens)
6. No external APIs have been queried yet
