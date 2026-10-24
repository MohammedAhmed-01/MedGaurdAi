"""Stage 7 – Data-quality report and output file writer.

Generates:
* A plain-text / JSON data-quality summary (dq_report.json).
* An HTML data-quality report (dq_report.html).
* Output CSVs for all normalized tables.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .ingredient_parser import (
    FLAG_MISSING,
    FLAG_TRUNCATED,
    FLAG_EQUALS_AMBIGUOUS,
    FLAG_SLASH_AMBIGUOUS,
    FLAG_MIXED_SEPARATORS,
    FLAG_EMBEDDED_DOSE,
    FLAG_PARENTHETICAL,
    ParseResult,
)

logger = logging.getLogger(__name__)


# ── Output writers ─────────────────────────────────────────────────────────────


def write_outputs(
    df_clean: pd.DataFrame,
    token_table: pd.DataFrame,
    freq_report: pd.DataFrame,
    review_queue: pd.DataFrame,
    missing_sci_table: pd.DataFrame,
    dq_stats: Dict[str, Any],
    output_dir: str | Path,
) -> Dict[str, Path]:
    """Write all pipeline outputs to ``output_dir``.

    The source CSV is never touched.  All outputs are new files.

    Args:
        df_clean: Processed product-level DataFrame.
        token_table: Per-token flat table.
        freq_report: Token frequency report.
        review_queue: Tokens requiring human review.
        missing_sci_table: Records with missing scientific names.
        dq_stats: Summary stats dict from ``build_dq_stats()``.
        output_dir: Directory where all output files are written.

    Returns:
        Dict mapping output names to their resolved Paths.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    paths: Dict[str, Path] = {}

    # 1. Drug products table (processed)
    p = out / "drug_products_processed.csv"
    df_clean.to_csv(p, index=False)
    paths["drug_products_processed"] = p
    logger.info("Wrote %s (%d rows)", p.name, len(df_clean))

    # 2. Ingredient token table
    p = out / "ingredient_token_table.csv"
    token_table.to_csv(p, index=False)
    paths["ingredient_token_table"] = p
    logger.info("Wrote %s (%d rows)", p.name, len(token_table))

    # 3. Frequency report
    p = out / "ingredient_token_frequency.csv"
    freq_report.to_csv(p, index=False)
    paths["ingredient_token_frequency"] = p
    logger.info("Wrote %s (%d rows)", p.name, len(freq_report))

    # 4. Review queue
    p = out / "ingredient_review_queue.csv"
    review_queue.to_csv(p, index=False)
    paths["ingredient_review_queue"] = p
    logger.info("Wrote %s (%d rows)", p.name, len(review_queue))

    # 5. Missing scientific names
    p = out / "missing_scientific_names.csv"
    missing_sci_table.to_csv(p, index=False)
    paths["missing_scientific_names"] = p
    logger.info("Wrote %s (%d rows)", p.name, len(missing_sci_table))

    # 6. DQ report (JSON)
    p = out / "dq_report.json"
    p.write_text(json.dumps(dq_stats, indent=2, default=str))
    paths["dq_report_json"] = p
    logger.info("Wrote %s", p.name)

    # 7. DQ report (HTML)
    p = out / "dq_report.html"
    p.write_text(_render_html_report(dq_stats))
    paths["dq_report_html"] = p
    logger.info("Wrote %s", p.name)

    return paths


# ── DQ stats builder ──────────────────────────────────────────────────────────


