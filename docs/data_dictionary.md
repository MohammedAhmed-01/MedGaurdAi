# Data Dictionary — Egyptian Drug Knowledge Graph

> Generated: 2026-10-24

## 1. Source Dataset (`data/egyptian-drugs.csv`)

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `commercial_name_en` | string | No (0 nulls) | English commercial product name. May contain dosage form, strength, pack size, and registration status markers like `(CANCELLED)`, `(ILLEGAL IMPORT)` |
| `commercial_name_ar` | string | No (0 nulls) | Arabic commercial product name. 20,148 unique values vs 25,065 unique English names — many products share the same Arabic base name |
| `scientific_name` | string | Yes (2,308 nulls / 9.21%) | Active ingredient(s). Combination products use `+` as primary separator. May contain parenthetical synonyms `PARACETAMOL(ACETAMINOPHEN)`, embedded doses, equals signs, slashes, and `&`/`AND` separators. 8,553 unique values |
| `manufacturer` | string | Yes (71 nulls / 0.28%) | Manufacturer name. May contain `>` separator indicating `local_manufacturer > distributor`. 5,565 unique values |
| `drug_class` | string | Yes (97 nulls / 0.39%) | Therapeutic class. 2,498 unique values. Many variations of the same concept exist (typos, plurals, parenthetical qualifiers) |
| `route` | string | No (0 nulls) | Route of administration. 13 unique values: `ORAL.SOLID`, `TOPICAL`, `INJECTION`, `UNKNOWN`, `ORAL.LIQUID`, `EFF`, `SPRAY`, `EYE`, `VAGINAL`, `MOUTH`, `RECTAL`, `SOAP`, `EAR` |
| `price_egp` | float64 | No (0 nulls) | Price in Egyptian Pounds. Range: 0.30 – 375,504.00. Median: 75.00. 75th percentile: 180.00 |

**Note:** The source CSV has no product ID column, no registration number, no barcode, and no explicit approval status field. The `source_row_index` (0-based) is assigned during loading as the sole stable identifier.

---

## 2. Processed Product Table (`outputs/drug_products_processed.csv`)

All original columns are preserved. Added columns from the pipeline:

| Column | Type | Added By | Description |
|--------|------|----------|-------------|
| `source_row_index` | int64 | loader.py | 0-based row index from source CSV |
| `is_exact_duplicate` | bool | cleaner.detect_duplicates | True if row is identical to a prior row across all 7 source columns |
| `is_name_duplicate` | bool | cleaner.detect_duplicates | True if `commercial_name_en` appears more than once |
| `registration_status` | string/null | cleaner.extract_status_markers | Extracted status: `ILLEGAL_IMPORT`, `WITHDRAWN`, `CANCELLED`, `NOT_APPLICABLE`, `DISCONTINUED`, or null |
| `commercial_name_en_clean` | string | cleaner.extract_status_markers | Commercial name with status marker text removed |
| `manufacturer_local` | string/null | cleaner.parse_manufacturer | Local manufacturer (left of `>`) or full value |
| `manufacturer_distributor` | string/null | cleaner.parse_manufacturer | Distributor (right of `>`) or null |
| `manufacturer_parse_flag` | string | cleaner.parse_manufacturer | `PLAIN`, `SPLIT`, `MULTI_SPLIT`, or `MISSING` |
| `drug_class_canonical` | string/null | cleaner.canonicalize_drug_class | Canonical drug class or pass-through |
| `drug_class_reviewed` | bool | cleaner.canonicalize_drug_class | True if mapping was found in `drug_class_map.csv` |
| `route_canonical` | string/null | cleaner.canonicalize_route | Canonical route from `route_map.csv` |
| `route_needs_review` | bool | cleaner.canonicalize_route | True if route value needs context review |

---

## 3. Ingredient Token Table (`outputs/ingredient_token_table.csv`)

One row per (product, ingredient position) pair. 57,208 rows from 25,070 source records.

| Column | Type | Description |
|--------|------|-------------|
| `source_row_index` | int64 | Links back to source product |
| `token_position` | int | 1-based position in the combination |
| `raw_token` | string | Exact ingredient text after splitting |
| `name_stripped` | string | Token with heuristic dose expression removed (not authoritative) |
| `dose_candidate` | string/null | Extracted dose expression (e.g., `500 MG`) — heuristic only |
| `parenthetical_content` | string/null | Text inside parentheses |
| `separator_detected` | string | `PLUS`, `SLASH`, `DASH`, `AND`, `AMP`, `EQUALS`, `NONE` |
| `record_flags` | string | Pipe-delimited record-level flags |
| `token_flags` | string | Pipe-delimited token-level flags |
| `requires_review` | bool | True if any flag triggers human review |

