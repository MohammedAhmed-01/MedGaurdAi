"""Raw-data profiling and quality audit for the Egyptian drug source CSV."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from .loader import REQUIRED_COLUMNS


STATUS_MARKER_RE = re.compile(
    r"\((ILLEGAL IMPORT|WITHDRAWAL|CANCELLED|N/A|DISCONTINUED)\)",
    re.IGNORECASE,
)
DOSE_RE = re.compile(r"\d[\d.,]*\s*(?:MG|MCG|G|ML|IU|%)", re.IGNORECASE)


def audit_raw(source_csv: str | Path, report_dir: str | Path) -> dict[str, Path]:
    """Profile the immutable source CSV and write Stage 1 audit artifacts."""
    source_path = Path(source_csv)
    output_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(source_path, dtype={"price_egp": "float64"})

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    scientific = frame["scientific_name"].fillna("").astype(str)
    english = frame["commercial_name_en"].fillna("").astype(str)
    prices = pd.to_numeric(frame["price_egp"], errors="coerce")
    valid_prices = prices.dropna()
    q1 = valid_prices.quantile(0.25) if not valid_prices.empty else float("nan")
    q3 = valid_prices.quantile(0.75) if not valid_prices.empty else float("nan")
    iqr = q3 - q1
    upper_outlier = q3 + 1.5 * iqr if pd.notna(iqr) else float("nan")

    metrics = [
        ("row_count", len(frame), "rows", "Raw data rows; source is not modified."),
        ("column_count", len(frame.columns), "columns", "Includes the seven source fields."),
        ("exact_duplicate_rows", int(frame.duplicated(keep="first").sum()), "rows", "Flag only; do not delete automatically."),
        ("duplicate_english_name_rows", int(frame.duplicated("commercial_name_en", keep=False).sum()), "rows", "Names can legitimately represent different strengths or manufacturers."),
        ("missing_scientific_name", int(frame["scientific_name"].isna().sum()), "rows", "Keep products unresolved until evidence is available."),
        ("empty_scientific_name_after_trim", int((scientific.str.strip() == "").sum()), "rows", "Includes null and whitespace-only values."),
        ("missing_manufacturer", int(frame["manufacturer"].isna().sum()), "rows", "Retain as unknown."),
        ("missing_drug_class", int(frame["drug_class"].isna().sum()), "rows", "Retain as unknown."),
        ("missing_route", int(frame["route"].isna().sum()), "rows", "Retain as unknown."),
        ("invalid_or_missing_price", int(prices.isna().sum()), "rows", "Do not impute; review source value."),
        ("non_positive_price", int((prices <= 0).fillna(False).sum()), "rows", "Flag for review; preserve original value."),
        ("price_upper_iqr_outlier", int((prices > upper_outlier).fillna(False).sum()), "rows", f"Tukey upper fence: {upper_outlier:.2f} EGP." if pd.notna(upper_outlier) else "Not calculable."),
        ("status_marker_rows", int(english.map(lambda value: bool(STATUS_MARKER_RE.search(value))).sum()), "rows", "Extract marker only in derived data."),
        ("multi_ingredient_plus_rows", int(scientific.str.contains(r"\+", regex=True).sum()), "rows", "Plus is the dominant source separator; parenthetical content is preserved."),
        ("scientific_name_dose_expression_rows", int(scientific.map(lambda value: bool(DOSE_RE.search(value))).sum()), "rows", "Dose is a candidate field, never an identity."),
        ("scientific_name_truncated_rows", int(scientific.str.rstrip().str.endswith("+").sum()), "rows", "Keep row and route to review."),
        ("manufacturer_contains_split_marker", int(frame["manufacturer"].fillna("").astype(str).str.contains(" > ", regex=False).sum()), "rows", "Parse conservatively and preserve original."),
    ]
    metrics_frame = pd.DataFrame(metrics, columns=["metric", "value", "unit", "notes"])
    metrics_path = output_dir / "raw_data_quality_metrics.csv"
    metrics_frame.to_csv(metrics_path, index=False)

    issue_rows = [
        ("MISSING_SCIENTIFIC_NAME", int((scientific.str.strip() == "").sum()), "Keep the product; do not create ingredient edges.", "Missing identity is unresolved, not safe or ingredient-free."),
        ("INVALID_PRICE", int(prices.isna().sum()), "Keep raw value and flag for review; no imputation.", "Price quality does not determine product identity."),
        ("NON_POSITIVE_PRICE", int((prices <= 0).fillna(False).sum()), "Keep raw value and flag for review.", "May be a source convention or invalid price."),
        ("PRICE_IQR_OUTLIER", int((prices > upper_outlier).fillna(False).sum()), "Keep value; review extreme prices separately.", "Outlier is not proof of a data error."),
        ("DUPLICATE_ENGLISH_NAME", int(frame.duplicated("commercial_name_en", keep=False).sum()), "Do not merge without composition, strength, route, and manufacturer agreement.", "Commercial names are not stable product identifiers."),
        ("EXACT_DUPLICATE_ROW", int(frame.duplicated(keep="first").sum()), "Flag only; preserve every source row and index.", "Source provenance must remain complete."),
        ("TRUNCATED_SCIENTIFIC_NAME", int(scientific.str.rstrip().str.endswith("+").sum()), "Keep parsed prefix only as provisional and require review.", "The source list may be incomplete."),
        ("STATUS_MARKER_PRESENT", int(english.map(lambda value: bool(STATUS_MARKER_RE.search(value))).sum()), "Store marker as product_status; do not infer current approval.", "Dataset presence is not proof of current marketing or approval."),
    ]
    issue_path = output_dir / "raw_data_issue_inventory.csv"
    pd.DataFrame(issue_rows, columns=["issue_code", "affected_rows", "handling_policy", "interpretation"]).to_csv(issue_path, index=False)

    report_path = output_dir / "raw_data_quality_report.md"
    report_path.write_text(_markdown_report(source_path, frame, metrics_frame, q1, q3, upper_outlier), encoding="utf-8")
    return {"metrics": metrics_path, "issues": issue_path, "report": report_path}


def _markdown_report(source_path: Path, frame: pd.DataFrame, metrics: pd.DataFrame, q1: float, q3: float, upper: float) -> str:
    lines = [
        "# Raw Data Quality Report",
        "",
        f"Source: `{source_path.as_posix()}`",
        "",
        "This audit reads the source CSV without modifying or dropping records. All findings are flags for downstream handling, not proof that an unusual value is invalid.",
        "",
        "## Verified Schema",
        "",
        f"- Rows: {len(frame):,}",
        f"- Columns: {len(frame.columns)}",
        f"- Columns: {', '.join(frame.columns)}",
        f"- Price quartiles: Q1={q1:.2f} EGP, Q3={q3:.2f} EGP; upper Tukey fence={upper:.2f} EGP",
        "",
        "## Handling Rules",
        "",
        "- Preserve every source row and retain its zero-based source-row position for traceability.",
        "- Do not merge duplicate names without agreement on formulation, strength, route, manufacturer, and ingredient composition.",
        "- Keep missing or malformed ingredient text unresolved; never infer an ingredient from a commercial name alone.",
        "- Preserve source prices, including outliers, and flag them rather than imputing values.",
        "- Extract status markers into derived fields, but do not interpret them as current regulatory status without authoritative evidence.",
        "",
        "## Metrics",
        "",
        "| Metric | Value | Unit | Notes |",
        "|---|---:|---|---|",
    ]
    lines.extend(f"| {row.metric} | {int(row.value):,} | {row.unit} | {row.notes} |" for row in metrics.itertuples())
    lines.extend(["", "## Quality Gate", "", "Stage 1 raw profiling is complete for the current source snapshot. Product transformation may proceed only with the documented flags and handling rules above; ingredient identity and interaction evidence remain separate quality gates.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the immutable Egyptian drug source CSV.")
    parser.add_argument("--source", default="data/egyptian-drugs.csv")
    parser.add_argument("--reports", default="reports")
    args = parser.parse_args()
    for name, path in audit_raw(args.source, args.reports).items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())