def build_dq_stats(
    df_raw: pd.DataFrame,
    df_clean: pd.DataFrame,
    parse_results: List[ParseResult],
    token_table: pd.DataFrame,
    freq_report: pd.DataFrame,
    review_queue: pd.DataFrame,
    raw_profile: Dict,
) -> Dict[str, Any]:
    """Assemble the data-quality statistics dictionary.

    Args:
        df_raw: DataFrame as loaded (before any cleaning).
        df_clean: DataFrame after all cleaning stages.
        parse_results: List of ParseResult from Stage 5.
        token_table: Output of Stage 6 ``build_token_table()``.
        freq_report: Output of Stage 6 ``build_frequency_report()``.
        review_queue: Output of Stage 6 ``build_review_queue()``.
        raw_profile: Output of ``loader.profile_raw()``.

    Returns:
        Dictionary suitable for JSON serialisation.
    """
    # Record-level flag counts
    flag_counts: Dict[str, int] = {}
    for pr in parse_results:
        for f in pr.flags:
            flag_counts[f] = flag_counts.get(f, 0) + 1

    # Token-level flag counts
    tok_flag_counts: Dict[str, int] = {}
    for _, row in token_table.iterrows():
        for f in str(row.get("token_flags", "")).split("|"):
            if f:
                tok_flag_counts[f] = tok_flag_counts.get(f, 0) + 1

    # Separator distribution
    sep_dist: Dict[str, int] = {}
    if not token_table.empty and "separator_detected" in token_table.columns:
        sep_series = token_table.drop_duplicates("source_row_index")["separator_detected"]
        sep_dist = sep_series.value_counts().to_dict()

    missing_cols = {
        col: int(df_clean[col].isna().sum())
        for col in ["scientific_name", "manufacturer", "drug_class"]
        if col in df_clean.columns
    }

    stats: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": "0.1.0",
        "source": {
            "raw_row_count": int(len(df_raw)),
            "raw_column_count": int(len(df_raw.columns)),
        },
        "cleaning": {
            "exact_duplicates_flagged": int(df_clean.get("is_exact_duplicate", pd.Series(dtype=bool)).sum()),
            "name_duplicate_rows_flagged": int(df_clean.get("is_name_duplicate", pd.Series(dtype=bool)).sum()),
            "registration_status_counts": (
                df_clean["registration_status"].value_counts().to_dict()
                if "registration_status" in df_clean.columns
                else {}
            ),
        },
        "manufacturer_parsing": {
            "flag_counts": (
                df_clean["manufacturer_parse_flag"].value_counts().to_dict()
                if "manufacturer_parse_flag" in df_clean.columns
                else {}
            ),
        },
        "drug_class": {
            "total_distinct_raw": int(df_clean["drug_class"].nunique()),
            "mapped_to_canonical": int(df_clean.get("drug_class_reviewed", pd.Series(dtype=bool)).sum()),
            "unmapped_count": int(
                (df_clean["drug_class_reviewed"] == False).sum()  # noqa: E712
                if "drug_class_reviewed" in df_clean.columns
                else 0
            ),
        },
        "route": {
            "raw_distribution": (
                df_clean["route"].value_counts().to_dict()
                if "route" in df_clean.columns
                else {}
            ),
            "needs_review_count": int(df_clean.get("route_needs_review", pd.Series(dtype=bool)).sum()),
        },
        "missing_values": missing_cols,
        "scientific_name_parsing": {
            "total_records_parsed": len(parse_results),
            "records_with_missing_sci_name": flag_counts.get(FLAG_MISSING, 0),
            "records_with_truncated_list": flag_counts.get(FLAG_TRUNCATED, 0),
            "records_with_equals_ambiguous": flag_counts.get(FLAG_EQUALS_AMBIGUOUS, 0),
            "records_with_slash_ambiguous": flag_counts.get(FLAG_SLASH_AMBIGUOUS, 0),
            "records_with_mixed_separators": flag_counts.get(FLAG_MIXED_SEPARATORS, 0),
            "separator_distribution": sep_dist,
            "all_record_flag_counts": flag_counts,
        },
        "token_inventory": {
            "total_token_occurrences": int(len(token_table)),
            "unique_raw_tokens": int(len(freq_report)),
            "tokens_with_embedded_dose": tok_flag_counts.get(FLAG_EMBEDDED_DOSE, 0),
            "tokens_with_parenthetical": tok_flag_counts.get(FLAG_PARENTHETICAL, 0),
            "review_queue_unique_tokens": int(len(review_queue)),
            "review_queue_total_occurrences": int(
                review_queue["occurrence_count"].sum() if not review_queue.empty else 0
            ),
            "top_10_tokens": (
                freq_report.head(10)[["raw_token", "occurrence_count"]].to_dict("records")
                if not freq_report.empty
                else []
            ),
        },
        "raw_profile": raw_profile,
    }
    return stats


# ── HTML renderer ─────────────────────────────────────────────────────────────