---

## 4. Canonicalized Token Table (`config/ingredient_token_canonicalized.csv`)

Same as token table plus 4 columns added by canonicalizer:

| Column | Type | Description |
|--------|------|-------------|
| `normalised_lookup_key` | string | Lookup key after dose-stripping, abbreviation expansion, parenthetical removal |
| `canonical_name` | string | Resolved canonical ingredient name, or empty |
| `canonical_ingredient_id` | string | Stable ID (e.g., `ING-0001`), or empty |
| `resolution_status` | string | `AUTO_CANONICAL`, `EXACT_PASS_THROUGH`, `NEEDS_REVIEW`, `UNRESOLVED`, `REJECTED` |

---

## 5. Canonical Ingredients Table (`config/canonical_ingredients.csv`)

78 rows. The authoritative reference for ingredient identities.

| Column | Type | Description |
|--------|------|-------------|
| `canonical_ingredient_id` | string | Stable ID (`ING-0001` through `ING-0078`) |
| `canonical_name` | string | Canonical name (upper case) |
| `preferred_display_name` | string | Human-readable display name |
| `ingredient_type` | string | `active_ingredient`, `mineral`, `vitamin`, `excipient`, `biological`, `herbal` |
| `review_status` | string | `approved`, `needs_review`, `provisional` |
| `evidence_source` | string | Source used for identity verification |
| `evidence_url` | string | URL to evidence source |
| `notes` | string | Curation notes |

---

## 6. Ingredient Synonym Map (`config/ingredient_synonym_map.csv`)

106 rows. Maps raw ingredient strings to canonical names.

| Column | Type | Description |
|--------|------|-------------|
| `raw_ingredient` | string | The raw ingredient text as found in the dataset |
| `canonical_ingredient` | string | Target canonical name |
| `mapping_type` | string | `documented_synonym`, `exact_normalization`, `identity_confirmed`, `broad_term_review` |
| `decision_status` | string | `auto_approved`, `needs_review`, `rejected` |
| `evidence_source` | string | Source authority for the mapping |
| `evidence_url` | string | URL to evidence |
| `notes` | string | Explanation of the mapping rationale |

---

## 7. Configuration Files

### `config/drug_class_map.csv`
Maps raw `drug_class` values to canonical forms. 32 entries. Columns: `raw_value`, `canonical_value`, `notes`.

### `config/route_map.csv`
Maps raw `route` values to canonical forms. 16 entries. Columns: `raw_value`, `canonical_value`, `notes`.

### `config/status_markers.csv`
Regex patterns for registration status detection. 5 entries. Columns: `pattern`, `status_code`, `description`.

---

## 8. Parse Flag Codes

| Flag | Level | Meaning |
|------|-------|---------|
| `MISSING_SCI_NAME` | Record | No `scientific_name` value |
| `TRUNCATED_LIST` | Record | Input ended with `+` indicating truncation |
| `SLASH_AMBIGUOUS` | Record/Token | `/` found — may be separator or per-unit notation |
| `EQUALS_AMBIGUOUS` | Record | `=` found — synonym or equative expression |
| `MIXED_SEPARATORS` | Record | Multiple separator types detected |
| `AND_SEPARATOR_USED` | Record | `AND` used as separator |
| `AMP_SEPARATOR_USED` | Record | `&` used as separator |
| `EMBEDDED_DOSE` | Token | Dose expression found in ingredient text |
| `HAS_PARENTHETICAL` | Token | Parenthetical content present |
| `PARSE_ERROR` | Token | Unexpected parsing failure |
| `EMPTY_TOKEN_PRODUCED` | Record | Splitting produced an empty token |

---

## 9. Resolution Status Codes (Canonicalization)

| Status | Meaning |
|--------|---------|
| `AUTO_CANONICAL` | Synonym map entry with `auto_approved` status |
| `EXACT_PASS_THROUGH` | Raw token already matches canonical name exactly |
| `NEEDS_REVIEW` | Mapping exists but `needs_review` or ambiguous |
| `UNRESOLVED` | No mapping found in synonym map |
| `REJECTED` | Mapping explicitly rejected |

