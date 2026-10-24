# Raw Data Quality Report

Source: `data/egyptian-drugs.csv`

This audit reads the source CSV without modifying or dropping records. All findings are flags for downstream handling, not proof that an unusual value is invalid.

## Verified Schema

- Rows: 25,070
- Columns: 7
- Columns: commercial_name_en, commercial_name_ar, scientific_name, manufacturer, drug_class, route, price_egp
- Price quartiles: Q1=31.00 EGP, Q3=180.00 EGP; upper Tukey fence=403.50 EGP

## Handling Rules

- Preserve every source row and retain its zero-based source-row position for traceability.
- Do not merge duplicate names without agreement on formulation, strength, route, manufacturer, and ingredient composition.
- Keep missing or malformed ingredient text unresolved; never infer an ingredient from a commercial name alone.
- Preserve source prices, including outliers, and flag them rather than imputing values.
- Extract status markers into derived fields, but do not interpret them as current regulatory status without authoritative evidence.

## Metrics

| Metric | Value | Unit | Notes |
|---|---:|---|---|
| row_count | 25,070 | rows | Raw data rows; source is not modified. |
| column_count | 7 | columns | Includes the seven source fields. |
| exact_duplicate_rows | 4 | rows | Flag only; do not delete automatically. |
| duplicate_english_name_rows | 10 | rows | Names can legitimately represent different strengths or manufacturers. |
| missing_scientific_name | 2,308 | rows | Keep products unresolved until evidence is available. |
| empty_scientific_name_after_trim | 2,308 | rows | Includes null and whitespace-only values. |
| missing_manufacturer | 71 | rows | Retain as unknown. |
| missing_drug_class | 97 | rows | Retain as unknown. |
| missing_route | 0 | rows | Retain as unknown. |
| invalid_or_missing_price | 0 | rows | Do not impute; review source value. |
| non_positive_price | 0 | rows | Flag for review; preserve original value. |
| price_upper_iqr_outlier | 2,186 | rows | Tukey upper fence: 403.50 EGP. |
| status_marker_rows | 1,563 | rows | Extract marker only in derived data. |
| multi_ingredient_plus_rows | 9,571 | rows | Plus is the dominant source separator; parenthetical content is preserved. |
| scientific_name_dose_expression_rows | 614 | rows | Dose is a candidate field, never an identity. |
| scientific_name_truncated_rows | 59 | rows | Keep row and route to review. |
| manufacturer_contains_split_marker | 13,271 | rows | Parse conservatively and preserve original. |

## Quality Gate

Stage 1 raw profiling is complete for the current source snapshot. Product transformation may proceed only with the documented flags and handling rules above; ingredient identity and interaction evidence remain separate quality gates.