def _render_html_report(stats: Dict[str, Any]) -> str:
    """Render a standalone HTML data-quality report.

    Args:
        stats: Output of ``build_dq_stats()``.

    Returns:
        HTML string.
    """
    def _kv_table(d: Dict) -> str:
        rows = "".join(
            f"<tr><td class='k'>{k}</td><td class='v'>{v}</td></tr>"
            for k, v in d.items()
        )
        return f"<table class='kv'>{rows}</table>"

    src = stats["source"]
    clean = stats["cleaning"]
    mfr = stats["manufacturer_parsing"]
    dc = stats["drug_class"]
    rt = stats["route"]
    mv = stats["missing_values"]
    sci = stats["scientific_name_parsing"]
    tok = stats["token_inventory"]

    top10_rows = "".join(
        f"<tr><td>{r['raw_token']}</td><td>{r['occurrence_count']}</td></tr>"
        for r in tok.get("top_10_tokens", [])
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Egyptian Drug Pipeline – DQ Report</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #222; }}
  h1 {{ color: #1a5276; }}
  h2 {{ color: #1f618d; border-bottom: 1px solid #aed6f1; padding-bottom: .3em; }}
  table.kv {{ border-collapse: collapse; margin-bottom: 1rem; }}
  table.kv td {{ padding: .25rem .75rem; border: 1px solid #d5d8dc; }}
  td.k {{ background: #eaf4fb; font-weight: 600; white-space: nowrap; }}
  td.v {{ font-family: monospace; }}
  .badge {{ display:inline-block; background:#1f618d; color:#fff;
            border-radius:4px; padding:.15rem .5rem; font-size:.85rem; }}
  table.top10 {{ border-collapse: collapse; }}
  table.top10 th, table.top10 td {{ border: 1px solid #ccc; padding: .25rem .6rem; }}
  table.top10 th {{ background: #d6eaf8; }}
  .warn {{ color: #b7950b; font-weight: 600; }}
  .ok {{ color: #1e8449; font-weight: 600; }}
</style>
</head>
<body>
<h1>Egyptian Drug Normalization Pipeline — Data-Quality Report</h1>
<p>Generated: <strong>{stats['generated_at']}</strong> &nbsp;|&nbsp;
   Pipeline version: <strong>{stats['pipeline_version']}</strong></p>

<h2>Source Dataset</h2>
{_kv_table({
    "Raw rows": src['raw_row_count'],
    "Columns": src['raw_column_count'],
})}

<h2>Row-Level Cleaning</h2>
{_kv_table({
    "Exact duplicate rows flagged": clean['exact_duplicates_flagged'],
    "Rows sharing a commercial name": clean['name_duplicate_rows_flagged'],
    "Registration-status flags": str(clean['registration_status_counts']),
})}

<h2>Missing Values</h2>
{_kv_table({c: f"{v} missing" for c, v in mv.items()})}

<h2>Manufacturer Parsing</h2>
{_kv_table(mfr['flag_counts'])}

<h2>Drug Class</h2>
{_kv_table({
    "Distinct raw values": dc['total_distinct_raw'],
    "Mapped to canonical": dc['mapped_to_canonical'],
    "Not yet mapped (review queue)": dc['unmapped_count'],
})}

<h2>Route</h2>
{_kv_table({
    "Raw distribution": str(rt['raw_distribution']),
    "Records needing route review": rt['needs_review_count'],
})}

<h2>scientific_name Parsing</h2>
{_kv_table({
    "Records parsed": sci['total_records_parsed'],
    "Missing scientific_name": f"<span class='warn'>{sci['records_with_missing_sci_name']}</span>",
    "Truncated lists (ends with '+')": sci['records_with_truncated_list'],
    "Equals-ambiguous": sci['records_with_equals_ambiguous'],
    "Slash-ambiguous": sci['records_with_slash_ambiguous'],
    "Mixed separators": sci['records_with_mixed_separators'],
    "Separator distribution": str(sci['separator_distribution']),
})}

<h2>Token Inventory</h2>
{_kv_table({
    "Total token occurrences": tok['total_token_occurrences'],
    "Unique raw tokens": tok['unique_raw_tokens'],
    "Tokens with embedded dose": tok['tokens_with_embedded_dose'],
    "Tokens with parenthetical content": tok['tokens_with_parenthetical'],
    "Review-queue unique tokens": tok['review_queue_unique_tokens'],
    "Review-queue total occurrences": tok['review_queue_total_occurrences'],
})}

<h3>Top 10 Most-Frequent Raw Tokens</h3>
<table class="top10">
<tr><th>Raw Token</th><th>Occurrences</th></tr>
{top10_rows}
</table>

<hr>
<p><em>This report was generated automatically.  All flags indicate records
that require human review before canonical name assignment or graph loading.</em></p>
</body>
</html>"""
    return html
